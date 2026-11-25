import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    phone = models.CharField(max_length=40, blank=True)
    password_change_required = models.BooleanField(default=False)
    session_version = models.PositiveIntegerField(default=0)

    def _get_session_auth_hash(self, secret=None):
        original = super()._get_session_auth_hash(secret)
        if not self.session_version:
            return original
        from django.utils.crypto import salted_hmac

        return salted_hmac(
            "accounts.session_version",
            f"{original}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    def has_permission_code(self, code):
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        from .access import permission_codes

        return any(item.rsplit(".", 1)[-1] == code for item in permission_codes(self))


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.OneToOneField("auth.Group", on_delete=models.CASCADE, related_name="role")
    key = models.SlugField(max_length=80, null=True, unique=True, editable=False)
    description = models.CharField(max_length=400, blank=True)
    active = models.BooleanField(default=True)
    system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=180)
    institution_type = models.CharField(
        max_length=12,
        choices=[
            ("school", "School"),
            ("college", "College"),
            ("academy", "Academy"),
            ("other", "Other"),
        ],
    )
    registration_number = models.CharField(max_length=100, blank=True)
    principal = models.CharField(max_length=180, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Pakistan")
    currency = models.CharField(max_length=3, default="PKR")
    timezone = models.CharField(max_length=64, default="Asia/Karachi")
    language = models.CharField(
        max_length=2, default="en", choices=[("en", "English"), ("ur", "Urdu")]
    )
    logo_png = models.BinaryField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(condition=models.Q(singleton=1), name="one_institution")
        ]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window = models.DateTimeField(db_index=True)
    count = models.PositiveIntegerField(default=0)
