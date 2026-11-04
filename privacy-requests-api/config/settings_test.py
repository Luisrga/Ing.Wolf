"""Settings used by the test suite: no external services are needed."""
import dj_database_url

from .settings import *  # noqa: F401,F403

# In-memory SQLite by default; set TEST_DATABASE_URL to run the suite on PostgreSQL.
DATABASES = {"default": dj_database_url.config(env="TEST_DATABASE_URL", default="sqlite://:memory:")}

# Run tasks inline in the calling process and never open a broker connection.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

STRIPE_SECRET_KEY = ""
STRIPE_PRICE_ID = ""
STRIPE_WEBHOOK_SECRET = ""
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # faster tests
