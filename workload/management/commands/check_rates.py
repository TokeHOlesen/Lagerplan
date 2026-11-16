from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from workload.ratesconfig import RatesError, describe, load_rates


class Command(BaseCommand):
    help = "Validate rates.toml and print the values the app will use."

    def handle(self, *args, **options):
        path = settings.WORKLOAD_RATES_PATH
        try:
            rates = load_rates(path)
        except (OSError, RatesError) as exc:
            raise CommandError(f"{path}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"{path} is valid."))
        self.stdout.write(describe(rates))
