from apps.audit.models import AuditEvent
from django.contrib.auth import get_user_model
from django.test import TestCase


class AuditInfrastructureTests(TestCase):
    def test_audit_event_can_store_sanitized_metadata(self):
        user = get_user_model().objects.create_user(username="auditor")
        event = AuditEvent.objects.create(
            acting_user=user,
            action="VIEW",
            resource_type="student",
            resource_id="sample-id",
            request_id="sample-request",
            sanitized_metadata={"result": "redacted"},
        )
        self.assertEqual(event.resource_type, "student")
