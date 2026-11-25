from django.core.management.base import BaseCommand

from apps.accounts.access import seed_roles


class Command(BaseCommand):
    help = "Create missing permission definitions and system role templates."

    def handle(self, **options):
        seed_roles()
        self.stdout.write(
            self.style.SUCCESS("Permission catalog and system role templates are available.")
        )
