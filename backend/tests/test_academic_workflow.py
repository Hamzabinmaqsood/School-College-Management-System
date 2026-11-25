import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.access import permission_rows, seed_roles
from apps.accounts.models import Institution, Role, User
from apps.admissions.models import ProgressionEvent, StudentEnrollment
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from apps.students.models import Guardian, Student, StudentDocument, StudentGuardian
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

API = "/api/v1/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class AcademicWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_roles()
        cls.school = Institution.objects.create(
            code="trial", name="Trial Academy", institution_type="academy"
        )
        cls.identity = InstallationIdentity.objects.create(institution=cls.school)
        cls.operator = User.objects.create_superuser(username="academic-admin")
        cls.reader = User.objects.create_user(username="staff-user")
        cls.day = timezone.localdate()
        cls.term = AcademicSession.objects.create(
            institution=cls.school,
            name="Current term",
            code="CURRENT",
            start_date=cls.day,
            end_date=cls.day + timedelta(days=40),
            status="active",
            is_current=True,
        )
        cls.future = AcademicSession.objects.create(
            institution=cls.school,
            name="Next term",
            code="NEXT",
            start_date=cls.day + timedelta(days=41),
            end_date=cls.day + timedelta(days=81),
            status="active",
        )
        cls.grade = AcademicClass.objects.create(
            institution=cls.school, name="Group One", code="ONE"
        )
        cls.advanced = AcademicClass.objects.create(
            institution=cls.school, name="Group Two", code="TWO"
        )
        cls.room = Section.objects.create(
            academic_class=cls.grade, name="Blue", code="BLUE", capacity=1
        )
        cls.room2 = Section.objects.create(academic_class=cls.grade, name="Gold", code="GOLD")
        cls.other = Section.objects.create(academic_class=cls.advanced, name="Green", code="GREEN")

    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        keys = self.settings(
            LICENSE_PUBLIC_KEYS={"test": encode(self.key.public_key().public_bytes_raw())}
        )
        keys.enable()
        self.addCleanup(keys.disable)
        self.client = APIClient()
        self.client.force_login(self.operator)
        self.now = timezone.now()
        response = self.write("post", "license/activate/", {"token": self.token(self.now)})
        self.assertEqual(response.status_code, 201, response.content)

    def token(self, now):
        def wire(value):
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")

        raw = canonical(
            {
                "version": 1,
                "license_id": str(uuid4()),
                "institution_id": str(self.school.pk),
                "institution_name": self.school.name,
                "installation_id": str(self.identity.installation_id),
                "edition": "standard",
                "issued_at": wire(now - timedelta(days=1)),
                "valid_from": wire(now - timedelta(days=1)),
                "expires_at": wire(now + timedelta(days=2)),
                "duration": "custom",
                "features": ["academics", "admissions", "students"],
                "key_id": "test",
                "grace_days": 0,
            }
        )
        return f"SMS1.{encode(raw)}.{encode(self.key.sign(raw))}"

    def write(self, method, path, data):
        return getattr(self.client, method)(API + path, data, format="json")

    def admission(self, number="", section=None, roll="A-1", name="Test student"):
        return {
            "student": {
                "first_name": name,
                "birth_date": "2014-01-01",
                "admission_date": self.day.isoformat(),
                **({"admission_number": number} if number else {}),
            },
            "enrollment": {
                "session": str(self.term.pk),
                "academic_class": str(self.grade.pk),
                "section": str(section.pk) if section else None,
                "roll_number": roll,
            },
        }

    def test_academic_registries_current_and_duplicates(self):
        failed = self.write(
            "post",
            "academic-sessions/",
            {
                "name": "Invalid",
                "code": "bad",
                "start_date": "2026-02-01",
                "end_date": "2026-01-01",
            },
        )
        self.assertEqual(failed.status_code, 400)
        result = self.write("post", f"academic-sessions/{self.future.pk}/set-current/", {})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(AcademicSession.objects.filter(is_current=True).get(), self.future)
        self.assertEqual(
            self.write("post", "classes/", {"name": "Duplicate", "code": "one"}).status_code, 409
        )
        subject = self.write("post", "subjects/", {"name": "Mathematics", "code": "MATH"})
        self.assertEqual(subject.status_code, 201, subject.content)
        self.assertEqual(
            self.write("post", "subjects/", {"name": "Duplicate", "code": "math"}).status_code, 409
        )
        assignment = {
            "academic_class": str(self.grade.pk),
            "subject": subject.json()["id"],
            "mandatory": False,
        }
        self.assertEqual(self.write("post", "class-subjects/", assignment).status_code, 201)
        self.assertIn(self.write("post", "class-subjects/", assignment).status_code, [400, 409])

    def test_admission_is_atomic_capacity_and_roll_scope(self):
        wrong = self.write("post", "admissions/", self.admission("WRONG", self.other))
        self.assertEqual(wrong.status_code, 400, wrong.content)
        self.assertFalse(Student.objects.exists())
        first = self.write("post", "admissions/", self.admission(section=self.room))
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(Student.objects.get().admission_number, "ADM-00001")
        self.assertEqual(
            self.write("post", "admissions/", self.admission("FULL", self.room, "B")).status_code,
            400,
        )
        self.assertEqual(
            self.write("post", "admissions/", self.admission("OTHER", self.room2)).status_code, 201
        )
        self.assertEqual(
            self.write("post", "admissions/", self.admission("ROLL", self.room2)).status_code, 400
        )
        self.assertEqual(
            self.write("post", "admissions/", self.admission("other", roll="UNIQUE")).status_code,
            409,
        )
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(StudentEnrollment.objects.count(), 2)

    def test_progression_and_guardian_history(self):
        guardian = Guardian.objects.create(
            institution=self.school, full_name="Test guardian", phone="555-0199"
        )
        data = self.admission(section=self.room)
        data["guardians"] = [
            {"guardian": str(guardian.pk), "relationship": "Parent", "primary": True}
        ]
        admitted = self.write("post", "admissions/", data)
        self.assertEqual(admitted.status_code, 201, admitted.content)
        first = admitted.json()
        self.assertEqual(StudentGuardian.objects.get().guardian, guardian)
        repeat_link = self.write(
            "post", f"students/{first['student']}/guardians/", data["guardians"][0]
        )
        self.assertEqual(repeat_link.status_code, 409)
        self.assertTrue(StudentGuardian.objects.get().primary)
        metrics = self.client.get(API + "students/summary/").json()
        self.assertEqual(
            (metrics["active_students"], metrics["current_enrollments"], metrics["new_admissions"]),
            (1, 1, 1),
        )
        transfer = self.write(
            "post",
            f"admissions/{first['id']}/transfer/",
            {
                "effective_date": self.day.isoformat(),
                "target": self.admission(section=self.room2)["enrollment"],
            },
        )
        self.assertEqual(transfer.status_code, 200, transfer.content)
        second = transfer.json()
        result = self.write(
            "post",
            f"admissions/{second['id']}/promote/",
            {
                "effective_date": self.future.start_date.isoformat(),
                "target": {
                    "session": str(self.future.pk),
                    "academic_class": str(self.advanced.pk),
                    "section": str(self.other.pk),
                    "roll_number": "P1",
                },
            },
        )
        self.assertEqual(result.status_code, 200, result.content)
        statuses = dict(StudentEnrollment.objects.values_list("id", "status"))
        self.assertEqual(sorted(statuses.values()), ["active", "promoted", "transferred"])
        self.assertEqual(ProgressionEvent.objects.count(), 2)
        self.assertEqual(
            self.client.get(API + f"students/{first['student']}/history/").json()["count"], 3
        )
        withdrawn = self.write(
            "post",
            f"admissions/{result.json()['id']}/withdraw/",
            {
                "effective_date": self.future.start_date.isoformat(),
            },
        )
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
        self.assertEqual(Student.objects.get().status, "withdrawn")
        reenrolled = self.write(
            "post",
            f"admissions/{result.json()['id']}/re-enroll/",
            {
                "effective_date": self.future.start_date.isoformat(),
                "target": {
                    "session": str(self.future.pk),
                    "academic_class": str(self.advanced.pk),
                    "roll_number": "P1",
                },
            },
        )
        self.assertEqual(reenrolled.status_code, 200, reenrolled.content)
        self.assertEqual(StudentEnrollment.objects.count(), 4)

    def test_document_upload_privacy_and_archive(self):
        reply = self.write("post", "admissions/", self.admission(section=self.room))
        self.assertEqual(reply.status_code, 201, reply.content)
        student = reply.json()["student"]
        url = f"students/{student}/documents/"
        spoofed = SimpleUploadedFile("fake.png", b"<script>no</script>", content_type="image/png")
        bad = self.client.post(
            API + url, {"kind": "photo", "label": "Profile", "file": spoofed}, format="multipart"
        )
        self.assertEqual(bad.status_code, 400)
        image = BytesIO()
        Image.new("RGB", (40, 40), "navy").save(image, "JPEG")
        upload = SimpleUploadedFile(
            "personal-name.jpg", image.getvalue(), content_type="image/jpeg"
        )
        document = self.client.post(
            API + url, {"kind": "photo", "label": "Portrait", "file": upload}, format="multipart"
        )
        self.assertEqual(document.status_code, 201, document.content)
        target = f"{url}{document.json()['id']}/"
        response = self.client.get(API + target + "download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Image.open(BytesIO(response.content)).format, "PNG")
        self.assertNotIn("personal-name", response["Content-Disposition"])
        reader = APIClient()
        reader.force_login(self.reader)
        self.assertEqual(reader.get(API + target + "download/").status_code, 403)
        self.assertEqual(APIClient().get(API + target + "download/").status_code, 401)
        self.assertEqual(self.write("post", target + "archive/", {}).status_code, 204)
        self.assertEqual(self.client.get(API + target + "download/").status_code, 404)
        self.assertTrue(StudentDocument.objects.filter(archived_at__isnull=False).exists())

    def test_roles_licensing_expiration_and_exports(self):
        self.assertEqual(APIClient().get(API + "students/").status_code, 401)
        self.assertEqual(
            self.write("post", "admissions/", self.admission(name="=2+2")).status_code, 201
        )
        role = self.write("post", "roles/", {"name": "Academic reader"}).json()
        role_id = role["id"]
        grants = permission_rows({"accounts.view_students", "accounts.export_students"})
        group = Role.objects.get(pk=role_id).group
        group.permissions.set(grants)
        self.reader.groups.add(group)
        reader = APIClient()
        reader.force_login(self.reader)
        self.assertEqual(reader.get(API + "students/").status_code, 200)
        self.assertEqual(reader.post(API + "students/", {}).status_code, 403)
        later = self.now + timedelta(days=3)
        with patch("apps.licensing.service.utc_now", return_value=later):
            denied = self.write("post", "admissions/", self.admission("LATE", roll="SECOND"))
            self.assertEqual(denied.json()["code"], "LICENSE_WRITE_DENIED")
            self.assertIn("'=2+2", reader.get(API + "students/export/").content.decode("utf-8-sig"))
            self.assertEqual(reader.get(API + "students/").status_code, 200)
            self.assertEqual(
                self.write("post", "license/activate/", {"token": self.token(later)}).status_code,
                201,
            )
            self.assertEqual(
                self.write(
                    "post", "admissions/", self.admission("RENEWED", roll="SECOND")
                ).status_code,
                201,
            )
        self.assertEqual(
            self.write("put", f"roles/{role_id}/permissions/", {"permissions": []}).status_code, 200
        )
        self.assertEqual(reader.get(API + "students/").status_code, 403)

    def test_postgresql_composite_fk_and_unique_active_enrollment(self):
        response = self.write("post", "admissions/", self.admission(section=self.room))
        self.assertEqual(response.status_code, 201, response.content)
        student = Student.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentEnrollment.objects.create(
                student=student,
                session=self.term,
                academic_class=self.grade,
                section=self.room2,
                enrollment_date=self.day,
            )
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only composite constraint")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentEnrollment.objects.create(
                student=student,
                session=self.term,
                academic_class=self.grade,
                section=self.other,
                enrollment_date=self.day,
                status="withdrawn",
                ended_on=self.day,
            )

    def test_multipart_wizard_rolls_back_documents_and_guardians(self):
        form = self.admission(section=self.room)
        form["guardians"] = [
            {
                "new_guardian": {"full_name": "Parent", "phone": "555-0111"},
                "relationship": "Parent",
                "primary": True,
            }
        ]
        form["documents"] = [{"field": "file_0", "label": "Unreadable", "kind": "admission-form"}]
        reply = self.client.post(
            API + "admissions/",
            {
                "payload": json.dumps(form),
                "file_0": SimpleUploadedFile("scan.png", b"invalid"),
            },
            format="multipart",
        )
        self.assertEqual(reply.status_code, 400, reply.content)
        self.assertFalse(Student.objects.exists())
        self.assertFalse(Guardian.objects.exists())
        self.assertFalse(StudentDocument.objects.exists())
