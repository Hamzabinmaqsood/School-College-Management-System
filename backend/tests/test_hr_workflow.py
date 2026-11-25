from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.access import permission_rows, seed_roles
from apps.accounts.models import Institution, User
from apps.hr.models import PayrollEntry
from apps.hr.payroll import payable
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from apps.students.models import Student
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

API = "/api/v1/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class HRWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_roles()
        cls.school = Institution.objects.create(
            code="trial", name="Trial Academy", institution_type="academy"
        )
        cls.identity = InstallationIdentity.objects.create(institution=cls.school)
        cls.operator = User.objects.create_superuser(username="academic-admin")
        cls.reader = User.objects.create_user(username="staff-user")
        cls.salary_reviewer = User.objects.create_superuser(username="salary-reviewer")
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
                "features": ["academics", "admissions", "hr", "payroll", "students"],
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
        activate = path == "salary-structures" and payload.get("active") and status == 201
        if activate:
            payload = {**payload, "active": False}
        response = self.write("post", "hr/" + path + "/", payload)
        self.assertEqual(response.status_code, status, response.content)
        result = response.json()
        if activate:
            endpoint = f"salary-structures/{result['id']}"
            submitted = self.make(endpoint + "/submit", {})
            self.client.force_login(self.salary_reviewer)
            try:
                self.make(endpoint + "/approve", {"approval": submitted["id"]}, 200)
            finally:
                self.client.force_login(self.operator)
            self.make(endpoint + "/activate", {"approval": submitted["id"]}, 200)
        return result

    def get_hr(self, path, status=200):
        result = self.client.get(API + "hr/" + path)
        self.assertEqual(result.status_code, status, result.content)
        return result

    def employee(self):
        department = self.make("departments", {"name": "Science", "code": "SCI"})
        self.make("departments", {"name": "Duplicate", "code": "sci"}, 409)
        role = self.make("designations", {"name": "Teacher", "code": "TEACH", "teaching": True})
        person = self.make(
            "employees",
            {
                "code": "E1",
                "first_name": "=استاد",
                "department": department["id"],
                "designation": role["id"],
                "employment_type": "contract",
                "joined_on": self.day,
            },
        )
        self.assertIsNone(person["user"])
        return person

    def test_teaching_assignment_history_is_scoped(self):
        from apps.hr.models import Employee

        person = self.employee()
        Employee.objects.filter(pk=person["id"]).update(user=self.reader)
        route = f"employees/{person['id']}"
        assignment = self.make(
            route + "/assignments",
            {
                "session": self.term.pk,
                "academic_class": self.grade.pk,
                "section": self.room.pk,
                "effective_start": self.day,
                "effective_end": self.day,
            },
        )
        extended = self.write(
            "patch",
            f"hr/{route}/assignment-dates/",
            {
                "assignment": assignment["id"],
                "effective_end": self.day + timedelta(days=5),
            },
        )
        self.assertEqual(extended.status_code, 200)
        self.make(route + "/deactivate-assignment", {"assignment": assignment["id"]}, 200)
        path = f"{route}/assignment-history/?assignment={assignment['id']}"
        events = self.get_hr(path).json()["results"]
        self.assertEqual(
            [row["action"] for row in events],
            [
                "HR_TEACHING_ASSIGNMENT_DEACTIVATED",
                "HR_TEACHING_ASSIGNMENT_DATES_UPDATED",
                "HR_TEACHING_ASSIGNMENT_CREATED",
            ],
        )
        self.assertEqual(events[1]["sanitized_metadata"]["before"]["effective_end"], str(self.day))
        self.get_hr(f"{route}/assignment-history/?assignment={uuid4()}", 404)
        self.client.force_login(self.reader)
        self.get_hr(path, 403)

    def test_overnight_attendance_calendar_and_paid_hours(self):
        from apps.hr.models import Employee
        from apps.hr.payroll import wage_units

        employee = self.employee()["id"]
        self.make(
            "contracts",
            {
                "employee": employee,
                "kind": "Night shift",
                "start_date": self.day,
                "end_date": self.day,
                "weekdays": [self.day.weekday()],
                "shift_start": "22:00",
                "shift_end": "06:00",
                "break_minutes": 30,
                "late_tolerance_minutes": 10,
                "early_tolerance_minutes": 5,
            },
        )
        self.make(
            "attendance",
            {
                "employee": employee,
                "date": self.day,
                "status": "present",
                "check_in": "22:15",
                "check_out": "05:50",
            },
        )
        month = self.day.strftime("%Y-%m")
        calendar = self.get_hr(f"attendance/calendar/?employee={employee}&month={month}").json()
        day = calendar["days"][self.day.day - 1]
        self.assertEqual(day["status"], "present")
        self.assertTrue(day["overnight"])
        self.assertEqual(day["late_minutes"], 15)
        self.assertEqual(day["early_minutes"], 10)
        actual = wage_units(Employee.objects.get(pk=employee), self.day, self.day, "hourly")
        self.assertEqual(actual, Decimal(425) / 60)

    def test_department_schedule_and_contract_leave_entitlement(self):
        person = self.employee()
        template = {
            "weekdays": [self.day.weekday()],
            "shift_start": "22:00",
            "shift_end": "06:00",
            "break_minutes": 30,
        }
        path = f"hr/departments/{person['department']}/"
        response = self.write("patch", path, {"default_schedule": template})
        self.assertEqual(response.status_code, 200, response.content)
        contract = self.make(
            "contracts",
            {
                "employee": person["id"],
                "kind": "Department overnight",
                "start_date": self.day,
                "end_date": self.day,
                "use_department_schedule": True,
                "leave_entitlements": {"annual": "18.50"},
            },
        )
        self.assertEqual(contract["break_minutes"], 30)
        self.assertEqual(contract["shift_start"], "22:00:00")
        changed = self.write("patch", path, {"default_schedule": {**template, "break_minutes": 45}})
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(self.get_hr(f"contracts/{contract['id']}/").json()["break_minutes"], 30)
        policy = self.make(
            "leave-types",
            {
                "name": "Annual",
                "code": "ANNUAL",
                "annual_days": 12,
                "accrual_mode": "fixed",
            },
        )
        result = self.make(
            "leave-balances/apply",
            {
                "employee": person["id"],
                "leave_type": policy["id"],
                "through": self.day,
            },
            200,
        )
        self.assertEqual(Decimal(str(result["balance"])), Decimal("18.50"))

    def test_leave_accrual_approval_and_reversal(self):
        employee = self.employee()["id"]
        policy = self.make(
            "leave-types",
            {
                "name": "Accrual",
                "code": "ACCRUAL",
                "annual_days": 12,
                "accrual_mode": "annual",
                "prorate": False,
            },
        )
        params = {"employee": employee, "leave_type": policy["id"], "through": self.day}
        self.assertEqual(self.make("leave-balances/apply", params, 200)["posted"], 1)
        self.assertEqual(self.make("leave-balances/apply", params, 200)["posted"], 0)
        leave = self.make(
            "leaves",
            {
                "employee": employee,
                "leave_type": policy["id"],
                "start_date": self.day,
                "end_date": self.day,
                "reason": "Test",
            },
        )
        self.make(f"leaves/{leave['id']}/approve", {}, 200)
        self.make(f"leaves/{leave['id']}/cancel", {}, 200)
        rows = self.get_hr(
            f"leave-balances/?employee={employee}&leave_type={policy['id']}&through={self.day}"
        ).json()
        self.assertEqual(Decimal(str(rows["balance"])), 12)
        self.assertEqual(
            [row["event"] for row in rows["ledger"]],
            [
                "accrual",
                "consumption",
                "reversal",
            ],
        )

    def test_leave_policy_revision_preserves_posted_terms(self):
        from apps.hr.models import Employee

        person = self.employee()["id"]
        Employee.objects.filter(pk=person).update(joined_on=date(2025, 1, 1))
        policy = self.make(
            "leave-types",
            {
                "name": "Versioned",
                "code": "VERSIONED",
                "annual_days": 12,
                "accrual_mode": "monthly",
            },
        )["id"]
        endpoint = f"leave-types/{policy}/versions"
        params = {"employee": person, "leave_type": policy}
        ledger_url = f"leave-balances/?employee={person}&leave_type={policy}"
        revision = {"effective_start": "2025-07-01", "terms": {"annual_days": 24, "carry_limit": 4}}
        with (
            patch("apps.hr.api.today", return_value=date(2025, 6, 30)),
            patch("apps.hr.leave_balance.today", return_value=date(2025, 6, 30)),
        ):
            initial = self.get_hr(endpoint + "/").json()[0]
            before = {**params, "through": "2025-06-30"}
            self.assertEqual(self.make("leave-balances/apply", before, 200)["posted"], 6)
            leave = self.make(
                "leaves",
                {
                    **params,
                    "start_date": "2025-06-30",
                    "end_date": "2025-06-30",
                    "reason": "Historical consumption fixture",
                },
            )
            self.make(f"leaves/{leave['id']}/approve", {}, 200)
            original = self.get_hr(ledger_url + "&through=2025-06-30").json()
            self.assertEqual(Decimal(str(original["balance"])), 5)
            self.make(endpoint, {**revision, "effective_start": "2025-06-30"}, 400)
            self.make(endpoint, {**revision, "effective_start": "2025-07-02"}, 400)
            draft = self.make(endpoint, {**revision, "draft": True})[0]
            self.assertEqual(draft["status"], "draft")
            published = self.make(endpoint, revision, 200)[0]
            self.assertEqual(published["status"], "scheduled")
            self.make(endpoint, revision, 409)
            changed = self.write("patch", f"hr/leave-types/{policy}/", {"annual_days": 30})
            self.assertEqual(changed.status_code, 409)
            self.make("leave-balances/apply", {**params, "through": "2025-07-31"}, 400)
            boundary = self.get_hr(ledger_url + "&through=2025-07-01&preview=1").json()
            self.assertEqual(boundary["policy_version"], published["id"])
            self.assertEqual(boundary["preview"], [])
            projection = self.get_hr(ledger_url + "&through=2025-07-31&preview=1").json()["preview"]
            self.assertEqual(len(projection), 1)
            self.assertEqual(projection[0]["policy_version_id"], published["id"])
            self.assertEqual(Decimal(str(projection[0]["amount"])), 2)

        with (
            patch("apps.hr.api.today", return_value=date(2025, 7, 31)),
            patch("apps.hr.leave_balance.today", return_value=date(2025, 7, 31)),
        ):
            july = {**params, "through": "2025-07-31"}
            self.assertEqual(self.make("leave-balances/apply", july, 200)["posted"], 1)
            self.assertEqual(self.make("leave-balances/apply", july, 200)["posted"], 0)
            after = self.get_hr(ledger_url + "&through=2025-07-31").json()
            self.assertEqual(after["ledger"][:-1], original["ledger"])
            self.assertEqual(after["ledger"][-1]["policy_version"], published["id"])
            self.assertEqual(after["ledger"][-1]["calculation"]["period_start"], "2025-07-01")
            self.assertEqual(Decimal(str(after["balance"])), 7)
            self.make(f"leave-types/{policy}/withdraw-version", {"version": published["id"]}, 409)
            self.make(f"leaves/{leave['id']}/cancel", {}, 200)
            reversed_ledger = self.get_hr(ledger_url + "&through=2025-07-31").json()
            self.assertEqual(Decimal(str(reversed_ledger["balance"])), 8)
            events = {entry["event"]: entry for entry in reversed_ledger["ledger"]}
            self.assertEqual(events["reversal"]["policy_version"], initial["id"])
            self.assertEqual(events["consumption"]["policy_version"], initial["id"])
            from apps.audit.models import AuditEvent

            self.assertEqual(
                AuditEvent.objects.filter(
                    action="HR_LEAVE_VERSION_SAVED",
                    resource_id=published["id"],
                ).count(),
                2,
            )

    def test_version_history_read_only_when_license_expires(self):
        person = self.employee()["id"]
        policy = self.make(
            "leave-types",
            {"name": "Paid", "code": "PAID", "accrual_mode": "fixed", "annual_days": 12},
        )["id"]
        endpoint = f"leave-types/{policy}/versions"
        params = {"employee": person, "leave_type": policy, "through": self.day}
        self.make("leave-balances/apply", params, 200)
        ledger_url = f"leave-balances/?employee={person}&leave_type={policy}&through={self.day}"
        ledger = self.get_hr(ledger_url).json()
        versions = self.get_hr(endpoint + "/").json()

        # Advance only the verifier clock, using the real signed and activated test license.
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=3)):
            result = self.client.get(API + "license/status/")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["status"], "EXPIRED")
            self.assertEqual(self.get_hr(endpoint + "/").json(), versions)
            self.assertEqual(self.get_hr(ledger_url).json(), ledger)
            denied = self.make(endpoint, {"effective_start": "2999-01-01", "terms": {}}, 403)
            self.assertIn("current subscription", str(denied))
            denied = self.make("leave-balances/apply", params, 403)
            self.assertIn("current subscription", str(denied))
            self.assertEqual(self.get_hr(endpoint + "/").json(), versions)
            self.assertEqual(self.get_hr(ledger_url).json(), ledger)

        self.reader.user_permissions.add(*permission_rows(["accounts.view_staff_leave"]))
        self.client.force_login(self.reader)
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=3)):
            self.assertEqual(self.get_hr(endpoint + "/").json(), versions)
            self.assertEqual(self.get_hr(ledger_url).json(), ledger)
            denied = self.make(endpoint, {"effective_start": "2999-01-01", "terms": {}}, 403)
            self.assertIn("do not have permission", str(denied))

    def test_scheduled_carry_revision_uses_january_terms_and_rolls_back_on_failure(self):
        from apps.hr.models import Employee

        employee_id = self.employee()["id"]
        Employee.objects.filter(pk=employee_id).update(joined_on=date(2024, 1, 1))
        policy = self.make(
            "leave-types",
            {
                "name": "Carry revision",
                "code": "CARRY-VERSION",
                "accrual_mode": "manual",
                "carry_limit": "2.00",
                "carry_expiry_days": 30,
            },
        )["id"]
        params = {"employee": employee_id, "leave_type": policy}
        ledger = f"leave-balances/?employee={employee_id}&leave_type={policy}&through="
        endpoint = f"leave-types/{policy}/versions"
        with patch("apps.hr.leave_balance.today", return_value=date(2024, 12, 31)):
            self.make(
                "leave-balances/adjust",
                {
                    **params,
                    "through": "2024-12-31",
                    "kind": "opening",
                    "amount": "7.00",
                    "reason": "Isolated opening",
                    "key": uuid4(),
                },
            )
            original = self.get_hr(ledger + "2024-12-31").json()
            [revision, initial] = self.make(
                endpoint,
                {
                    "effective_start": "2025-01-01",
                    "terms": {"carry_limit": "5.00", "carry_expiry_days": 10},
                },
            )
        with patch("apps.hr.leave_balance.today", return_value=date(2025, 1, 31)):
            january = {**params, "through": "2025-01-05"}
            projected = self.get_hr(ledger + "2025-01-05").json()["preview"]
            self.assertEqual(len(projected), 1)
            self.assertEqual(projected[0]["policy_version_id"], revision["id"])
            self.assertEqual(Decimal(str(projected[0]["amount"])), 5)
            with patch("apps.hr.leave_balance.audit", side_effect=RuntimeError("audit probe")):
                self.make("leave-balances/apply", january, 500)
            self.assertEqual(self.get_hr(ledger + "2025-01-05").json()["ledger"], [])
            self.assertEqual(self.make("leave-balances/apply", january, 200)["posted"], 1)
            self.assertEqual(
                self.make("leave-balances/apply", {**params, "through": "2025-01-11"}, 200)[
                    "posted"
                ],
                1,
            )
            posted = self.get_hr(ledger + "2025-01-31").json()
            self.assertEqual(Decimal(str(posted["balance"])), 0)
            self.assertEqual(
                [(row["event"], row["amount"], row["policy_version"]) for row in posted["ledger"]],
                [("carry", "5.00", revision["id"]), ("expiration", "-5.00", revision["id"])],
            )
            self.assertEqual(self.get_hr(ledger + "2024-12-31").json(), original)
            self.assertEqual(original["ledger"][0]["policy_version"], initial["id"])

    def test_monthly_accrual_prorates_and_reverts_after_contract_expiry(self):
        from apps.hr.models import Employee

        employee = self.employee()["id"]
        year = self.day.year - 1
        joined, april_end, may_end = date(year, 4, 16), date(year, 4, 30), date(year, 5, 31)
        Employee.objects.filter(pk=employee).update(joined_on=joined)
        self.make(
            "contracts",
            {
                "employee": employee,
                "kind": "April contract",
                "start_date": joined,
                "end_date": april_end,
                "leave_entitlements": {"MONTH": "48", "ZERO": "0"},
            },
        )
        policy = self.make(
            "leave-types",
            {
                "name": "Monthly",
                "code": "MONTH",
                "annual_days": 12,
                "accrual_mode": "monthly",
                "prorate": True,
            },
        )
        zero_policy = self.make(
            "leave-types",
            {
                "name": "Zero",
                "code": "ZERO",
                "annual_days": 12,
                "accrual_mode": "monthly",
                "prorate": True,
            },
        )
        params = {"employee": employee, "leave_type": policy["id"]}
        april = self.make("leave-balances/apply", {**params, "through": april_end}, 200)
        self.assertEqual(Decimal(str(april["balance"])), Decimal("2.00"))
        zero = self.make(
            "leave-balances/apply",
            {
                "employee": employee,
                "leave_type": zero_policy["id"],
                "through": april_end,
            },
            200,
        )
        self.assertEqual(zero["posted"], 0)
        may = self.make("leave-balances/apply", {**params, "through": may_end}, 200)
        self.assertEqual(Decimal(str(may["balance"])), Decimal("3.00"))
        self.assertEqual(may["posted"], 1)

    def test_staff_calendar_month_boundary_and_working_override(self):
        from apps.attendance.models import AttendanceHoliday
        from apps.hr.api import today
        from apps.hr.calendar import month_rows
        from apps.hr.models import Employee

        person = Employee.objects.get(pk=self.employee()["id"])
        month = date(self.day.year - 1, 2, 1)
        person.joined_on = month
        person.save(update_fields=["joined_on"])
        self.make(
            "contracts",
            {
                "employee": person.pk,
                "kind": "Schedule",
                "start_date": month,
                "end_date": month + timedelta(days=10),
                "weekdays": [(month.weekday() + 1) % 7],
            },
        )
        rows = list(month_rows(person, month, self.school))
        self.assertEqual(rows[0]["status"], "non_working")
        AttendanceHoliday.objects.create(
            institution=self.school, date=month, name="Working exception", kind="working"
        )
        rows = list(month_rows(person, month, self.school))
        self.assertEqual(rows[0]["status"], "unrecorded")
        self.assertEqual(len({row["date"] for row in rows}), len(rows))
        self.school.timezone = "Asia/Karachi"
        self.school.save(update_fields=["timezone"])
        with patch("django.utils.timezone.now", return_value=datetime(2025, 1, 31, 19, tzinfo=UTC)):
            self.assertEqual(today(), date(2025, 2, 1))

    def test_leave_carry_limit_and_expiration(self):
        from apps.hr.models import Employee

        employee = self.employee()["id"]
        year = self.day.year - 1
        joined = date(year - 1, 1, 1)
        Employee.objects.filter(pk=employee).update(joined_on=joined)
        policy = self.make(
            "leave-types",
            {
                "name": "Manual",
                "code": "MANUAL",
                "annual_days": 0,
                "accrual_mode": "manual",
                "carry_limit": "3",
                "carry_expiry_days": 30,
            },
        )
        data = {"employee": employee, "leave_type": policy["id"]}
        entry = {
            **data,
            "through": date(year - 1, 12, 31),
            "kind": "opening",
            "amount": "5",
            "reason": "Opening entitlement",
            "key": uuid4(),
        }
        self.make("leave-balances/adjust", entry)
        self.make("leave-balances/adjust", entry, 200)
        carried = self.make("leave-balances/apply", {**data, "through": date(year, 1, 5)}, 200)
        self.assertEqual(Decimal(str(carried["balance"])), 3)
        expired = self.make("leave-balances/apply", {**data, "through": date(year, 2, 1)}, 200)
        self.assertEqual(Decimal(str(expired["balance"])), 0)
        self.assertEqual(expired["posted"], 1)

    def test_overtime_is_included_only_after_approval(self):
        employee = self.employee()["id"]
        recorded = self.make(
            "attendance", {"employee": employee, "date": self.day, "status": "present"}
        )
        bounds = {"start_date": self.day, "end_date": self.day}
        policy = self.make(
            "overtime-policies",
            dict(
                bounds,
                name="After hours",
                rate="100",
                regular_multiplier="1.50",
                maximum_hours="4",
                separate_approver=False,
            ),
        )
        overtime = self.make(
            "overtime",
            {
                "attendance": recorded["id"],
                "policy": policy["id"],
                "requested_hours": "2",
            },
        )
        structure = self.make(
            "salary-structures",
            {
                "name": "Basic",
                "code": "SAL",
                "basis": "monthly",
                "basic": "1000",
                "components": [],
                "active": True,
            },
        )
        self.make("salary-assignments", dict(bounds, employee=employee, structure=structure["id"]))
        period = self.make("periods", dict(bounds, name="Current"))
        query = {"period": period["id"]}
        before = self.make("payroll/preview", query, 200)["entries"][0]
        self.assertEqual(before["gross"], "1000.00")
        decision = self.make(
            f"overtime/{overtime['id']}/decision",
            {
                "status": "approved",
                "hours": "2",
                "reason": "Verified attendance",
            },
            200,
        )
        for _ in range(2):
            result = self.make("payroll/preview", query, 200)["entries"][0]
            self.assertEqual(result["items"], [decision["snapshot"]])
            self.assertEqual(result["gross"], "1300.00")

    def test_salary_structure_approval_requires_current_revision_and_distinct_actor(self):
        from apps.audit.models import AuditEvent

        draft = {
            "name": "Dated structure",
            "code": "APPROVAL",
            "basis": "monthly",
            "basic": "1025.25",
            "effective_from": "2099-01-01",
            "effective_through": "2099-12-31",
            "components": [{"label": "Allowance", "kind": "earning", "amount": "17.25"}],
        }
        self.make("salary-structures", {**draft, "active": True}, 400)
        self.make("salary-structures", {**draft, "effective_through": "2098-12-31"}, 400)
        row = self.make("salary-structures", draft)
        path = f"salary-structures/{row['id']}"
        first = self.make(path + "/submit", {})
        self.assertEqual(self.make(path + "/submit", {}, 200)["id"], first["id"])
        original = {"approval": first["id"]}
        self.make(path + "/activate", original, 409)
        self.make(path + "/approve", original, 403)
        self.reader.user_permissions.add(*permission_rows(["accounts.manage_salary_setup"]))
        self.client.force_login(self.reader)
        self.make(path + "/approve", original, 403)
        self.make(path + "/reject", original, 403)
        self.make(path + "/activate", original, 403)
        self.get_hr(path + "/approvals/", 403)

        self.client.force_login(self.salary_reviewer)
        self.make(path + "/reject", original, 400)
        rejected = self.make(path + "/reject", {**original, "reason": "Revise the earning"}, 200)
        self.assertEqual(rejected["reviewer"], self.salary_reviewer.username)
        self.client.force_login(self.operator)
        self.make(path + "/activate", original, 409)
        self.make(path + "/submit", {}, 409)
        endpoint = "hr/" + path + "/"
        edited = self.write("patch", endpoint, {"basic": "1100.99"})
        self.assertEqual(edited.status_code, 200)
        second = self.make(path + "/submit", {})
        self.assertEqual(second["revision"], 2)
        self.client.force_login(self.salary_reviewer)
        self.make(path + "/approve", original, 409)
        self.make(path + "/approve", {"approval": second["id"]}, 200)

        self.client.force_login(self.operator)
        self.assertEqual(self.write("patch", endpoint, {"basic": "1150.99"}).status_code, 200)
        self.make(path + "/activate", {"approval": second["id"]}, 409)
        third = self.make(path + "/submit", {})
        decision = {"approval": third["id"]}
        self.client.force_login(self.salary_reviewer)
        self.make(path + "/approve", decision, 200)
        self.client.force_login(self.operator)
        with patch("apps.hr.salary_approval.audit", side_effect=RuntimeError("audit probe")):
            self.make(path + "/activate", decision, 500)
        self.assertFalse(self.get_hr(path + "/").json()["active"])
        activated = self.make(path + "/activate", decision, 200)
        self.make(path + "/activate", decision, 409)
        detail = self.get_hr(path + "/").json()
        self.assertEqual(detail["status"], "active")
        self.assertEqual(activated["activator"], self.operator.username)
        self.assertEqual(activated["snapshot"]["basic"], "1150.99")
        self.assertEqual(activated["snapshot"]["components"], draft["components"])
        self.assertEqual(self.write("patch", endpoint, {"basic": "1.00"}).status_code, 400)
        self.assertEqual(self.get_hr(path + "/approvals/").json()[2]["snapshot"], first["snapshot"])
        self.assertEqual(
            AuditEvent.objects.filter(
                action="HR_SALARY_STRUCTURE_ACTIVATED",
                resource_id=row["id"],
            ).count(),
            1,
        )

        employee = self.employee()
        dates = {"employee": employee["id"], "structure": row["id"]}
        self.make(
            "salary-assignments",
            {**dates, "start_date": "2098-12-31", "end_date": "2099-01-01"},
            400,
        )
        assignment = {**dates, "start_date": "2099-01-01", "end_date": "2099-01-31"}
        self.make("salary-assignments", assignment)
        self.make("salary-assignments", assignment, 409)

    def test_salary_approval_license_expiry_and_configured_self_approval(self):
        from apps.hr.models import HRSettings

        HRSettings.objects.create(institution=self.school, separate_salary_structure_approver=False)
        employee = self.employee()["id"]
        prior = self.make(
            "salary-structures",
            {
                "name": "Historical structure",
                "code": "HIST-LICENSE",
                "basis": "monthly",
                "basic": "1050.50",
                "components": [],
                "active": True,
            },
        )
        dates = {"start_date": self.day, "end_date": self.day}
        self.make("salary-assignments", {**dates, "employee": employee, "structure": prior["id"]})
        period = self.make("periods", {**dates, "name": "Historical", "separate_approver": False})
        run = self.make("payroll/generate", {"period": period["id"], "key": uuid4()})
        for step in ("submit", "review", "approve", "finalize"):
            self.make(f"payroll/{run['id']}/{step}", {}, 200)
        payroll = f"payroll/{run['id']}/"
        payroll_before = self.get_hr(payroll).json()
        entry = payroll_before["entries"]["results"][0]["id"]
        payslip = f"payslips/{entry}/"
        payslip_before = self.get_hr(payslip).content
        export = self.get_hr("reports/payroll/export/").content
        row = self.make(
            "salary-structures",
            {
                "name": "Self-review policy",
                "code": "SELF",
                "basis": "monthly",
                "basic": "1500.51",
                "components": [],
            },
        )
        path = f"salary-structures/{row['id']}"
        request = self.make(path + "/submit", {})
        decision = {"approval": request["id"]}
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=3)):
            self.get_hr(path + "/")
            self.assertEqual(self.get_hr(path + "/approvals/").json()[0]["decision"], "pending")
            for operation, body in [
                ("submit", {}),
                ("approve", decision),
                ("reject", {**decision, "reason": "Test"}),
                ("activate", decision),
            ]:
                denied = self.make(path + "/" + operation, body, 403)
                self.assertIn("current subscription", str(denied))
            self.assertEqual(self.get_hr(path + "/approvals/").json()[0]["decision"], "pending")
            self.assertEqual(self.get_hr(payroll).json(), payroll_before)
            self.assertEqual(self.get_hr(payslip).content, payslip_before)
            self.assertEqual(self.get_hr("reports/payroll/export/").content, export)
            renewed = self.write(
                "post", "license/activate/", {"token": self.token(self.now + timedelta(days=3))}
            )
            self.assertEqual(renewed.status_code, 201, renewed.content)
            result = self.make(path + "/approve", decision, 200)
            self.assertEqual(result["reviewer"], self.operator.username)
            self.make(path + "/activate", decision, 200)

    def test_salary_revision_uses_future_assignment_and_preserves_finalized_payroll(self):
        employee = self.employee()["id"]
        initial = self.make(
            "salary-structures",
            {
                "name": "Original",
                "code": "OLD",
                "basis": "monthly",
                "basic": "1000.10",
                "active": True,
                "components": [{"label": "Allowance", "kind": "earning", "amount": "25.15"}],
            },
        )
        dates = {"start_date": self.day, "end_date": self.day}
        original_assignment = self.make(
            "salary-assignments",
            {
                **dates,
                "employee": employee,
                "structure": initial["id"],
            },
        )
        original = self.make("periods", {**dates, "name": "Original", "separate_approver": False})
        run = self.make("payroll/generate", {"period": original["id"], "key": uuid4()})
        path = f"payroll/{run['id']}"
        for step in ("submit", "review", "approve", "finalize"):
            self.make(path + "/" + step, {}, 200)
        before = self.get_hr(path + "/").json()["entries"]
        self.assertEqual(before["results"][0]["net"], "1025.25")
        revision = self.make(
            "salary-structures",
            {
                "name": "Future",
                "code": "NEW",
                "basis": "monthly",
                "basic": "1200.10",
                "active": True,
                "components": [
                    {"label": "Allowance", "kind": "earning", "amount": "50.15"},
                    {"label": "Deduction", "kind": "deduction", "amount": "5.05"},
                ],
            },
        )
        assignment = {"employee": employee, "structure": revision["id"]}
        self.make("salary-assignments", {**assignment, **dates}, 409)
        tomorrow = self.day + timedelta(days=1)
        self.make(
            "salary-assignments",
            {
                **assignment,
                "start_date": tomorrow,
                "end_date": self.day,
            },
            400,
        )
        future = {"start_date": tomorrow, "end_date": tomorrow}
        self.make("salary-assignments", {**assignment, **future})
        period = self.make("periods", {**future, "name": "Future"})
        preview = self.make("payroll/preview", {"period": period["id"]}, 200)
        self.assertEqual(preview["entries"][0]["net"], "1245.20")
        stored = self.get_hr(f"salary-assignments/{original_assignment['id']}/").json()
        self.assertEqual(stored["structure"], initial["id"])
        reply = self.write(
            "patch",
            f"hr/salary-assignments/{original_assignment['id']}/",
            {"structure": revision["id"]},
        )
        self.assertEqual(reply.status_code, 403)
        self.make(path + "/recalculate", {}, 409)
        self.assertEqual(self.get_hr(path + "/").json()["entries"], before)

    def test_separate_payroll_approver_and_immutable_snapshot(self):
        employee = self.employee()["id"]
        structure = self.make(
            "salary-structures",
            {
                "name": "Dual control",
                "code": "DUAL",
                "basis": "monthly",
                "basic": "1010.25",
                "active": True,
                "components": [],
            },
        )
        dates = {"start_date": self.day, "end_date": self.day}
        self.make(
            "salary-assignments",
            {
                **dates,
                "employee": employee,
                "structure": structure["id"],
            },
        )
        period = self.make("periods", {**dates, "name": "Dual", "separate_approver": True})
        run = self.make("payroll/generate", {"period": period["id"], "key": uuid4()})
        path = f"payroll/{run['id']}"
        self.make(path + "/submit", {}, 200)
        self.make(path + "/review", {}, 200)
        original = self.get_hr(path + "/").json()["entries"]
        denied = self.make(path + "/approve", {}, 403)
        self.assertIn("separate operator", denied["details"]["detail"])
        self.assertEqual(self.get_hr(path + "/").json()["status"], "reviewed")
        self.reader.user_permissions.set(
            permission_rows(
                {
                    "accounts.view_payroll",
                    "accounts.approve_payroll",
                }
            )
        )
        self.client.force_login(self.reader)
        self.make(path + "/approve", {}, 200)
        self.make(path + "/finalize", {}, 403)
        self.assertEqual(self.get_hr(path + "/").json()["status"], "approved")
        self.client.force_login(self.operator)
        self.make(path + "/finalize", {}, 200)
        self.make(path + "/recalculate", {}, 409)
        final = self.get_hr(path + "/").json()
        self.assertEqual(final["entries"], original)
        self.assertEqual(final["status"], "finalized")
        decisions = {row["status"]: row["actor_id"] for row in final["decisions"]}
        self.assertEqual(str(decisions["submitted"]), str(self.operator.pk))
        self.assertEqual(str(decisions["approved"]), str(self.reader.pk))

    def test_hr_attendance_leave_and_payroll(self):
        employee = self.employee()["id"]
        history = self.get_hr(f"employees/{employee}/history/").json()
        self.assertEqual(history[0]["details"]["designation"], "Teacher")
        recorded = self.make(
            "attendance", {"employee": employee, "date": self.day, "status": "present"}
        )
        self.make("attendance", {"employee": employee, "date": self.day, "status": "present"}, 400)
        self.make(
            f"attendance/{recorded['id']}/correct",
            {"status": "late", "reason": "Clock record"},
            200,
        )
        corrections = f"attendance/{recorded['id']}/corrections/"
        history = self.get_hr(corrections).json()["results"]
        self.assertEqual(history[0]["previous"], {"status": "present"})
        self.assertEqual(history[0]["revised"], {"status": "late"})
        self.assertEqual(history[0]["reason"], "Clock record")
        self.make(f"attendance/{recorded['id']}/correct", {"status": "absent"}, 400)
        self.client.force_login(self.reader)
        self.get_hr(corrections, 403)
        self.client.force_login(self.operator)
        policy = self.make("leave-types", {"name": "Annual", "code": "ANNUAL", "annual_days": 5})
        leave = self.make(
            "leaves",
            {
                "employee": employee,
                "leave_type": policy["id"],
                "start_date": self.day,
                "end_date": self.day,
                "reason": "Appointment",
            },
        )
        self.make(f"leaves/{leave['id']}/approve", {}, 200)
        structure = self.make(
            "salary-structures",
            {
                "name": "Teaching",
                "code": "SAL",
                "basis": "monthly",
                "basic": "1000.10",
                "active": True,
                "components": [{"label": "Allowance", "kind": "earning", "amount": "125.55"}],
            },
        )
        self.make(
            "salary-assignments",
            {
                "employee": employee,
                "structure": structure["id"],
                "start_date": self.day,
                "end_date": self.term.end_date,
            },
        )
        advance = self.make(
            "advances",
            {
                "employee": employee,
                "reference": uuid4(),
                "amount": "100.00",
                "installment": "30.00",
                "recover_from": self.day,
            },
        )
        self.make(f"advances/{advance['id']}/approve", {}, 200)
        self.make(f"advances/{advance['id']}/disburse", {}, 200)
        period = self.make(
            "periods",
            {
                "name": "Current payroll",
                "start_date": self.day,
                "end_date": self.day,
                "separate_approver": False,
            },
        )
        preview = self.make("payroll/preview", {"period": period["id"]}, 200)
        self.assertEqual(preview["entries"][0]["net"], "1095.65")
        request = {"period": period["id"], "key": uuid4()}
        run = self.make("payroll/generate", request)
        self.assertEqual(self.make("payroll/generate", request, 200)["id"], run["id"])
        self.make(f"payroll/{run['id']}/recalculate", {}, 200)
        entry = self.get_hr(f"payroll/{run['id']}/").json()["entries"]["results"][0]
        payment = {
            "entry": entry["id"],
            "amount": "500.00",
            "date": self.day,
            "key": uuid4(),
            "method": "cash",
        }
        self.make("salary-payments", payment, 409)
        for step in ("submit", "review", "approve", "finalize"):
            self.make(f"payroll/{run['id']}/{step}", {}, 200)
        posted = self.make("salary-payments", payment)
        self.assertEqual(self.make("salary-payments", payment, 200)["id"], posted["id"])
        self.make("salary-payments", payment | {"amount": "600.00", "key": uuid4()}, 400)
        self.assertContains(self.get_hr(f"payslips/{entry['id']}/"), "595.65")
        self.make(
            "payroll-adjustments",
            {
                "entry": entry["id"],
                "amount": "-20.00",
                "reason": "Approved adjustment",
                "key": uuid4(),
            },
        )
        self.assertContains(self.get_hr(f"payslips/{entry['id']}/"), "575.65")
        self.make(f"salary-payments/{posted['id']}/reverse", {"reason": "Wrong cash envelope"}, 200)
        self.assertContains(self.get_hr(f"payslips/{entry['id']}/"), "1075.65")
        self.assertIn("'=استاد", self.get_hr("reports/employees/export/").content.decode())
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=5)):
            self.make("salary-payments", payment | {"key": uuid4()}, 403)
            self.get_hr(f"payslips/{entry['id']}/")
        self.client.force_login(self.reader)
        self.get_hr("payroll/", 403)
        self.get_hr(f"payslips/{entry['id']}/", 403)

    def test_private_documents_and_numbering(self):
        person = self.employee()
        change = self.client.patch(
            API + "hr/settings/",
            {
                "employee_prefix": "STAFF",
                "next_employee_number": 42,
                "document_retention_by_kind": {"contract": 30},
            },
            format="json",
        )
        self.assertEqual(change.status_code, 200, change.content)
        employee = self.make(
            "employees",
            {
                "first_name": "Employee without login",
                "department": person["department"],
                "designation": person["designation"],
                "employment_type": "temporary",
                "joined_on": self.day,
            },
        )
        self.assertEqual(employee["code"], "STAFF-00042")
        scan = BytesIO()
        Image.new("RGB", (2, 2)).save(scan, format="PNG")
        upload = SimpleUploadedFile("scan.png", scan.getvalue(), content_type="image/png")
        result = self.client.post(
            API + "hr/documents/",
            {
                "employee": employee["id"],
                "label": "Contract scan",
                "kind": "contract",
                "file": upload,
            },
            format="multipart",
        )
        self.assertEqual(result.status_code, 201, result.content)
        document = result.json()["id"]
        self.assertEqual(
            self.get_hr(f"documents/{document}/download/")["Content-Type"], "image/png"
        )
        self.assertEqual(result.json()["review_on"], (self.day + timedelta(days=30)).isoformat())
        self.make(f"documents/{document}/retention", {"operation": "hold", "reason": "Review"}, 200)
        self.make(f"documents/{document}/archive", {}, 400)
        self.make(
            f"documents/{document}/retention", {"operation": "release", "reason": "Closed"}, 200
        )
        history = self.get_hr(f"documents/{document}/reviews/").json()
        self.assertEqual(history["count"], 2)
        self.make(f"documents/{document}/archive", {}, 200)
        self.client.force_login(self.reader)
        self.get_hr(f"documents/{document}/download/", 403)


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class HRConcurrencyTests(TransactionTestCase):
    token = HRWorkflowTests.token
    write = HRWorkflowTests.write
    make = HRWorkflowTests.make
    employee = HRWorkflowTests.employee

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Payroll concurrency requires PostgreSQL.")
        with transaction.atomic():
            HRWorkflowTests.setUpTestData.__func__(self)
        HRWorkflowTests.setUp(self)

    def race(self, path, requests, *, other_path=None):
        barrier = Barrier(2)
        clients = [APIClient(), APIClient()]
        for client in clients:
            client.force_login(self.operator)

        def call(client, data, route):
            try:
                barrier.wait(10)
                reply = client.post(API + "hr/" + route + "/", data, format="json")
                return reply.status_code, reply.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(call, clients, requests, [path, other_path or path]))

    def test_concurrent_accrual_posts_a_single_transaction(self):
        person = self.employee()
        policy = self.make(
            "leave-types",
            {"name": "Annual", "code": "ANNUAL-RACE", "annual_days": 12, "accrual_mode": "fixed"},
        )
        params = {"employee": person["id"], "leave_type": policy["id"], "through": self.day}
        results = self.race("leave-balances/apply", [params, params])
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(sorted(result["posted"] for _, result in results), [0, 1])
        self.assertEqual({Decimal(str(result["balance"])) for _, result in results}, {Decimal(12)})

    def test_concurrent_policy_publications_have_one_effective_version(self):
        from apps.hr.models import LeavePolicyVersion

        policy = self.make(
            "leave-types", {"name": "Monthly", "code": "VERSION-RACE", "accrual_mode": "monthly"}
        )
        revision = {"effective_start": date(self.day.year + 1, 1, 1), "terms": {"annual_days": 12}}
        results = self.race(f"leave-types/{policy['id']}/versions", [revision, revision])
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(LeavePolicyVersion.objects.filter(leave_type_id=policy["id"]).count(), 2)

    def test_concurrent_leave_revision_and_accrual_keep_the_original_version(self):
        from apps.hr.models import LeaveBalanceTransaction

        person = self.employee()
        policy = self.make(
            "leave-types",
            {
                "name": "Concurrent",
                "code": "MIXED-RACE",
                "annual_days": 12,
                "accrual_mode": "fixed",
            },
        )
        results = self.race(
            "leave-balances/apply",
            [
                {"employee": person["id"], "leave_type": policy["id"], "through": self.day},
                {
                    "effective_start": date(self.day.year + 1, 1, 1),
                    "terms": {"annual_days": 24},
                },
            ],
            other_path=f"leave-types/{policy['id']}/versions",
        )
        self.assertEqual([status for status, _ in results], [200, 201])
        scheduled, original = results[1][1]
        self.assertEqual(scheduled["status"], "scheduled")
        posted = LeaveBalanceTransaction.objects.get(leave_type_id=policy["id"])
        self.assertEqual(str(posted.policy_version_id), original["id"])
        self.assertEqual(posted.amount, Decimal("12.00"))

    def test_salary_approval_serializes_submission_decision_and_activation(self):
        from apps.hr.models import HRSettings, SalaryStructureApproval

        HRSettings.objects.create(institution=self.school, separate_salary_structure_approver=False)
        draft = self.make(
            "salary-structures",
            {
                "name": "Approval race",
                "code": "APPROVAL-RACE",
                "basis": "monthly",
                "basic": "1250.50",
                "components": [],
            },
        )
        path = f"salary-structures/{draft['id']}"
        submitted = self.race(path + "/submit", [{}, {}])
        self.assertEqual(sorted(status for status, _ in submitted), [200, 201])
        approval = submitted[0][1]["id"]
        self.assertEqual(submitted[1][1]["id"], approval)
        action = {"approval": approval}
        self.assertEqual(
            sorted(status for status, _ in self.race(path + "/approve", [action, action])),
            [200, 409],
        )
        self.assertEqual(
            sorted(status for status, _ in self.race(path + "/activate", [action, action])),
            [200, 409],
        )
        persisted = SalaryStructureApproval.objects.get(structure_id=draft["id"])
        self.assertEqual(str(persisted.pk), approval)
        self.assertTrue(persisted.structure.active)
        self.assertIsNotNone(persisted.activated_at)

    def test_generation_and_payment_serialize(self):
        person = self.employee()
        structure = self.make(
            "salary-structures",
            {
                "name": "Monthly",
                "code": "PAY",
                "basis": "monthly",
                "basic": "100.00",
                "active": True,
                "components": [],
            },
        )
        self.make(
            "salary-assignments",
            {
                "employee": person["id"],
                "structure": structure["id"],
                "start_date": self.day,
                "end_date": self.day,
            },
        )
        period = self.make(
            "periods",
            {
                "name": "Month",
                "start_date": self.day,
                "end_date": self.day,
                "separate_approver": False,
            },
        )
        results = self.race(
            "payroll/generate", [{"period": period["id"], "key": uuid4()} for _ in range(2)]
        )
        self.assertEqual(sorted(code for code, _ in results), [201, 400])
        run = dict(results)[201]
        for action in ("submit", "review", "approve", "finalize"):
            self.make(f"payroll/{run['id']}/{action}", {}, 200)
        entry = PayrollEntry.objects.get()
        data = {
            "entry": entry.pk,
            "amount": "75.00",
            "date": self.day,
            "method": "cash",
            "key": uuid4(),
        }
        attempts = self.race("salary-payments", [data, data])
        self.assertEqual(sorted(code for code, _ in attempts), [200, 201])
        self.assertEqual(entry.payments.count(), 1)
        self.assertEqual(payable(entry), Decimal("25.00"))
