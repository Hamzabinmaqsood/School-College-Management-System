import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase


class CustomUserTests(TestCase):
    def test_user_uses_uuid_primary_key(self):
        user = get_user_model().objects.create_user(
            username="foundation-user",
            password="not-a-real-production-password",
        )
        self.assertIsInstance(user.id, uuid.UUID)

    def test_superuser_has_permission_code(self):
        user = get_user_model().objects.create_superuser(
            username="foundation-admin",
            email="admin@example.local",
            password="not-a-real-production-password",
        )
        self.assertTrue(user.has_permission_code("export"))
