from io import BytesIO
from unittest.mock import patch

from apps.accounts.access import ADMIN, guard_admin_loss, seed_roles
from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

API = "/api/v1/"
PASSWORD = "test-only-Sign-in!721"
NEW_PASSWORD = "different-test-Password!732"


class FoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_roles()
        cls.owner = User.objects.create_user(username="bootstrap", password=PASSWORD)
        cls.owner.groups.add(Role.objects.get(key=ADMIN).group)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def write(self, method, path, body=None):
        token = self.client.get(API + "auth/csrf/").json()["csrf_token"]
        return getattr(self.client, method)(
            API + path, body or {}, format="json", HTTP_X_CSRFTOKEN=token
        )

    def login(self, username="bootstrap", password=PASSWORD):
        return self.write("post", "auth/login/", {"username": username, "password": password})

    def test_authentication_and_csrf(self):
        self.assertEqual(self.client.get(API + "auth/me/").status_code, 401)
        self.assertEqual(self.client.post(API + "auth/login/", {}, format="json").status_code, 403)
        failed = self.login(password="invalid")
        self.assertEqual(failed.json()["code"], "INVALID_CREDENTIALS")
        signed_in = self.login()
        self.assertEqual(signed_in.status_code, 200)
        self.assertTrue(signed_in.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.get(API + "auth/me/").json()["username"], "bootstrap")
        self.assertEqual(self.client.post(API + "auth/logout/").status_code, 403)
        self.assertEqual(self.write("post", "auth/logout/").status_code, 204)
        self.assertEqual(self.client.get(API + "auth/me/").status_code, 401)
        self.assertEqual(
            set(AuditEvent.objects.values_list("action", flat=True)),
            {"LOGIN_FAILED", "LOGIN_SUCCEEDED", "LOGOUT"},
        )
        self.assertNotIn(PASSWORD, str(list(AuditEvent.objects.values("sanitized_metadata"))))

    @override_settings(APP_LOGIN_LIMIT=2, APP_SESSION_IDLE=5)
    def test_rate_limit_disabled_user_and_session_timeout(self):
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.login().status_code, 429)
        session = self.client.session
        session["app_last_seen"] = 1
        session.save()
        self.assertEqual(self.client.get(API + "auth/me/").status_code, 401)
        User.objects.create_user(username="disabled", password=PASSWORD, is_active=False)
        self.assertEqual(self.login("disabled").json()["code"], "INVALID_CREDENTIALS")

    def test_institution_and_user_management(self):
        self.assertEqual(self.login().status_code, 200)
        created = self.write(
            "patch",
            "institution/",
            {"code": "test", "name": "Test School", "institution_type": "school"},
        )
        self.assertEqual(created.status_code, 200, created.content)
        self.assertEqual(created.json()["country"], "Pakistan")
        self.assertEqual(self.client.get(API + "institution/").json()["name"], "Test School")
        roles = list(Role.objects.exclude(key=ADMIN).values_list("pk", flat=True)[:2])
        record = self.write(
            "post",
            "users/",
            {"username": "member", "password": PASSWORD, "role_ids": [str(key) for key in roles]},
        )
        self.assertEqual(record.status_code, 201, record.content)
        member = record.json()
        self.assertEqual(len(member["roles"]), 2)
        self.assertNotIn("password", member)
        detail = f"users/{member['id']}/"
        self.assertEqual(self.write("patch", detail, {"first_name": "Updated"}).status_code, 200)
        admin_client, self.client = self.client, APIClient(enforce_csrf_checks=True)
        result = self.login("member")
        self.assertTrue(result.json()["password_change_required"])
        self.assertEqual(self.client.get(API + "users/").status_code, 403)
        changed = self.write(
            "post",
            "auth/change-password/",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertFalse(changed.json()["password_change_required"])
        self.assertEqual(self.client.get(API + "institution/").status_code, 403)
        member_client, self.client = self.client, admin_client
        self.assertEqual(
            self.write("post", detail + "reset-password/", {"password": PASSWORD}).status_code, 200
        )
        self.assertEqual(member_client.get(API + "auth/me/").status_code, 401)
        self.assertEqual(self.write("post", detail + "deactivate/").status_code, 200)
        self.assertEqual(self.write("post", detail + "activate/").status_code, 200)
        self.assertNotIn(PASSWORD, str(list(AuditEvent.objects.values("sanitized_metadata"))))

    def test_role_changes_and_privilege_escalation(self):
        self.assertEqual(self.login().status_code, 200)
        role = self.write("post", "roles/", {"name": "Restricted operator"}).json()
        permissions_url = f"roles/{role['id']}/permissions/"
        grants = [
            "accounts.view_user",
            "auth.view_group",
            "accounts.manage_role_permissions",
            "accounts.assign_roles",
        ]
        self.assertEqual(
            self.write("put", permissions_url, {"permissions": grants}).status_code, 200
        )
        admin_client = self.client
        member = User.objects.create_user(username="operator", password=PASSWORD)
        member.groups.add(Role.objects.get(pk=role["id"]).group)
        self.client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.login("operator").status_code, 200)
        self.assertEqual(self.client.get(API + "users/").status_code, 200)
        denied = self.write("put", permissions_url, {"permissions": ["accounts.suspend_user"]})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.write("patch", f"users/{member.pk}/", {"role_ids": []}).status_code, 403
        )
        member_client, self.client = self.client, admin_client
        self.assertEqual(self.write("put", permissions_url, {"permissions": []}).status_code, 200)
        self.assertEqual(member_client.get(API + "users/").status_code, 403)
        self.assertEqual(self.write("delete", f"roles/{role['id']}/").status_code, 400)
        self.assertEqual(
            self.write("delete", f"roles/{Role.objects.get(key=ADMIN).pk}/").status_code, 403
        )

    def test_logo_requires_image_content_and_is_reencoded(self):
        self.assertEqual(self.login().status_code, 200)
        data = {"code": "demo", "name": "Test Institution", "institution_type": "school"}
        token = self.client.get(API + "auth/csrf/").json()["csrf_token"]
        url = API + "institution/"
        bogus = SimpleUploadedFile("logo.png", b"<html>", content_type="image/png")
        failure = self.client.patch(
            url, {**data, "logo": bogus}, format="multipart", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(failure.status_code, 400)
        source = BytesIO()
        Image.new("RGB", (32, 32), "navy").save(source, "JPEG")
        logo = SimpleUploadedFile(
            "untrusted-name.jpg", source.getvalue(), content_type="image/jpeg"
        )
        success = self.client.patch(
            url, {**data, "logo": logo}, format="multipart", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(success.status_code, 200, success.content)
        served = APIClient().get(success.json()["logo_url"])
        self.assertEqual(served["Content-Type"], "image/png")
        self.assertIn("institution-logo.png", served["Content-Disposition"])
        self.assertEqual(Image.open(BytesIO(served.content)).format, "PNG")

    def test_final_admin_and_superuser_protection(self):
        with self.assertRaises(PermissionDenied):
            guard_admin_loss(self.owner)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.write("post", f"users/{self.owner.pk}/deactivate/").status_code, 403)
        root = User.objects.create_superuser(username="root", password=PASSWORD)
        self.assertEqual(self.write("post", f"users/{root.pk}/deactivate/").status_code, 403)


class BootstrapTests(TestCase):
    def test_bootstrap_creates_role_bound_admin_once(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="initial-owner"),
            patch("getpass.getpass", return_value=PASSWORD),
        ):
            call_command("setup_admin")
            call_command("setup_admin")
        created = User.objects.get(username="initial-owner")
        self.assertTrue(created.check_password(PASSWORD))
        self.assertFalse(created.is_superuser)
        self.assertTrue(created.groups.filter(role__key=ADMIN).exists())
