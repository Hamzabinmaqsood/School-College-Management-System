import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    acting_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=128, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    request_id = models.CharField(max_length=128, blank=True)
    sanitized_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-timestamp",)
        indexes = (
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["acting_user", "timestamp"]),
        )
