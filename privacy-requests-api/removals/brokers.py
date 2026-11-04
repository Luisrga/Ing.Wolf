"""Broker integration boundary.

Real brokers each have their own opt-out flow (web forms, email, APIs). This
module defines the interface the rest of the app depends on, plus a
*simulated* client so the whole pipeline can run and be tested without
contacting any third party.
"""
from typing import Protocol


class TemporaryBrokerError(Exception):
    """The broker is unavailable right now; the task should be retried."""


class PermanentBrokerError(Exception):
    """The broker rejected the request; retrying will not help."""


class BrokerClient(Protocol):
    def submit_opt_out(self, request) -> None: ...


class SimulatedBrokerClient:
    """Deterministic fake used for the demo.

    Brokers whose name starts with ``flaky-`` always fail temporarily and
    ``reject-`` brokers fail permanently, which makes retry behaviour easy to
    demonstrate and test.
    """

    def submit_opt_out(self, request) -> None:
        name = request.broker.name.lower()
        if name.startswith("flaky-"):
            raise TemporaryBrokerError(f"{request.broker.name} is unavailable")
        if name.startswith("reject-"):
            raise PermanentBrokerError(f"{request.broker.name} rejected the request")


def get_broker_client() -> BrokerClient:
    return SimulatedBrokerClient()
