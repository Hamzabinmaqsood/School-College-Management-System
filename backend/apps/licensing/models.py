import uuid

from django.db import models


class InstallationIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.OneToOneField("accounts.Institution", on_delete=models.PROTECT)
    installation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_verified_at = models.DateTimeField(null=True, editable=False)
    clock_review = models.BooleanField(default=False, editable=False)
    current = models.ForeignKey(
        "LicenseActivation",
        on_delete=models.PROTECT,
        null=True,
        editable=False,
        related_name="+",
    )


class LicenseActivation(models.Model):
    license_id = models.UUIDField(primary_key=True, editable=False)
    installation = models.ForeignKey(
        InstallationIdentity, on_delete=models.PROTECT, related_name="activations"
    )
    token = models.TextField(editable=False)
    activated_at = models.DateTimeField(auto_now_add=True)
