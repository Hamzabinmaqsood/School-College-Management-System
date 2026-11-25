from uuid import UUID, uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.models import AuditEvent
from apps.licensing.service import installation


class Command(BaseCommand):
    help = "Rotate the installation ID after arranging vendor reissue."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm", type=UUID, required=True, help="The current installation ID"
        )

    @transaction.atomic
    def handle(self, **options):
        identity = installation(lock=True)
        if not identity or identity.installation_id != options["confirm"]:
            raise CommandError("The confirmation does not match this installation.")
        previous = identity.installation_id
        identity.installation_id = uuid4()
        identity.last_verified_at = None
        identity.clock_review = False
        identity.current = None
        identity.save(
            update_fields=["installation_id", "last_verified_at", "clock_review", "current"]
        )
        AuditEvent.objects.create(
            action="LICENSE_INSTALLATION_REISSUED",
            resource_type="installation",
            resource_id=str(identity.pk),
            sanitized_metadata={"previous_installation_id": str(previous)},
        )
        self.stdout.write(
            f"Installation {identity.installation_id} requires a new vendor-signed license."
        )
