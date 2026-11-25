from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from apps.accounts.access import permission_codes, permission_rows, seed_roles
from apps.accounts.models import Institution, User
from apps.audit.models import AuditEvent
from apps.licensing.models import InstallationIdentity
from apps.licensing.permissions import LicensedBusinessWrites
from apps.licensing.protocol import calendar_end, canonical, decode, encode, validate
from config.urls import urlpatterns as application_urls
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

LICENSE = "/api/v1/license/"
NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def sign(payload, key):
    raw = canonical(validate(payload))
    return f"SMS1.{encode(raw)}.{encode(key.sign(raw))}"


def wire(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class BusinessRole(BasePermission):
    def has_permission(self, request, view):
        return "accounts.view_students" in permission_codes(request.user)


class BusinessFixture(APIView):
    permission_classes = (IsAuthenticated, BusinessRole, LicensedBusinessWrites)
    license_feature = "students"

    def get(self, request):
        return Response({"record": Institution.objects.first().name})

    def post(self, request):
        return Response({"accepted": True})


class ExportBackupFixture(BusinessFixture):
    permission_classes = (IsAuthenticated, BusinessRole)


urlpatterns = [
    *application_urls,
    path("test-business/", BusinessFixture.as_view()),
    path("test-export/", ExportBackupFixture.as_view()),
    path("test-backup/", ExportBackupFixture.as_view()),
]


@override_settings(ROOT_URLCONF=__name__, LICENSE_PUBLIC_KEYS_FILE="")
class LicensingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_roles()
        cls.institution = Institution.objects.create(
            code="trial", name="Trial school", institution_type="school"
        )
        cls.installation = InstallationIdentity.objects.create(institution=cls.institution)
        cls.admin = User.objects.create_superuser(username="admin")
        cls.reader = User.objects.create_user(username="reader")
        cls.reader.user_permissions.set(
            permission_rows({"accounts.view_dashboard", "accounts.view_students"})
        )
        cls.unprivileged = User.objects.create_user(username="other")

    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        keys = self.settings(
            LICENSE_PUBLIC_KEYS={"trial": encode(self.key.public_key().public_bytes_raw())}
        )
        keys.enable()
        self.addCleanup(keys.disable)
        self.clock = patch("apps.licensing.service.utc_now", return_value=NOW)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.admin)

    def payload(self, **overrides):
        return {
            "version": 1,
            "license_id": str(uuid4()),
            "institution_id": str(self.institution.pk),
            "institution_name": self.institution.name,
            "installation_id": str(self.installation.installation_id),
            "edition": "standard",
            "issued_at": wire(NOW - timedelta(days=3)),
            "valid_from": wire(NOW - timedelta(days=2)),
            "expires_at": wire(NOW + timedelta(days=20)),
            "duration": "custom",
            "features": ["students"],
            "key_id": "trial",
            "grace_days": 0,
        } | overrides

    def activate(self, token, *, client=None, file=False):
        client = client or self.client
        csrf = client.get("/api/v1/auth/csrf/").json()["csrf_token"]
        values = (
            {"file": SimpleUploadedFile("trial.smslicense", token.encode())}
            if file
            else {"token": token}
        )
        return client.post(
            LICENSE + "activate/",
            values,
            format="multipart" if file else "json",
            HTTP_X_CSRFTOKEN=csrf,
        )

    def status(self, client=None):
        return (client or self.client).get(LICENSE + "status/").json()

    def test_activation_file_duplicate_renewal_replay_and_history(self):
        first = sign(self.payload(), self.key)
        success = self.activate(first, file=True)
        self.assertEqual(success.status_code, 201, success.content)
        self.assertEqual(success.json()["status"], "ACTIVE")
        self.assertTrue(self.activate(first).json()["duplicate"])
        renewed = self.activate(
            sign(self.payload(expires_at=wire(NOW + timedelta(days=45))), self.key)
        )
        self.assertEqual(renewed.status_code, 201, renewed.content)
        self.assertEqual(self.activate(first).json()["code"], "LICENSE_REPLAY")
        self.assertEqual(
            self.activate(sign(self.payload(), self.key)).json()["code"], "OLDER_LICENSE"
        )
        history = self.client.get(LICENSE + "history/").json()
        self.assertEqual(history["count"], 2)
        self.assertTrue(history["results"][0]["current"])
        self.assertNotIn("token", history["results"][0])
        self.assertTrue(AuditEvent.objects.filter(action="LICENSE_RENEWED").exists())
        self.assertNotIn(
            first, str(list(AuditEvent.objects.values_list("sanitized_metadata", flat=True)))
        )

    def test_rejects_tampering_invalid_key_and_identity_mismatch(self):
        payload = self.payload()
        original = sign(payload, self.key)
        prefix, _, signature = original.split(".")
        payload["expires_at"] = wire(NOW + timedelta(days=60))
        tampered = f"{prefix}.{encode(canonical(payload))}.{signature}"
        cases = [
            (tampered, "INVALID_SIGNATURE"),
            (sign(self.payload(), Ed25519PrivateKey.generate()), "INVALID_SIGNATURE"),
            (sign(self.payload(installation_id=str(uuid4())), self.key), "INSTALLATION_MISMATCH"),
            (sign(self.payload(institution_id=str(uuid4())), self.key), "INSTALLATION_MISMATCH"),
            (
                sign(self.payload(valid_from=wire(NOW + timedelta(days=1))), self.key),
                "NOT_YET_VALID",
            ),
            (sign(self.payload(expires_at=wire(NOW)), self.key), "EXPIRED"),
        ]
        for token, expected in cases:
            with self.subTest(expected=expected):
                response = self.activate(token)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], expected)
        self.assertEqual(self.status()["status"], "NOT_ACTIVATED")

    def test_expiration_grace_read_export_backup_and_rbac(self):
        self.activate(
            sign(self.payload(expires_at=wire(NOW + timedelta(days=1)), grace_days=3), self.key)
        )
        self.client.force_login(self.reader)
        self.assertNotIn("license", self.status())
        write = self.client.post("/test-business/", {})
        self.assertEqual(write.status_code, 403)  # A valid license does not bypass CSRF.
        client = APIClient()
        client.force_login(self.reader)
        self.assertEqual(client.post("/test-business/", {}).status_code, 200)
        client.force_login(self.unprivileged)
        self.assertEqual(client.post("/test-business/", {}).status_code, 403)
        client.force_login(self.reader)
        self.now.return_value = NOW + timedelta(days=1)
        self.assertEqual(self.status()["status"], "GRACE_PERIOD")
        self.assertEqual(client.post("/test-business/", {}).json()["code"], "LICENSE_WRITE_DENIED")
        with self.settings(LICENSE_GRACE_WRITES=True):
            self.assertEqual(client.post("/test-business/", {}).status_code, 200)
        self.now.return_value = NOW + timedelta(days=4)
        self.assertEqual(self.status()["status"], "EXPIRED")
        self.assertEqual(client.post("/test-business/", {}).status_code, 403)
        self.assertEqual(client.get("/test-business/").json()["record"], self.institution.name)
        for endpoint in ("/test-export/", "/test-backup/"):
            self.assertEqual(client.post(endpoint, {}).status_code, 200)

    def test_clock_review_persists_and_reissue_preserves_history(self):
        self.activate(sign(self.payload(), self.key))
        self.now.return_value = NOW - timedelta(minutes=1)
        self.assertEqual(self.status()["status"], "ACTIVE")
        self.now.return_value = NOW - timedelta(minutes=10)
        client = APIClient()
        client.force_login(self.reader)
        self.assertEqual(
            client.post("/test-business/", {}).json()["details"]["status"], "CLOCK_REVIEW_REQUIRED"
        )
        self.assertTrue(AuditEvent.objects.filter(action="LICENSE_CLOCK_REVIEW").exists())
        self.assertEqual(self.status()["status"], "CLOCK_REVIEW_REQUIRED")
        self.now.return_value = NOW
        self.assertEqual(self.status()["status"], "ACTIVE")
        self.assertTrue(AuditEvent.objects.filter(action="LICENSE_CLOCK_RECOVERED").exists())
        call_command("reissue_installation", "--confirm", str(self.installation.installation_id))
        self.installation.refresh_from_db()
        self.assertEqual(self.status()["status"], "NOT_ACTIVATED")
        self.assertEqual(self.client.get(LICENSE + "history/").json()["count"], 1)

    def test_unauthorized_activation_and_features(self):
        token = sign(self.payload(features=[]), self.key)
        self.assertEqual(APIClient().post(LICENSE + "activate/", {"token": token}).status_code, 401)
        reader = APIClient()
        reader.force_login(self.reader)
        self.assertEqual(self.activate(token, client=reader).status_code, 403)
        self.assertEqual(reader.get(LICENSE + "installation/").status_code, 403)
        self.assertEqual(self.activate(token).status_code, 201)
        self.assertEqual(
            reader.post("/test-business/", {}).json()["details"]["status"], "FEATURE_NOT_LICENSED"
        )

    def test_month_clamping_and_private_key_absence(self):
        start = datetime(2028, 1, 31, 20, 30, tzinfo=UTC)
        self.assertEqual(calendar_end(start, 1), datetime(2028, 2, 29, 20, 30, tzinfo=UTC))
        self.assertEqual(calendar_end(start, 3), datetime(2028, 4, 30, 20, 30, tzinfo=UTC))
        start = datetime(2026, 11, 30, tzinfo=UTC)
        token = sign(
            self.payload(
                valid_from=wire(start), expires_at=wire(calendar_end(start, 1)), duration="1m"
            ),
            self.key,
        )
        self.assertNotIn(self.key.private_bytes_raw(), decode(token.split(".")[1]))
        self.assertEqual(len(decode(token.split(".")[2])), 64)
