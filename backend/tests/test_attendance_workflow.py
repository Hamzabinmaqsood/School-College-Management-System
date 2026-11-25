from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, ClassSubject, Section, Subject
from apps.accounts.access import permission_rows, seed_roles
from apps.accounts.models import Institution, User
from apps.admissions.models import StudentEnrollment
from apps.attendance.access import group_allowed
from apps.attendance.models import AttendanceCorrection, AttendanceRecord, TeachingAssignment
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from apps.students.models import Student
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

API = "/api/v1/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class AttendanceWorkflowTests(TestCase):
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
            start_date=cls.day - timedelta(days=10),
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
                "features": ["academics", "admissions", "attendance", "students"],
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

    def criteria(self, **overrides):
        return {
            "session": str(self.term.pk),
            "academic_class": str(self.grade.pk),
            "date": self.day.isoformat(),
            "mode": "daily",
            **overrides,
        }

    def open_register(self, **overrides):
        result = self.write("post", "attendance/", self.criteria(**overrides))
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def action(self, register, action, **data):
        return self.write(
            "post",
            f"attendance/{register['id']}/{action}/",
            {"version": register["version"], **data},
        )

    def test_register_lifecycle_reports_and_expired_license(self):
        student = self.add_student(name="=طالب علم")
        response = self.client.get(API + "attendance/roster/", self.criteria())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["roster"][0]["student"], str(student.pk))
        draft = self.open_register()
        self.assertEqual(self.write("post", "attendance/", self.criteria()).status_code, 200)
        self.assertEqual(self.action(draft, "finalize").status_code, 400)
        mark = {"record": draft["records"][0]["id"], "status": "late", "remarks": "Private remark"}
        saved = self.action(draft, "save", marks=[mark])
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(self.action(draft, "save", marks=[mark]).status_code, 409)
        summary = self.client.get(API + "attendance/summary/")
        self.assertEqual(summary.status_code, 200, summary.content)
        self.assertEqual(summary.json()["status"], "incomplete")
        self.assertIsNone(summary.json()["totals"]["percentage"])
        final = self.action(saved.json(), "finalize")
        self.assertEqual(final.status_code, 200, final.content)
        self.assertEqual(self.action(final.json(), "save", marks=[mark]).status_code, 409)
        result = self.action(
            final.json(),
            "correct",
            record=mark["record"],
            status="absent",
            reason="Verified correction",
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(AttendanceCorrection.objects.get().previous_status, "late")
        summary = self.client.get(API + "attendance/summary/").json()
        self.assertEqual((summary["status"], summary["totals"]["percentage"]), ("finalized", 0))
        history = self.client.get(API + f"attendance/student/{student.pk}/")
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual(history.json()["totals"]["absent"], 1)
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=5)):
            self.assertEqual(
                self.action(
                    result.json(),
                    "correct",
                    record=mark["record"],
                    status="present",
                    reason="Change after expiry",
                ).status_code,
                403,
            )
            csv = self.client.get(API + "attendance/export/", {"report": "daily"})
            self.assertEqual(csv.status_code, 200, csv.content)
            self.assertIn("'=طالب علم", csv.content.decode("utf-8-sig"))
            self.assertNotIn("Private remark", csv.content.decode("utf-8-sig"))
            printable = self.client.get(API + "attendance/print/", {"report": "daily"})
            self.assertContains(printable, "Attendance report")

    def test_teacher_scope_period_and_assignment_revocation(self):
        self.add_student(room=self.room)
        subject = Subject.objects.create(institution=self.school, code="MATH", name="Mathematics")
        ClassSubject.objects.create(academic_class=self.grade, subject=subject)
        daily = self.open_register(section=str(self.room.pk))
        period = self.open_register(
            section=str(self.room.pk), mode="period", subject=str(subject.pk), period="p1"
        )
        self.assertEqual(period["period"], "P1")
        scope = self.write(
            "post",
            "attendance/assignments/",
            {
                "user": self.reader.pk,
                "session": str(self.term.pk),
                "academic_class": str(self.grade.pk),
                "section": str(self.room.pk),
                "subject": str(subject.pk),
            },
        )
        self.assertEqual(scope.status_code, 201, scope.content)
        self.reader.user_permissions.add(
            *permission_rows(
                [
                    "accounts.view_attendance",
                    "attendance.view_attendancesession",
                    "attendance.change_attendancerecord",
                    "accounts.view_attendance_history",
                ]
            )
        )
        limited = APIClient()
        limited.force_login(self.reader)
        result = limited.get(API + "attendance/")
        self.assertEqual([item["id"] for item in result.json()["results"]], [period["id"]])
        self.assertEqual(limited.get(API + f"attendance/{daily['id']}/").status_code, 404)
        self.assertEqual(limited.get(API + f"attendance/{period['id']}/").status_code, 200)
        self.assertEqual(limited.get(API + "attendance/export/").status_code, 403)
        assignment = scope.json()["id"]
        next_day, end_date = self.day + timedelta(days=1), self.day + timedelta(days=2)
        dated = self.write(
            "patch",
            f"attendance/assignments/{assignment}/",
            {
                "effective_start": next_day,
                "effective_end": end_date,
            },
        )
        self.assertEqual(dated.status_code, 200, dated.content)
        overlapping = self.write(
            "post",
            "attendance/assignments/",
            {
                "user": self.reader.pk,
                "session": self.term.pk,
                "academic_class": self.grade.pk,
                "section": self.room.pk,
                "subject": subject.pk,
                "effective_start": end_date,
            },
        )
        self.assertEqual(overlapping.status_code, 400, overlapping.content)
        group = {
            "session": self.term,
            "academic_class": self.grade,
            "section": self.room,
            "subject": subject,
            "date": next_day,
        }
        for day, allowed in (
            (self.day, False),
            (next_day, True),
            (end_date, True),
            (end_date + timedelta(days=1), False),
        ):
            with patch("apps.attendance.service.today", return_value=day):
                self.assertEqual(group_allowed(self.reader, group), allowed)
                self.assertTrue(group_allowed(self.reader, group, operational=False))
        TeachingAssignment.objects.update(active=False)
        self.assertEqual(limited.get(API + f"attendance/{period['id']}/").status_code, 404)

    def test_calendar_leave_and_explicit_reconciliation(self):
        student = self.add_student()
        policy = self.write("patch", "attendance/settings/", {"late_attended": False})
        self.assertEqual(policy.status_code, 200, policy.content)
        holiday = self.write(
            "post",
            "attendance/holidays/",
            {
                "date": self.day.isoformat(),
                "name": "Institution holiday",
                "kind": "institution",
            },
        )
        self.assertEqual(holiday.status_code, 201, holiday.content)
        self.assertEqual(self.write("post", "attendance/", self.criteria()).status_code, 400)
        draft = self.open_register(calendar_override="Authorized teaching group")
        finalized = self.action(draft, "finalize", acknowledge_unmarked=True)
        self.assertEqual(finalized.status_code, 200, finalized.content)
        leave = self.write(
            "post",
            "attendance/leaves/",
            {
                "student": str(student.pk),
                "session": str(self.term.pk),
                "start_date": self.day.isoformat(),
                "end_date": self.day.isoformat(),
                "reason": "Private leave reason",
            },
        )
        self.assertEqual(leave.status_code, 201, leave.content)
        leave_id = leave.json()["id"]
        self.assertEqual(
            self.write("post", f"attendance/leaves/{leave_id}/reject/", {}).status_code, 400
        )
        approved = self.write("post", f"attendance/leaves/{leave_id}/approve/", {})
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(AttendanceRecord.objects.get().status, "unmarked")
        result = self.action(
            finalized.json(),
            "correct",
            record=draft["records"][0]["id"],
            use_leave=True,
            reason="Reconcile approved request",
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(AttendanceRecord.objects.get().status, "excused")
        self.assertEqual(str(AttendanceCorrection.objects.get().leave_id), leave_id)
        detail = self.client.get(API + f"attendance/leaves/{leave_id}/")
        self.assertEqual(detail.json()["decisions"][-1]["status"], "approved")

    def test_historical_snapshot_and_bulk_rollback(self):
        student = self.add_student(room=self.room)
        placement = StudentEnrollment.objects.get(student=student)
        earlier = self.day - timedelta(days=3)
        student.admission_date = earlier
        student.save(update_fields=["admission_date"])
        placement.enrollment_date = earlier
        placement.save(update_fields=["enrollment_date"])
        before = self.open_register(section=str(self.room.pk), date=earlier.isoformat())
        result = self.action(
            before,
            "save",
            marks=[
                {"record": before["records"][0]["id"], "status": "present"},
                {"record": str(uuid4()), "status": "absent"},
            ],
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(AttendanceRecord.objects.get().status, "unmarked")
        placement.ended_on = self.day
        placement.status = "transferred"
        placement.save(update_fields=["ended_on", "status"])
        replacement = StudentEnrollment.objects.create(
            student=student,
            session=self.term,
            academic_class=self.grade,
            section=self.room2,
            enrollment_date=self.day,
            roll_number="G9",
        )
        current = self.open_register(section=str(self.room2.pk))
        self.assertEqual(current["records"][0]["enrollment"], str(replacement.pk))
        prior = self.client.get(API + f"attendance/{before['id']}/").json()
        self.assertEqual(prior["records"][0]["enrollment"], str(placement.pk))
        self.assertEqual(prior["records"][0]["roll_number"], "A-1")
        self.assertEqual(
            self.write("post", "attendance/", self.criteria(section=str(self.room.pk))).status_code,
            400,
        )
        if connection.vendor == "postgresql":
            with self.assertRaises(IntegrityError), transaction.atomic():
                AttendanceRecord.objects.filter(pk=current["records"][0]["id"]).update(date=earlier)


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class ConcurrentAttendanceTests(TransactionTestCase):
    token = AttendanceWorkflowTests.token
    write = AttendanceWorkflowTests.write
    admission = AttendanceWorkflowTests.admission
    add_student = AttendanceWorkflowTests.add_student
    criteria = AttendanceWorkflowTests.criteria
    open_register = AttendanceWorkflowTests.open_register

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent attendance writes require PostgreSQL row locks.")
        with transaction.atomic():
            AttendanceWorkflowTests.setUpTestData.__func__(self)
        AttendanceWorkflowTests.setUp(self)

    def test_concurrent_writes_do_not_overwrite_each_other(self):
        self.add_student()
        draft = self.open_register()
        record = draft["records"][0]["id"]
        route = API + f"attendance/{draft['id']}/save/"
        clients = [APIClient(), APIClient()]
        for client in clients:
            client.force_login(self.operator)
        start = Barrier(2)

        def update(client, status):
            close_old_connections()
            try:
                start.wait(timeout=10)
                response = client.post(
                    route,
                    {"version": draft["version"], "marks": [{"record": record, "status": status}]},
                    format="json",
                )
                return response.status_code, status
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, clients, ["present", "late"]))
        self.assertEqual(sorted(code for code, _ in results), [200, 409])
        self.assertEqual(AttendanceRecord.objects.get(pk=record).status, dict(results)[200])
