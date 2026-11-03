# Privacy Request Tracker API

A small backend service where people submit **data-removal (opt-out) requests**
to data brokers and track them until they are processed. Built with **Django,
Django REST Framework, Celery, PostgreSQL, RabbitMQ, Redis and Stripe**.

It is a portfolio project: it exercises the problems a real backend has
(async pipelines, retries, idempotency, billing webhooks, per-user data
isolation) without contacting any real third party.

> **What is simulated:** broker opt-outs go through a fake client
> (`removals/brokers.py`) and every demo broker is an `example.com` placeholder.
> **What is real:** the API, the task pipeline, the data model and the Stripe
> Checkout + webhook flow (use your own Stripe *test-mode* keys).

## Features

- Token-authenticated REST API (register, list brokers, create/list/filter requests).
- **Asynchronous processing with Celery** (RabbitMQ broker, Redis result backend):
  exponential backoff with jitter on temporary broker errors, no retry on
  permanent ones, and a periodic Celery beat job that recovers work lost to a
  crashed worker.
- **Idempotent tasks**: a request is atomically claimed (`PENDING -> PROCESSING`),
  so duplicate deliveries (`acks_late`) cannot submit it twice.
- **Business rule enforced twice**: the free plan allows 3 active requests
  (checked under a row lock), and a partial unique constraint in the database
  guarantees one active request per user and broker.
- **Stripe subscriptions**: Checkout Session creation and a webhook that verifies
  the signature, stores processed event ids (replays are no-ops) and applies the
  event in the same transaction.
- Users can only ever see their own requests.

## Architecture

```
client ──HTTP──▶ Django + DRF ──▶ PostgreSQL
                    │  create_requests()  (limit check, row lock)
                    └─ on_commit ──▶ RabbitMQ ──▶ Celery worker ──▶ broker client (simulated)
                                         ▲               │
                              Celery beat (stale recovery) └─▶ status updates in PostgreSQL
Stripe ──webhook (signed)──▶ /api/billing/webhook/ ──▶ Subscription
```

## Quick start

Needs Docker. Create a Stripe **test-mode** account only if you want to try billing.

```bash
cp .env.example .env          # fill the STRIPE_* values to try billing
docker compose up --build
```

The API is at http://localhost:8000 and the RabbitMQ UI at http://localhost:15672.

Without Docker (SQLite, tasks need a broker or `CELERY_TASK_ALWAYS_EAGER=1`):

```bash
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py seed_brokers
CELERY_TASK_ALWAYS_EAGER=1 python manage.py runserver
```

## Try it

```bash
# 1. Register and keep the token
TOKEN=$(curl -s localhost:8000/api/auth/register/ \
  -d username=ana -d email=ana@example.com -d password='Str0ng-demo-pass' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
H="Authorization: Token $TOKEN"

# 2. See the brokers, then request removal from two of them
curl -s -H "$H" localhost:8000/api/brokers/
curl -s -H "$H" -H 'Content-Type: application/json' -d '{"broker_ids":[1,2]}' localhost:8000/api/requests/

# 3. Watch them move from pending to submitted
curl -s -H "$H" "localhost:8000/api/requests/?status=submitted"

# 4. Hit the free-plan limit (402) and get the upgrade hint
curl -s -H "$H" -H 'Content-Type: application/json' -d '{"all_brokers":true}' localhost:8000/api/requests/
```

`flaky-demo-broker` always fails temporarily (watch the retries in the worker
log) and `reject-demo-broker` fails permanently.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register/` | Returns an auth token |
| POST | `/api/auth/token/` | Login: username + password |
| GET | `/api/brokers/` | Active brokers |
| GET / POST | `/api/requests/` | List (`?status=`) / create (`broker_ids` **or** `all_brokers`) |
| GET | `/api/requests/<id>/` | Own requests only |
| POST | `/api/billing/checkout/` | Returns a Stripe Checkout URL |
| GET | `/api/billing/status/` | `free` or `premium` |
| POST | `/api/billing/webhook/` | Stripe only; signature required |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

28 tests cover the API rules, per-user isolation, plan limits, task idempotency,
retry and give-up behaviour, stale-work recovery, and the Stripe webhook
(valid and invalid signatures, replays, cancellation). Tasks run eagerly in
tests; Stripe calls are mocked and webhooks are signed locally.

## Design notes and limits

- The broker call happens **outside** any database transaction, so a slow
  broker never holds a lock.
- Tasks are enqueued with `transaction.on_commit`, so a worker cannot receive an
  id whose row is not visible yet.
- The row lock used for the limit check is a no-op on SQLite; its effect shows
  on PostgreSQL. The partial unique constraint is the safety net in both.
- Not included on purpose: real broker integrations, email, rate limits beyond
  DRF throttling, API docs generation, and WorkOS/SSO.
- The suite passes on SQLite (default) and on PostgreSQL 16
  (`TEST_DATABASE_URL=postgres://... pytest`). The Docker Compose stack and the
  real RabbitMQ/Redis path are provided but were not run where this was written;
  tests run tasks in-process.
