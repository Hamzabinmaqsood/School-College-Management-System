from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import patch

from apps.academics.models import AcademicClass, AcademicSession, ClassSubject, Section, Subject
from apps.accounts.access import permission_rows, seed_roles
from apps.accounts.models import Institution, User
from apps.attendance.models import AttendanceHoliday, TeachingAssignment
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

URL = "/api/v1/timetables/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class TimetableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_roles()
        cls.school = Institution.objects.create(code="T", name="Timetable School")
        cls.identity = InstallationIdentity.objects.create(institution=cls.school)
        cls.operator = User.objects.create_superuser(username="planner")
        cls.reviewer = User.objects.create_user(username="reviewer")
        cls.reviewer.user_permissions.set(permission_rows(["accounts.approve_timetable"]))
        cls.teacher = User.objects.create_user(username="teacher")
        cls.teacher.user_permissions.set(permission_rows(["accounts.view_own_timetable"]))
        cls.substitute = User.objects.create_user(username="substitute")
        cls.section_date = date(2099, 5, 4)
        cls.session = AcademicSession.objects.create(
            institution=cls.school,
            code="T",
            name="Term",
            start_date=date(2099, 1, 1),
            end_date=date(2099, 12, 31),
        )
        cls.grade = AcademicClass.objects.create(institution=cls.school, code="1", name="Grade")
        cls.section = Section.objects.create(academic_class=cls.grade, code="A", name="Section A")
        cls.other = Section.objects.create(academic_class=cls.grade, code="B", name="Section B")
        cls.subject = Subject.objects.create(institution=cls.school, code="S", name="Science")
        ClassSubject.objects.create(academic_class=cls.grade, subject=cls.subject)
        for teacher in (cls.teacher, cls.substitute):
            TeachingAssignment.objects.create(
                session=cls.session,
                academic_class=cls.grade,
                subject=cls.subject,
                user=teacher,
            )

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.operator)
        self.now = timezone.now()
        key = Ed25519PrivateKey.generate()
        self.enterContext(
            self.settings(
                LICENSE_PUBLIC_KEYS={"fixture": encode(key.public_key().public_bytes_raw())}
            )
        )
        from uuid import uuid4

        def wire(value):
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")

        token = canonical(
            {
                "version": 1,
                "license_id": str(uuid4()),
                "institution_id": str(self.school.pk),
                "institution_name": self.school.name,
                "installation_id": str(self.identity.installation_id),
                "edition": "standard",
                "issued_at": wire(self.now - timedelta(hours=1)),
                "valid_from": wire(self.now - timedelta(hours=1)),
                "expires_at": wire(self.now + timedelta(days=2)),
                "duration": "custom",
                "features": ["attendance", "timetables"],
                "key_id": "fixture",
                "grace_days": 0,
            }
        )
        activated = self.api.post(
            "/api/v1/license/activate/",
            {
                "token": f"SMS1.{encode(token)}.{encode(key.sign(token))}",
            },
            format="json",
        )
        self.assertEqual(activated.status_code, 201, activated.content)

    def post(self, path, payload, status=201):
        response = self.api.post(URL + path, payload, format="json")
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def get(self, path, status=200, **params):
        response = self.api.get(URL + path, params)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def config(self):
        clock = {"starts_at": "08:00", "ends_at": "14:00"}
        morning = self.post(
            "shifts/", {"name": "Morning", "code": "AM", **clock, "weekdays": list(range(7))}
        )
        afternoon = self.post(
            "shifts/", {"name": "Afternoon", "code": "PM", **clock, "weekdays": list(range(7))}
        )
        room = self.post("rooms/", {"name": "Lab", "code": "LAB", "capacity": 25})
        period = self.post(
            "periods/",
            {
                "shift": morning["id"],
                "name": "Teaching",
                "code": "P1",
                "starts_at": "09:00",
                "ends_at": "10:00",
            },
        )
        other_period = self.post(
            "periods/",
            {
                "shift": afternoon["id"],
                "name": "Teaching",
                "code": "P2",
                "starts_at": "09:45",
                "ends_at": "10:30",
            },
        )
        self.post(
            "periods/",
            {
                "shift": morning["id"],
                "name": "Overlap",
                "code": "BREAK",
                "starts_at": "09:30",
                "ends_at": "10:30",
                "teaching": False,
            },
            409,
        )
        return morning, afternoon, room, period, other_period

    def draft(self, section, shift, session=None):
        date_range = {
            "effective_start": self.section_date,
            "effective_end": self.section_date + timedelta(days=30),
        }
        plan = self.post(
            "plans/",
            {
                "session": (session or self.session).pk,
                "section": section.pk,
                "shift": shift["id"],
                **date_range,
            },
        )
        version = self.get(f"plans/{plan['id']}/versions/")[0]
        return plan, version

    def flow(self, plan, version):
        endpoint = f"plans/{plan['id']}/"
        body = {"version": version["id"]}
        self.post(endpoint + "submit/", body, 200)
        self.post(endpoint + "approve/", body, 403)
        self.api.force_login(self.reviewer)
        self.post(endpoint + "approve/", body, 200)
        self.api.force_login(self.operator)
        self.post(endpoint + "publish/", body, 200)

    def lesson(self, version, period, room, teacher=None):
        return {
            "version": version["id"],
            "period": period["id"],
            "weekday": self.section_date.weekday(),
            "room": room["id"],
            "subject": self.subject.pk,
            "teacher": (teacher or self.teacher).pk,
        }

    def test_break_curriculum_and_assignment_validation(self):
        morning, _, room, period, _ = self.config()
        _, version = self.draft(self.section, morning)
        lesson = self.lesson(version, period, room)
        interval = self.post(
            "periods/",
            {
                "shift": morning["id"],
                "name": "Morning break",
                "code": "BRK",
                "starts_at": "10:00",
                "ends_at": "10:30",
                "teaching": False,
            },
        )
        other_subject = Subject.objects.create(
            institution=self.school, code="NE", name="Outside curriculum"
        )
        ineligible = User.objects.create_user(username="unassigned-teacher")
        for changes, message in (
            ({"period": interval["id"]}, "Choose a teaching period"),
            ({"subject": other_subject.pk}, "class curriculum"),
            ({"teacher": ineligible.pk}, "active assignment"),
        ):
            with self.subTest(message=message):
                self.assertIn(message, str(self.post("entries/", {**lesson, **changes}, 400)))
                self.assertEqual(self.get("entries/", version=version["id"])["count"], 0)
        self.post("entries/", lesson)
        self.assertEqual(self.get("entries/", version=version["id"])["count"], 1)

    def test_lesson_lookup_and_validation_share_curriculum_and_teacher_scope(self):
        from apps.admissions.models import StudentEnrollment
        from apps.hr import models as hr
        from apps.students.models import Student

        morning, _, room, period, _ = self.config()
        second_period = self.post(
            "periods/",
            {
                "shift": morning["id"],
                "name": "Second lesson",
                "code": "P2",
                "starts_at": "10:00",
                "ends_at": "11:00",
            },
        )
        plan, version = self.draft(self.section, morning)
        payload = self.lesson(version, period, room)
        options = f"plans/{plan['id']}/lesson-options/"
        another_session = AcademicSession.objects.create(
            institution=self.school,
            code="OTHER",
            name="Other term",
            start_date=self.session.start_date,
            end_date=self.session.end_date,
        )
        wrong_subject = Subject.objects.create(
            institution=self.school,
            code="WRONG-TERM",
            name="Other term subject",
        )
        ClassSubject.objects.create(
            academic_class=self.grade,
            subject=wrong_subject,
            session=another_session,
        )
        params = {
            "version": version["id"],
            "weekday": payload["weekday"],
            "subject": self.subject.pk,
            "period": period["id"],
        }
        result = self.get(options, **params)
        self.assertEqual([row["id"] for row in result["subjects"]], [str(self.subject.pk)])
        self.assertIn(str(self.teacher.pk), {row["id"] for row in result["teachers"]})
        teacher_ids = {row["id"] for row in result["teachers"]}

        other_class = AcademicClass.objects.create(
            institution=self.school, code="2", name="Other grade"
        )
        wrong_class = Subject.objects.create(institution=self.school, code="WC", name="Wrong class")
        inactive = Subject.objects.create(
            institution=self.school, code="IS", name="Inactive subject", active=False
        )
        inactive_curriculum = Subject.objects.create(
            institution=self.school, code="IC", name="Inactive curriculum"
        )
        ClassSubject.objects.create(academic_class=other_class, subject=wrong_class)
        ClassSubject.objects.create(academic_class=self.grade, subject=inactive)
        ClassSubject.objects.create(
            academic_class=self.grade, subject=inactive_curriculum, active=False
        )
        self.assertEqual(
            {row["id"] for row in self.get(options, **params)["subjects"]},
            {str(self.subject.pk)},
        )

        inactive_override = ClassSubject.objects.create(
            academic_class=self.grade,
            subject=self.subject,
            session=self.session,
            active=False,
        )
        scoped_options = self.get(options, **params)
        self.assertNotIn(str(self.subject.pk), {row["id"] for row in scoped_options["subjects"]})
        self.assertNotIn(str(self.teacher.pk), {row["id"] for row in scoped_options["teachers"]})
        self.post("entries/", payload, 400)
        inactive_override.delete()

        invalid_assignments = (
            {"academic_class": other_class},
            {"section": self.other},
            {"subject": wrong_class},
            {"session": another_session},
            {"active": False},
            {"effective_start": self.section_date + timedelta(days=1)},
            {"effective_end": self.section_date - timedelta(days=1)},
        )
        for index, changes in enumerate(invalid_assignments):
            teacher = User.objects.create_user(username=f"ineligible-{index}")
            assignment = {
                "user": teacher,
                "session": self.session,
                "academic_class": self.grade,
                "subject": self.subject,
                "active": True,
            }
            assignment.update(changes)
            TeachingAssignment.objects.create(**assignment)
        available = self.get(options, **params)["teachers"]
        available_ids = {row["id"] for row in available}
        self.assertEqual(available_ids, teacher_ids)

        assignment = TeachingAssignment.objects.get(user=self.teacher, session=self.session)
        assignment.effective_start = self.section_date + timedelta(days=1)
        assignment.save(update_fields=["effective_start"])
        self.assertNotIn(
            str(self.teacher.pk), {row["id"] for row in self.get(options, **params)["teachers"]}
        )
        self.post("entries/", payload, 400)
        assignment.effective_start = self.section_date
        assignment.effective_end = self.section_date + timedelta(days=28)
        assignment.save(update_fields=["effective_start", "effective_end"])
        department = hr.Department.objects.create(
            institution=self.school, name="Academic", code="L"
        )
        title = hr.Designation.objects.create(institution=self.school, name="Teacher", code="L")
        hr.Employee.objects.create(
            institution=self.school,
            department=department,
            designation=title,
            user=self.teacher,
            code="L",
            first_name="Teacher",
            employment_type="contract",
            joined_on=self.section_date + timedelta(days=1),
        )
        self.assertNotIn(
            str(self.teacher.pk), {row["id"] for row in self.get(options, **params)["teachers"]}
        )
        self.assertIn("employment or contract", str(self.post("entries/", payload, 400)))
        self.assertEqual(self.get("entries/", version=version["id"])["count"], 0)
        hr.Employee.objects.filter(user=self.teacher).update(joined_on=self.section_date)
        self.assertIn(
            str(self.teacher.pk), {row["id"] for row in self.get(options, **params)["teachers"]}
        )
        hr.Employee.objects.filter(user=self.teacher).update(
            joined_on=self.section_date - timedelta(days=1),
            ended_on=self.section_date - timedelta(days=1),
        )
        self.assertNotIn(
            str(self.teacher.pk), {row["id"] for row in self.get(options, **params)["teachers"]}
        )
        hr.Employee.objects.filter(user=self.teacher).update(
            ended_on=None, status="suspended"
        )
        self.assertNotIn(
            str(self.teacher.pk), {row["id"] for row in self.get(options, **params)["teachers"]}
        )
        hr.Employee.objects.filter(user=self.teacher).update(status="active")
        self.post("entries/", payload)

        optional_subject = Subject.objects.create(
            institution=self.school, code="OPTIONAL", name="Optional subject"
        )
        ClassSubject.objects.create(
            academic_class=self.grade,
            subject=optional_subject,
            session=self.session,
            mandatory=False,
        )
        optional_params = {**params, "subject": optional_subject.pk}
        self.assertNotIn(
            str(optional_subject.pk),
            {row["id"] for row in self.get(options, **params)["subjects"]},
        )
        student = Student.objects.create(
            institution=self.school,
            admission_number="OPTIONAL-1",
            first_name="Optional",
            birth_date=date(2090, 1, 1),
            admission_date=self.section_date,
        )
        enrollment = StudentEnrollment.objects.create(
            student=student,
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            enrollment_date=self.section_date,
        )
        TeachingAssignment.objects.create(
            user=self.teacher,
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            subject=optional_subject,
        )
        group = self.post(
            "teaching-groups/",
            {
                "session": self.session.pk,
                "section": self.section.pk,
                "subject": optional_subject.pk,
                "name": "Optional group",
                "code": "OPT",
                "enrollments": [enrollment.pk],
            },
        )
        optional_result = self.get(options, **optional_params)
        self.assertIn(
            str(optional_subject.pk), {row["id"] for row in optional_result["subjects"]}
        )
        self.assertEqual(
            [row["id"] for row in optional_result["groups"]], [str(group["id"])]
        )
        optional_payload = {
            **payload,
            "period": second_period["id"],
            "subject": optional_subject.pk,
            "teacher": self.teacher.pk,
        }
        self.post("entries/", optional_payload, 400)
        self.assertEqual(self.get("entries/", version=version["id"])["count"], 1)
        self.post("entries/", {**optional_payload, "group": group["id"]})
        self.assertEqual(self.get("entries/", version=version["id"])["count"], 2)

    def test_recurring_contract_must_cover_all_lesson_dates_inclusive(self):
        from apps.hr import models as hr

        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        department = hr.Department.objects.create(
            institution=self.school, name="Academic", code="ACA"
        )
        designation = hr.Designation.objects.create(
            institution=self.school, name="Teacher", code="TEA"
        )
        employee = hr.Employee.objects.create(
            institution=self.school,
            code="CONTRACT-TEACHER",
            user=self.teacher,
            first_name="Teacher",
            department=department,
            designation=designation,
            employment_type="contract",
            joined_on=self.section_date,
        )
        contract = hr.EmploymentContract.objects.create(
            employee=employee,
            kind="teaching",
            start_date=self.section_date,
            end_date=self.section_date + timedelta(days=28),
            weekdays=list(range(7)),
            created_by=self.operator,
        )
        lesson = self.lesson(version, period, room)
        options = f"plans/{plan['id']}/lesson-options/"
        params = {
            "version": version["id"],
            "weekday": lesson["weekday"],
            "subject": lesson["subject"],
            "period": lesson["period"],
        }

        self.assertIn(
            str(self.teacher.pk),
            {row["id"] for row in self.get(options, **params)["teachers"]},
        )
        self.post("entries/", lesson)

        contract.end_date -= timedelta(days=1)
        contract.save(update_fields=["end_date"])
        self.assertNotIn(
            str(self.teacher.pk),
            {row["id"] for row in self.get(options, **params)["teachers"]},
        )
        self.assertIn("employment or contract", str(self.post("entries/", lesson, 400)))
        self.assertEqual(self.get("entries/", version=version["id"])["count"], 1)

        contract.end_date += timedelta(days=1)
        contract.start_date += timedelta(days=1)
        contract.save(update_fields=["start_date", "end_date"])
        self.assertNotIn(
            str(self.teacher.pk),
            {row["id"] for row in self.get(options, **params)["teachers"]},
        )
        self.assertIn("employment or contract", str(self.post("entries/", lesson, 400)))

        contract.start_date -= timedelta(days=1)
        contract.save(update_fields=["start_date"])
        self.assertIn(
            str(self.teacher.pk),
            {row["id"] for row in self.get(options, **params)["teachers"]},
        )

    def test_published_entry_cannot_be_updated_or_deleted(self):
        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        payload = self.lesson(version, period, room)
        entry = self.post("entries/", payload)
        self.flow(plan, version)
        path = URL + f"entries/{entry['id']}/"
        changed = self.api.patch(path, {"notes": "Retrospective change"}, format="json")
        removed = self.api.delete(path)
        self.assertEqual(changed.status_code, 409, changed.content)
        self.assertEqual(removed.status_code, 409, removed.content)
        self.assertEqual(self.get(f"entries/{entry['id']}/")["notes"], entry["notes"])
        lesson = self.get("daily/", date=self.section_date)["lessons"][0]
        self.assertEqual(lesson["entry"], entry["id"])

    def test_publication_conflicts_revisions_and_teacher_scope(self):
        morning, afternoon, room, period, other_period = self.config()
        plan, version = self.draft(self.section, morning)
        other, other_version = self.draft(self.other, afternoon)
        payload = self.lesson(version, period, room)
        self.post(
            "subject-requirements/",
            {
                "session": self.session.pk,
                "section": self.section.pk,
                "subject": self.subject.pk,
                "minimum": 1,
                "maximum": 2,
            },
        )
        self.post(f"plans/{plan['id']}/submit/", {"version": version["id"]}, 400)
        self.assertEqual(
            self.get(
                "suggestions/",
                **{
                    key: payload[key]
                    for key in ("version", "subject", "teacher", "room", "weekday")
                },
            )[0]["period"],
            period["id"],
        )
        self.post("entries/", payload)
        self.assertEqual(self.get("daily/", date=self.section_date)["lessons"], [])
        self.flow(plan, version)
        self.post("entries/", self.lesson(other_version, other_period, room), 409)
        self.post("entries/", self.lesson(other_version, other_period, room, self.substitute), 409)
        self.assertEqual(
            self.get(f"plans/{plan['id']}/subject-allocation/", version=version["id"])[0][
                "allocated"
            ],
            1,
        )
        boundary = self.section_date + timedelta(days=7)
        revision = self.post(
            f"plans/{plan['id']}/new-version/",
            {
                "effective_start": boundary,
                "effective_end": boundary + timedelta(days=21),
            },
        )
        from apps.audit.models import AuditEvent

        endpoint = f"plans/{plan['id']}/"
        body = {"version": revision["id"]}
        submitted = self.post(endpoint + "submit/", body, 200)
        stale = {**body, "expected_decision_at": "2000-01-01T00:00:00Z"}
        self.api.force_login(self.reviewer)
        self.assertIn("Reload the timetable", str(self.post(endpoint + "approve/", stale, 409)))
        self.assertEqual(
            AuditEvent.objects.filter(
                resource_id=revision["id"], action="TIMETABLE_APPROVED"
            ).count(),
            0,
        )
        approved = self.post(
            endpoint + "approve/", {**body, "expected_decision_at": submitted["submitted_at"]}, 200
        )
        self.api.force_login(self.operator)
        self.assertIn("Reload the timetable", str(self.post(endpoint + "publish/", stale, 409)))
        self.assertEqual(
            AuditEvent.objects.filter(
                resource_id=revision["id"], action="TIMETABLE_PUBLISHED"
            ).count(),
            0,
        )
        self.post(
            endpoint + "publish/", {**body, "expected_decision_at": approved["approved_at"]}, 200
        )
        self.assertEqual(
            self.get("daily/", date=self.section_date)["lessons"][0]["version"], version["id"]
        )
        self.assertEqual(self.get("daily/", date=boundary)["lessons"][0]["version"], revision["id"])
        self.api.force_login(self.teacher)
        self.get("plans/", 403)
        self.get("weekly/", 403, date=boundary, teacher=self.substitute.pk)
        self.assertEqual(len(self.get("weekly/", date=boundary)["lessons"]), 1)
        self.api.force_login(self.substitute)
        self.get("weekly/", 403, date=boundary)
        self.assertTrue(other["id"])

    def test_dated_substitution_calendar_and_license_expiry(self):
        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        entry = self.post("entries/", self.lesson(version, period, room))
        self.flow(plan, version)
        AttendanceHoliday.objects.create(
            institution=self.school,
            date=self.section_date + timedelta(days=7),
            name="Closure",
            kind="closure",
        )
        self.assertEqual(
            self.get("daily/", date=self.section_date + timedelta(days=7))["lessons"], []
        )
        change = {
            "entry": entry["id"],
            "date": self.section_date,
            "kind": "substitute",
            "teacher": self.substitute.pk,
            "reason": "Coverage",
        }
        self.post("exceptions/", change)
        self.post("exceptions/", change, 409)
        effective = self.get("daily/", date=self.section_date)
        self.assertEqual(effective["lessons"][0]["teacher"], str(self.substitute.pk))
        self.assertEqual(effective["lessons"][0]["change"], "substitute")
        self.assertEqual(effective["workload"][0]["minutes"], 60)
        self.assertEqual(effective["attendance"]["missing"], 1)
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=3)):
            self.post("rooms/", {"name": "Expired", "code": "OLD"}, 403)
            self.assertEqual(self.get("daily/", date=self.section_date), effective)
            response = self.api.get(URL + "reports/export/", {"date": self.section_date})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Science", response.content)

    def test_preferences_are_soft_and_teacher_workload_is_enforced(self):
        morning, _, room, period, _ = self.config()
        _, version = self.draft(self.section, morning)
        from_day = self.section_date
        payload = self.lesson(version, period, room)
        day = from_day.weekday()
        availability = {
            "teacher": self.teacher.pk,
            "weekday": day,
            "starts_at": "08:00",
            "ends_at": "14:00",
            "effective_start": from_day,
            "effective_end": from_day + timedelta(days=15),
            "priority": 5,
        }
        self.post("teacher-availability/", {**availability, "preference": "avoid"})
        report = self.post("validate/", payload, 200)
        self.assertEqual(report["preference_score"], -5)
        self.post("entries/", payload)
        policy = self.post(
            "workload-policies/",
            {
                "teacher": self.teacher.pk,
                "effective_start": from_day,
                "effective_end": from_day + timedelta(days=30),
                "weekly_max": 1,
                "hard": True,
            },
        )
        next_lesson = {**payload, "weekday": (day + 1) % 7}
        self.post("entries/", next_lesson, 400)
        result = self.api.patch(
            URL + f"workload-policies/{policy['id']}/", {"hard": False}, format="json"
        )
        self.assertEqual(result.status_code, 200, result.content)
        report = self.post("validate/", next_lesson, 200)
        self.assertIn("weekly teaching limit", report["warnings"])
        self.post("entries/", next_lesson)

    def test_cross_date_change_is_counted_once_and_retains_source(self):
        morning, afternoon, room, period, second_period = self.config()
        plan, version = self.draft(self.section, morning)
        entry = self.post("entries/", self.lesson(version, period, room))
        self.flow(plan, version)
        destination = self.section_date + timedelta(days=1)
        AttendanceHoliday.objects.create(
            institution=self.school,
            date=destination,
            name="Closure",
            kind="closure",
        )
        change = {
            "entry": entry["id"],
            "date": self.section_date,
            "kind": "rescheduled",
            "period": period["id"],
            "destination_date": destination,
            "reason": "Room maintenance",
        }
        self.post("exceptions/", change, 400)
        AttendanceHoliday.objects.filter(institution=self.school, date=destination).delete()
        row = self.post("exceptions/", change)
        self.assertEqual(row["destination_date"], destination.isoformat())
        schedule = self.get("weekly/", date=self.section_date)
        self.assertEqual(
            [event["change"] for event in schedule["lessons"]], ["rescheduled_out", "rescheduled"]
        )
        self.assertEqual(schedule["attendance"]["expected"], 1)
        self.assertEqual(schedule["lessons"][1]["original_date"], self.section_date.isoformat())
        self.assertEqual(self.get("reports/reschedules/", date=self.section_date)["count"], 1)
        _, competitor = self.draft(self.other, afternoon)
        lesson = self.lesson(competitor, second_period, room)
        self.post("entries/", {**lesson, "weekday": destination.weekday()}, 409)

    def test_cross_version_move_keeps_source_and_uses_destination_revision(self):
        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        original = self.post("entries/", self.lesson(version, period, room))
        self.flow(plan, version)
        boundary = self.section_date + timedelta(days=7)
        revision = self.post(
            f"plans/{plan['id']}/new-version/",
            {"effective_start": boundary, "effective_end": boundary + timedelta(days=14)},
        )
        self.flow(plan, revision)
        destination = boundary + timedelta(days=1)
        from apps.attendance.models import AttendanceSession

        payload = {
            "entry": original["id"],
            "date": self.section_date,
            "kind": "rescheduled",
            "period": period["id"],
            "destination_date": destination,
            "reason": "Fixture move",
        }
        existing = AttendanceSession.objects.create(
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            date=destination,
            mode="period",
            subject=self.subject,
            period=period["code"],
            status="finalized",
            late_attended=True,
            excused_policy="exclude",
            recorded_by=self.operator,
        )
        denied = self.post("exceptions/", payload, 409)
        self.assertIn("destination lesson", str(denied))
        self.assertEqual(self.get("exceptions/")["count"], 0)
        existing.refresh_from_db()
        self.assertEqual(existing.status, "finalized")
        existing.delete()
        change = self.post("exceptions/", payload)
        self.assertEqual(change["destination_version"], revision["id"])
        source = self.get("daily/", date=self.section_date)["lessons"][0]
        result = self.get("daily/", date=destination)
        self.assertEqual(result["attendance"]["expected"], 1)
        self.assertEqual(len(result["lessons"]), 1)
        moved = result["lessons"][0]
        self.assertEqual(source["version"], version["id"])
        self.assertEqual(source["change"], "rescheduled_out")
        self.assertEqual(moved["version"], revision["id"])
        self.assertEqual(moved["source_version"], version["id"])
        self.assertEqual(moved["entry"], original["id"])

    def test_parallel_groups_require_disjoint_enrollments_and_snapshotted_rosters(self):
        from apps.admissions.models import StudentEnrollment
        from apps.students.models import Student

        morning, _, room, period, _ = self.config()
        _, version = self.draft(self.section, morning)
        other_room = self.post("rooms/", {"name": "Lab B", "code": "LB", "capacity": 1})
        options = []
        for index in range(2):
            student = Student.objects.create(
                institution=self.school,
                admission_number=f"G-{index}",
                first_name=f"Student {index}",
                birth_date=date(2090, 1, 1),
                admission_date=self.section_date,
            )
            options.append(
                StudentEnrollment.objects.create(
                    student=student,
                    session=self.session,
                    academic_class=self.grade,
                    section=self.section,
                    enrollment_date=self.section_date,
                )
            )
        self.post(
            "teaching-groups/",
            {
                "session": self.session.pk,
                "section": self.section.pk,
                "enrollments": [options[0].pk],
                "name": "Required subject",
                "code": "INVALID",
                "subject": self.subject.pk,
            },
            400,
        )
        self.subject.classsubject_set.update(mandatory=False)
        second = Subject.objects.create(institution=self.school, name="Biology", code="BIO")
        ClassSubject.objects.create(academic_class=self.grade, subject=second, mandatory=False)
        TeachingAssignment.objects.create(
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            subject=second,
            user=self.substitute,
        )
        scope = {
            "session": self.session.pk,
            "section": self.section.pk,
            "enrollments": [options[0].pk],
            "capacity": 1,
        }
        first_group = self.post(
            "teaching-groups/",
            {**scope, "name": "Science option", "code": "S-A", "subject": self.subject.pk},
        )
        second_group = self.post(
            "teaching-groups/",
            {**scope, "name": "Biology option", "code": "B-A", "subject": second.pk},
        )
        first = {**self.lesson(version, period, room), "group": first_group["id"]}
        parallel = {
            **self.lesson(version, period, other_room, self.substitute),
            "subject": second.pk,
            "group": second_group["id"],
        }
        self.post("entries/", first)
        self.post("entries/", parallel, 409)
        reply = self.api.patch(
            URL + f"teaching-groups/{second_group['id']}/",
            {"enrollments": [options[1].pk]},
            format="json",
        )
        self.assertEqual(reply.status_code, 200, reply.content)
        self.post("entries/", parallel)
        plan = self.get("plans/")["results"][0]
        self.flow(plan, version)
        with patch("apps.attendance.service.today", return_value=self.section_date):
            reply = self.api.post(
                "/api/v1/attendance/",
                {
                    "session": self.session.pk,
                    "academic_class": self.grade.pk,
                    "section": self.section.pk,
                    "subject": second.pk,
                    "date": self.section_date,
                    "mode": "period",
                    "period": period["code"],
                    "calendar_override": "Isolated attendance fixture",
                },
                format="json",
            )
        self.assertEqual(reply.status_code, 201, reply.content)
        register = reply.json()
        self.assertEqual(register["schedule_snapshot"]["group"], second_group["id"])
        self.assertEqual([item["student_name"] for item in register["records"]], ["Student 1"])

        old_group_path = f"teaching-groups/{second_group['id']}/"
        frozen = self.api.patch(URL + old_group_path, {"enrollments": []}, format="json")
        self.assertEqual(frozen.status_code, 409, frozen.content)
        boundary = self.section_date + timedelta(days=7)
        options[1].status = "withdrawn"
        options[1].ended_on = boundary
        options[1].save(update_fields=["status", "ended_on"])
        newcomer = Student.objects.create(
            institution=self.school,
            admission_number="GROUP-NEXT",
            first_name="New group member",
            birth_date=date(2090, 1, 1),
            admission_date=boundary,
        )
        enrollment = StudentEnrollment.objects.create(
            student=newcomer,
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            enrollment_date=boundary,
        )
        blocked_successor = self.post(
            "teaching-groups/",
            {
                **scope,
                "name": "Biology option successor",
                "code": "B-B",
                "subject": second.pk,
                "enrollments": [enrollment.pk],
            },
            400,
        )
        self.assertIn("must make a unique set", str(blocked_successor))
        self.assertEqual(self.get(old_group_path)["enrollments"], [str(options[1].pk)])
        revision = self.post(
            f"plans/{plan['id']}/new-version/",
            {"effective_start": boundary, "effective_end": boundary + timedelta(days=21)},
        )
        current = self.post(old_group_path + "successor/", {"version": revision["id"]})
        self.assertEqual(current["predecessor"], second_group["id"])
        self.assertEqual(current["enrollments"], [])
        self.post(old_group_path + "successor/", {"version": revision["id"]}, 400)
        path = URL + f"teaching-groups/{current['id']}/"
        invalid = self.api.patch(path, {"enrollments": [options[1].pk]}, format="json")
        self.assertEqual(invalid.status_code, 400, invalid.content)
        edited = self.api.patch(path, {"enrollments": [enrollment.pk]}, format="json")
        self.assertEqual(edited.status_code, 200, edited.content)
        self.flow(plan, revision)
        self.assertIn(
            second_group["id"],
            [row["group"] for row in self.get("daily/", date=self.section_date)["lessons"]],
        )
        self.assertIn(
            current["id"], [row["group"] for row in self.get("daily/", date=boundary)["lessons"]]
        )
        self.assertEqual(self.get(old_group_path)["enrollments"], [str(options[1].pk)])
        saved_register = self.api.get(f"/api/v1/attendance/{register['id']}/")
        self.assertEqual(saved_register.status_code, 200, saved_register.content)
        self.assertEqual(saved_register.json()["schedule_snapshot"], register["schedule_snapshot"])
        self.assertEqual(saved_register.json()["records"], register["records"])

    def test_reschedule_rejects_exam_leave_and_existing_attendance(self):
        from apps.attendance.models import AttendanceSession
        from apps.examinations import models as exams
        from apps.hr import models as hr

        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        entry = self.post("entries/", self.lesson(version, period, room))
        self.flow(plan, version)
        end = self.section_date + timedelta(days=3)
        exam_type = exams.ExamType.objects.create(institution=self.school, name="Exam", code="EX")
        scheme = exams.GradingScheme.objects.create(
            institution=self.school,
            name="Grades",
            effective_from=self.section_date,
            effective_to=end,
            basis="marks",
        )
        exam = exams.Examination.objects.create(
            institution=self.school,
            session=self.session,
            exam_type=exam_type,
            scheme=scheme,
            name="Exam",
            code="EX",
            status="scheduled",
            start_date=self.section_date,
            end_date=end,
            created_by=self.operator,
        )
        group = exams.ExaminationClass.objects.create(exam=exam, academic_class=self.grade)
        subject = exams.ExaminationSubject.objects.create(
            group=group, subject=self.subject, subject_name="Science"
        )
        exam_day = self.section_date + timedelta(days=1)
        exams.ExamSchedule.objects.create(
            subject=subject, date=exam_day, start_time="09:30", end_time="10:30"
        )
        payload = {
            "entry": entry["id"],
            "date": self.section_date,
            "period": period["id"],
            "kind": "rescheduled",
            "destination_date": exam_day,
            "reason": "Isolated relocation",
        }
        self.post("exceptions/", payload, 409)

        leave_day = self.section_date + timedelta(days=2)
        dept = hr.Department.objects.create(institution=self.school, name="Faculty", code="FAC")
        designation = hr.Designation.objects.create(
            institution=self.school, name="Teacher", code="T"
        )
        employee = hr.Employee.objects.create(
            institution=self.school,
            code="T1",
            user=self.teacher,
            first_name="Teacher",
            department=dept,
            designation=designation,
            employment_type="contract",
            joined_on=self.section_date,
        )
        leave_type = hr.LeaveType.objects.create(institution=self.school, name="Leave", code="L")
        hr.EmployeeLeave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=leave_day,
            end_date=leave_day,
            days=1,
            reason="Fixture approved leave",
            status="approved",
            submitted_by=self.operator,
        )
        self.post("exceptions/", {**payload, "destination_date": leave_day}, 400)
        recurring_day = self.section_date + timedelta(days=7)
        recurring_leave = hr.EmployeeLeave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=recurring_day,
            end_date=recurring_day,
            days=1,
            reason="Fixture recurring lesson leave",
            status="pending",
            submitted_by=self.operator,
        )
        statuses = (
            ("pending", None),
            ("rejected", None),
            ("approved", "approved_leave"),
            ("canceled", None),
        )
        for status, warning in statuses:
            with self.subTest(leave_status=status):
                recurring_leave.status = status
                recurring_leave.save(update_fields=["status"])
                scheduled = self.get("daily/", date=recurring_day)["lessons"]
                self.assertEqual(len(scheduled), 1)
                self.assertEqual(scheduled[0]["entry"], entry["id"])
                self.assertEqual(scheduled[0]["version"], version["id"])
                self.assertEqual(scheduled[0]["warning"], warning)
        self.assertIsNone(self.get("daily/", date=self.section_date)["lessons"][0]["warning"])
        register = AttendanceSession.objects.create(
            session=self.session,
            academic_class=self.grade,
            section=self.section,
            date=self.section_date,
            mode="period",
            subject=self.subject,
            period=period["code"],
            status="finalized",
            late_attended=True,
            excused_policy="exclude",
            recorded_by=self.operator,
            schedule_snapshot={"entry": entry["id"]},
        )
        self.post("exceptions/", {**payload, "destination_date": end}, 409)
        register.refresh_from_db()
        self.assertEqual(register.status, "finalized")
        self.assertEqual(register.schedule_snapshot, {"entry": entry["id"]})
        self.assertEqual(self.get("exceptions/")["count"], 0)

    def test_five_role_scope_and_permission_denials(self):
        from apps.audit.models import AuditEvent

        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        payload = self.lesson(version, period, room)
        result = self.post("entries/", payload)
        endpoint = f"plans/{plan['id']}/"
        body = {"version": version["id"]}
        self.post(endpoint + "submit/", body, 200)
        hr = User.objects.create_user(username="hr-officer")
        hr.user_permissions.set(permission_rows(["accounts.view_staff"]))
        for account in (self.teacher, hr, self.substitute):
            with self.subTest(role=account.username):
                self.api.force_login(account)
                error = self.post(endpoint + "approve/", body, 403)
                self.assertIn("do not have permission", str(error))
                self.assertNotIn(result["id"], str(error))
                self.get(endpoint + "versions/", 403)
        self.api.force_login(self.reviewer)
        self.post(endpoint + "approve/", body, 200)
        for account in (self.reviewer, self.teacher, hr, self.substitute):
            self.api.force_login(account)
            self.post(endpoint + "publish/", body, 403)
        self.api.force_login(self.operator)
        self.assertEqual(self.get(endpoint + "versions/")[0]["status"], "approved")
        self.post(endpoint + "publish/", body, 200)
        self.assertEqual(
            AuditEvent.objects.filter(
                resource_id=version["id"],
                action="TIMETABLE_PUBLISHED",
            ).count(),
            1,
        )

    def test_capacity_enforcement_requires_its_settings_grant(self):
        authorized = User.objects.create_user(username="capacity-settings-officer")
        authorized.user_permissions.set(
            permission_rows(["accounts.change_timetable_settings"])
        )
        self.api.force_login(authorized)
        allowed = self.api.patch(
            URL + "settings/", {"enforce_capacity": False}, format="json"
        )
        self.assertEqual(allowed.status_code, 200, allowed.content)

        hr = User.objects.create_user(username="capacity-hr")
        hr.user_permissions.set(permission_rows(["accounts.view_staff"]))
        payroll = User.objects.create_user(username="capacity-payroll")
        payroll.user_permissions.set(permission_rows(["accounts.view_payroll"]))
        restricted = User.objects.create_user(username="capacity-restricted")
        roles = (
            ("administrator", self.operator, True),
            ("teacher", self.teacher, False),
            ("hr", hr, False),
            ("payroll", payroll, False),
            ("restricted", restricted, False),
        )
        for role, account, may_override in roles:
            with self.subTest(role=role):
                self.api.force_login(account)
                response = self.api.patch(
                    URL + "settings/",
                    {"enforce_capacity": not may_override},
                    format="json",
                )
                self.assertEqual(response.status_code, 200 if may_override else 403)

        self.api.force_login(self.operator)
        current = self.api.get(URL + "settings/")
        self.assertEqual(current.status_code, 200, current.content)
        self.assertFalse(current.json()["enforce_capacity"])

    def test_csv_export_escapes_formulas_and_requires_export_grant(self):
        self.subject.name = '  =HYPERLINK("example.invalid","Été")'
        self.subject.save(update_fields=["name"])
        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        self.post("entries/", self.lesson(version, period, room))
        self.flow(plan, version)
        path = "reports/class/"
        params = {
            "date": self.section_date,
            "through": self.section_date,
            "session": self.session.pk,
        }
        report = self.get(path, **params)
        self.assertEqual(report["results"][0]["subject_name"], self.subject.name)
        csv = self.api.get(URL + path, {**params, "format_type": "csv"})
        self.assertEqual(csv.status_code, 200)
        self.assertTrue(csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("'" + self.subject.name.replace('"', '""'), csv.content.decode("utf-8-sig"))
        reader = User.objects.create_user(username="report-reader")
        reader.user_permissions.set(permission_rows(["accounts.view_timetable"]))
        self.api.force_login(reader)
        self.get(path, **params)
        self.get(path, 403, **params, format_type="csv")

    def test_all_report_routes_reconcile_and_export_after_license_expiry(self):
        from csv import DictReader
        from io import StringIO

        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        entry = self.post("entries/", self.lesson(version, period, room))
        self.post(
            "subject-requirements/",
            {
                "session": self.session.pk,
                "section": self.section.pk,
                "subject": self.subject.pk,
                "minimum": 1,
                "maximum": 2,
            },
        )
        self.flow(plan, version)
        start = self.section_date
        self.post(
            "exceptions/",
            {
                "entry": entry["id"],
                "date": start + timedelta(days=7),
                "kind": "substitute",
                "teacher": self.substitute.pk,
                "reason": "Coverage",
            },
        )
        self.post(
            "exceptions/",
            {
                "entry": entry["id"],
                "date": start + timedelta(days=14),
                "kind": "cancelled",
                "reason": "Cancellation",
            },
        )
        self.post(
            "exceptions/",
            {
                "entry": entry["id"],
                "date": start + timedelta(days=21),
                "kind": "rescheduled",
                "destination_date": start + timedelta(days=22),
                "period": period["id"],
                "reason": "Move",
            },
        )
        expected = {
            "class": (4, "subject_name", "Science"),
            "section": (4, "section_name", self.section.name),
            "teacher-weekly": (4, "teacher_name", self.teacher.username),
            "teacher-daily": (4, "date", str(start)),
            "rooms": (1, "minutes", 180),
            "workload": (2, "minutes", 120),
            "allocations": (1, "allocated", 1),
            "unassigned": (0, None, None),
            "conflicts": (0, None, None),
            "substitutions": (1, "original_teacher", self.teacher.username),
            "cancellations": (1, "change", "cancelled"),
            "reschedules": (1, "destination_date", str(start + timedelta(days=22))),
            "revisions": (1, "status", "published"),
            "attendance": (1, "expected", 3),
        }
        # Source plus destination are distinct in schedule views; canceled and moved-away slots
        # do not contribute to workload, room usage or the expected attendance tally.
        for kind in ("class", "section", "teacher-weekly", "teacher-daily"):
            count, key, value = expected[kind]
            expected[kind] = (count + 1, key, value)
        params = {"date": start, "through": start + timedelta(days=22), "session": self.session.pk}
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=3)):
            for kind, (count, key, value) in expected.items():
                with self.subTest(report=kind):
                    endpoint = f"reports/{kind}/"
                    page = self.get(endpoint, **params, limit=1)
                    self.assertEqual(page["count"], count)
                    self.assertEqual(bool(page["next"]), count > 1)
                    if key:
                        self.assertEqual(page["results"][0][key], value)
                    result = self.api.get(URL + endpoint, {**params, "format_type": "csv"})
                    self.assertEqual(result.status_code, 200)
                    self.assertIn("text/csv", result["Content-Type"])
                    rows = list(DictReader(StringIO(result.content.decode("utf-8-sig"))))
                    self.assertEqual(len(rows), count)
                    if key:
                        self.assertEqual(rows[0][key], str(value))
                    self.api.force_login(self.reviewer)
                    self.get(endpoint, 403, **params)
                    self.api.force_login(self.operator)


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class TimetableConcurrencyTests(TransactionTestCase):
    post = TimetableTests.post
    get = TimetableTests.get
    config = TimetableTests.config
    draft = TimetableTests.draft
    lesson = TimetableTests.lesson

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Timetable write serialization requires PostgreSQL.")
        with transaction.atomic():
            TimetableTests.setUpTestData.__func__(self)
        TimetableTests.setUp(self)

    def assert_publication_race(self, contenders, expected_conflict):
        from apps.audit.models import AuditEvent

        for plan, version, slot, room, teacher in contenders:
            self.post("entries/", self.lesson(version, slot, room, teacher))
            body = {"version": version["id"]}
            self.post(f"plans/{plan['id']}/submit/", body, 200)
            self.api.force_login(self.reviewer)
            self.post(f"plans/{plan['id']}/approve/", body, 200)
            self.api.force_login(self.operator)

        barrier = Barrier(2)

        def publish(candidate):
            plan, version, *_ = candidate
            client = APIClient()
            client.force_login(self.operator)
            try:
                barrier.wait(10)
                return client.post(
                    URL + f"plans/{plan['id']}/publish/",
                    {"version": version["id"]},
                    format="json",
                )
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(publish, contenders))
        self.assertEqual(sorted(result.status_code for result in responses), [200, 409])
        denial = next(result for result in responses if result.status_code == 409)
        self.assertIn(expected_conflict, str(denial.json()))
        self.assertEqual(len(self.get("daily/", date=self.section_date)["lessons"]), 1)
        for (plan, version, *_), result in zip(contenders, responses, strict=True):
            published = result.status_code == 200
            saved = self.get(f"plans/{plan['id']}/versions/")[0]
            self.assertEqual(saved["status"], "published" if published else "approved")
            self.assertEqual(
                AuditEvent.objects.filter(
                    resource_id=version["id"],
                    action="TIMETABLE_PUBLISHED",
                ).count(),
                int(published),
            )

    def test_two_concurrent_publications_cannot_reserve_the_same_teacher(self):
        morning, afternoon, room, period, other_period = self.config()
        first, current = self.draft(self.section, morning)
        second, concurrent = self.draft(self.other, afternoon)
        other_room = self.post("rooms/", {"name": "Studio", "code": "STUDIO", "capacity": 25})
        self.assert_publication_race(
            [
                (first, current, period, room, self.teacher),
                (second, concurrent, other_period, other_room, self.teacher),
            ],
            "teacher",
        )

    def test_two_concurrent_publications_cannot_reserve_the_same_room(self):
        morning, afternoon, room, period, other_period = self.config()
        first, current = self.draft(self.section, morning)
        second, concurrent = self.draft(self.other, afternoon)
        self.assert_publication_race(
            [
                (first, current, period, room, self.teacher),
                (second, concurrent, other_period, room, self.substitute),
            ],
            "room",
        )

    def test_two_concurrent_publications_cannot_reserve_the_same_section(self):
        morning, afternoon, room, period, other_period = self.config()
        first, current = self.draft(self.section, morning)
        other_session = AcademicSession.objects.create(
            institution=self.school,
            code="T2",
            name="Overlapping term",
            start_date=self.session.start_date,
            end_date=self.session.end_date,
        )
        TeachingAssignment.objects.create(
            session=other_session,
            academic_class=self.grade,
            subject=self.subject,
            user=self.substitute,
        )
        second, concurrent = self.draft(self.section, afternoon, session=other_session)
        other_room = self.post("rooms/", {"name": "Studio", "code": "STUDIO", "capacity": 25})
        self.assert_publication_race(
            [
                (first, current, period, room, self.teacher),
                (second, concurrent, other_period, other_room, self.substitute),
            ],
            "section",
        )

    def test_concurrent_reschedules_cannot_claim_one_destination(self):
        from apps.audit.models import AuditEvent

        morning, _, room, period, _ = self.config()
        plan, version = self.draft(self.section, morning)
        entry = self.post("entries/", self.lesson(version, period, room))
        TimetableTests.flow(self, plan, version)
        first = self.section_date
        later = first + timedelta(days=7)
        destination = later + timedelta(days=1)
        revision = self.post(
            f"plans/{plan['id']}/new-version/",
            {"effective_start": destination, "effective_end": destination + timedelta(days=14)},
        )
        TimetableTests.flow(self, plan, revision)
        barrier = Barrier(2)

        def relocate(source):
            client = APIClient()
            client.force_login(self.operator)
            payload = {
                "entry": entry["id"],
                "date": source,
                "kind": "rescheduled",
                "destination_date": destination,
                "period": period["id"],
                "reason": "Relocate fixture lesson",
            }
            try:
                barrier.wait(10)
                return client.post(URL + "exceptions/", payload, format="json")
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(relocate, (first, later)))
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        denial = next(response for response in responses if response.status_code == 409)
        self.assertIn("section conflict", str(denial.json()))
        changes = self.get("exceptions/")
        self.assertEqual(changes["count"], 1)
        accepted = changes["results"][0]
        self.assertEqual(accepted["destination_date"], destination.isoformat())
        self.assertEqual(accepted["destination_version"], revision["id"])
        delivered = self.get("daily/", date=destination)["lessons"]
        self.assertEqual([lesson["exception"] for lesson in delivered], [accepted["id"]])
        self.assertEqual(AuditEvent.objects.filter(action="TIMETABLE_EXCEPTION_CREATED").count(), 1)
