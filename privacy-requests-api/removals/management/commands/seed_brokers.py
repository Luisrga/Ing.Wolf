from django.core.management.base import BaseCommand

from removals.models import Broker

DEMO_BROKERS = [
    ("example-people-search", "https://example.com/optout/people-search"),
    ("example-background-check", "https://example.com/optout/background"),
    ("example-marketing-data", "https://example.com/optout/marketing"),
    ("example-address-finder", "https://example.com/optout/address"),
    # Behaviour hooks for the simulated client (see removals/brokers.py)
    ("flaky-demo-broker", "https://example.com/optout/flaky"),
    ("reject-demo-broker", "https://example.com/optout/reject"),
]


class Command(BaseCommand):
    help = "Create fictional demo brokers (example.com only, nothing real is contacted)."

    def handle(self, *args, **options):
        for name, url in DEMO_BROKERS:
            Broker.objects.get_or_create(name=name, defaults={"opt_out_url": url})
        self.stdout.write(self.style.SUCCESS(f"{len(DEMO_BROKERS)} demo brokers ready."))
