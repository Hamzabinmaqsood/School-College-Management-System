from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, ClassSubject, Section, Subject
from apps.accounts.access import permission_rows, seed_roles
from apps.accounts.models import Institution, User
from apps.attendance.models import TeachingAssignment
from apps.examinations import models
from apps.examinations.results import subject_result
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from apps.students.models import Student
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

API = "/api/v1/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class ExaminationTests(TestCase):
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
            start_date=cls.day.replace(day=1),
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
                "features": ["academics", "admissions", "examinations", "students"],
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

    def add_student(self, number="ATT-001", room=None, name="طالب علم"):
        result = self.write("post", "admissions/", self.admission(number, room, name=name))
        self.assertEqual(result.status_code, 201, result.content)
        return Student.objects.get(admission_number=number)

    def make(self, path, payload, status=201):
        response = self.write("post", "examinations/" + path + "/", payload)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def setup_exam(self):
        student = self.add_student(name="=طالب علم")
        subject = Subject.objects.create(institution=self.school, name="Mathematics", code="MATH")
        ClassSubject.objects.create(academic_class=self.grade, subject=subject)
        kind = self.make("types", {"name": "Final", "code": "FINAL"})
        self.make("types", {"name": "Duplicate", "code": "final"}, 409)
        scheme = self.make(
            "grading-schemes",
            {
                "name": "School grading",
                "basis": "percentage",
                "effective_from": self.term.start_date,
                "effective_to": self.term.end_date,
                "bands": [
                    {"label": "Fail", "minimum": "0", "points": "0", "passing": False},
                    {"label": "Pass", "minimum": "40", "points": "4", "passing": True},
                ],
            },
        )
        exam = self.make(
            "exams",
            {
                "name": "Term final",
                "code": "TERM",
                "exam_type": kind["id"],
                "session": self.term.pk,
                "scheme": scheme["id"],
                "start_date": self.day,
                "end_date": self.day,
            },
        )
        group = self.make("classes", {"exam": exam["id"], "academic_class": self.grade.pk})
        paper = self.make(
            "subjects",
            {
                "group": group["id"],
                "subject": subject.pk,
                "components": [{"name": "Theory", "maximum": "80", "minimum": "32"}],
            },
        )
        self.make(
            "schedules",
            {
                "subject": paper["id"],
                "date": self.day,
                "start_time": "09:00",
                "end_time": "10:00",
                "room": "A",
            },
        )
        self.make(
            "schedules",
            {
                "subject": paper["id"],
                "date": self.day,
                "start_time": "09:30",
                "end_time": "10:30",
                "room": "B",
            },
            400,
        )
        self.make(f"exams/{exam['id']}/schedule", {}, 200)
        self.make(f"exams/{exam['id']}/open", {}, 200)
        return student, group

    def marks(self):
        return self.get_exam("marks/").json()["results"]

    def get_exam(self, path, expected=200):
        result = self.client.get(API + "examinations/" + path)
        self.assertEqual(result.status_code, expected, result.content)
        return result

    def test_publish_correct_and_retry(self):
        student, group = self.setup_exam()
        submission = self.get_exam(f"marks/{self.marks()[0]['id']}/").json()
        path = f"marks/{submission['id']}/"
        mark = {"registration": submission["marks"][0]["registration"], "status": "marked"}
        self.make(path + "submit", {"version": submission["version"]}, 400)
        self.make(
            path + "save",
            {"version": submission["version"], "marks": [mark | {"obtained": "80.01"}]},
            400,
        )
        data = {"version": submission["version"], "marks": [mark | {"obtained": "64.00"}]}
        saved = self.make(path + "save", data, 200)
        self.make(path + "save", data, 409)
        submitted = self.make(path + "submit", {"version": saved["version"]}, 200)
        self.make(path + "verify", {"version": submitted["version"]}, 200)
        result = self.make("results", {"group": group["id"]})
        self.make(f"results/{result['id']}/publish", {"confirmed": True}, 400)
        self.make(f"results/{result['id']}/approve", {}, 200)
        self.make(f"results/{result['id']}/publish", {"confirmed": True}, 200)
        historical = self.get_exam(f"results/student/{student.pk}/").json()["results"][0]
        self.assertEqual((historical["percentage"], historical["gpa"]), ("80.00", "4.00"))
        self.assertContains(self.get_exam(f"results/{historical['id']}/report-card/"), "80.00")
        self.assertIn("'=طالب علم", self.get_exam("reports/class-results/export/").content.decode())
        self.make(f"results/{result['id']}/withdraw", {"reason": "Approved correction"}, 200)
        component = models.ExamAssessmentComponent.objects.get()
        revised = self.make(
            f"results/{result['id']}/correct",
            mark
            | {
                "obtained": "20.00",
                "component": component.pk,
                "reason": "Source sheet corrected",
            },
        )
        self.assertEqual(revised["revision"], 2)
        self.make(f"results/{revised['id']}/approve", {}, 200)
        self.make(f"results/{revised['id']}/publish", {"confirmed": True}, 200)
        revisions = self.get_exam(f"results/student/{student.pk}/").json()["results"]
        self.assertEqual(
            [(row["active"], row["percentage"]) for row in revisions],
            [(True, "25.00"), (False, "80.00")],
        )
        self.assertEqual(models.MarksCorrection.objects.get().previous["obtained"], "64.00")
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=5)):
            self.make("results", {"group": group["id"]}, 403)
            self.get_exam(f"results/{historical['id']}/report-card/")
            self.get_exam("reports/class-results/export/")

    def test_teaching_scope_and_database_mark_bounds(self):
        student, group = self.setup_exam()
        register = models.MarksSubmission.objects.get()
        ref = f"marks/{register.pk}/"
        self.reader.user_permissions.set(
            permission_rows(
                {
                    "accounts.view_exam_marks",
                    "accounts.enter_exam_marks",
                    "accounts.update_exam_marks",
                    "accounts.submit_exam_marks",
                }
            )
        )
        self.client.force_login(self.reader)
        self.get_exam(ref, 404)
        TeachingAssignment.objects.create(
            user=self.reader,
            session=self.term,
            academic_class=self.grade,
            subject=register.component.subject.subject,
        )
        row = self.get_exam(ref).json()
        self.assertEqual(row["marks"][0]["student"], student.first_name)
        self.make("results", {"group": group["id"]}, 403)
        self.make(ref + "verify", {"version": row["version"]}, 403)
        TeachingAssignment.objects.update(active=False)
        self.get_exam(ref, 404)
        if connection.vendor == "postgresql":
            with self.assertRaises(IntegrityError), transaction.atomic():
                register.marks.update(obtained="81.00", status="marked")

    def test_weighted_scores_distinguish_absence_and_missing(self):
        scheme = SimpleNamespace(
            basis="percentage",
            bands=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        minimum=Decimal(40), label="Pass", points=Decimal(4), passing=True
                    ),
                    SimpleNamespace(
                        minimum=Decimal(0), label="Fail", points=Decimal(0), passing=False
                    ),
                ]
            ),
        )
        subject = SimpleNamespace(
            subject_name="Mathematics",
            subject_id=uuid4(),
            weighted=True,
            scheme=scheme,
            passing_percentage=Decimal(40),
        )
        theory = SimpleNamespace(
            maximum=Decimal(80), minimum=None, weight=Decimal(80), required=True
        )
        practical = SimpleNamespace(
            maximum=Decimal(10), minimum=None, weight=Decimal(20), required=True
        )
        marked = SimpleNamespace(status="marked", obtained=Decimal(40))

        def run(status):
            return subject_result(
                subject,
                [
                    (theory, marked),
                    (practical, SimpleNamespace(status=status, obtained=None)),
                ],
                scheme,
            )

        self.assertEqual(run("absent")["percentage"], "40.00")
        self.assertEqual(run("exempt")["percentage"], "50.00")
        self.assertEqual(run("missing")["status"], "incomplete")
        self.assertEqual(run("withheld")["status"], "withheld")


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class ConcurrentMarksTests(TransactionTestCase):
    token = ExaminationTests.token
    admission = ExaminationTests.admission
    add_student = ExaminationTests.add_student
    write = ExaminationTests.write
    make = ExaminationTests.make
    setup_exam = ExaminationTests.setup_exam

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent marks saving requires PostgreSQL row locks.")
        with transaction.atomic():
            ExaminationTests.setUpTestData.__func__(self)
        ExaminationTests.setUp(self)

    def test_concurrent_writes_protect_a_submission_version(self):
        self.setup_exam()
        register = models.MarksSubmission.objects.get()
        mark = register.marks.get()
        route = API + f"examinations/marks/{register.pk}/save/"
        ready = Barrier(2)
        clients = [APIClient(), APIClient()]
        for client in clients:
            client.force_login(self.operator)

        def post(client, score):
            try:
                ready.wait(timeout=10)
                result = client.post(
                    route,
                    {
                        "version": register.version,
                        "marks": [
                            {
                                "registration": mark.registration_id,
                                "status": "marked",
                                "obtained": score,
                            }
                        ],
                    },
                    format="json",
                )
                return result.status_code, score
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(post, clients, ["52.00", "55.00"]))
        self.assertEqual(sorted(status for status, _ in statuses), [200, 409])
        mark.refresh_from_db()
        self.assertEqual(mark.obtained, Decimal(dict(statuses)[200]))
