from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, Section
from apps.accounts.access import seed_roles
from apps.accounts.models import Institution, User
from apps.fees.ledger import round_money
from apps.fees.models import FeeInvoice, FeePayment
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, encode
from apps.students.models import Student
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

API = "/api/v1/"


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class FeeWorkflowTests(TestCase):
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
                "features": ["academics", "admissions", "fees", "students"],
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
        response = self.write("post", "fees/" + path + "/", payload)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def setup_fees(self):
        student = self.add_student(name="=طالب علم")
        category = self.make("categories", {"name": "Tuition", "code": "TUITION"})
        plan = self.make(
            "structures",
            {
                "name": "Regular fees",
                "session": self.term.pk,
                "academic_class": self.grade.pk,
                "start_date": self.term.start_date,
                "end_date": self.term.end_date,
                "items": [
                    {"category": category["id"], "amount": "1250.50", "recurrence": "monthly"}
                ],
            },
        )
        self.make(f"structures/{plan['id']}/activate", {}, 200)
        self.make(
            "assignments",
            {
                "enrollment": student.enrollments.get().pk,
                "category": category["id"],
                "amount": "1000.10",
                "start_date": self.term.start_date,
                "end_date": self.term.end_date,
            },
        )
        concession = self.make(
            "concessions",
            {
                "student": student.pk,
                "session": self.term.pk,
                "label": "Merit award",
                "category": category["id"],
                "kind": "percent",
                "value": "50.00",
                "start_date": self.term.start_date,
                "end_date": self.term.end_date,
            },
        )
        self.make(f"concessions/{concession['id']}/approve", {}, 200)
        return student, category

    def invoice(self, student):
        criteria = {"session": self.term.pk, "period": self.day.replace(day=1)}
        preview = self.make("billing/preview", criteria, 200)
        self.assertEqual(preview["total"], "500.05")
        self.make("billing/generate", criteria)
        duplicate = self.make("billing/generate", criteria)
        self.assertEqual((duplicate["invoices"], duplicate["duplicate_lines"]), (0, 1))
        return FeeInvoice.objects.get(student=student)

    def payment(self, student, invoice, amount):
        return {
            "student": student.pk,
            "date": str(invoice.issue_date),
            "amount": amount,
            "method": "cash",
            "allocations": [{"invoice": invoice.pk, "amount": amount}],
            "idempotency_key": uuid4(),
        }

    def get_fee(self, path):
        result = self.client.get(API + "fees/" + path)
        self.assertEqual(result.status_code, 200, result.content)
        return result

    def test_billing_payment_retry_refund_and_reports(self):
        student, _ = self.setup_fees()
        duplicate = self.write("post", "fees/categories/", {"name": "Repeat", "code": "tuition"})
        self.assertEqual(duplicate.status_code, 409)
        invoice = self.invoice(student)
        body = self.payment(student, invoice, "200.02")
        posted = self.make("payments", body)
        self.assertEqual(self.make("payments", body, 200)["receipt"], posted["receipt"])
        self.assertEqual(FeePayment.objects.count(), 1)
        invalid = self.payment(student, invoice, "300.04")
        self.make("payments", invalid, 409)
        self.assertEqual(FeePayment.objects.count(), 1)
        balance = self.get_fee(f"invoices/{invoice.pk}/").json()
        self.assertEqual((balance["outstanding"], balance["status"]), ("300.03", "partially_paid"))
        closed = self.make("payments", self.payment(student, invoice, "300.03"))
        self.assertEqual(self.get_fee(f"invoices/{invoice.pk}/").json()["status"], "paid")
        self.assertContains(self.get_fee(f"payments/{posted['id']}/receipt/"), "200.02")
        self.make(
            "refunds",
            {
                "allocation": closed["allocations"][0]["id"],
                "amount": "25.00",
                "date": str(invoice.issue_date),
                "reason": "Refund authorized",
                "idempotency_key": uuid4(),
            },
        )
        statement = self.get_fee(f"students/{student.pk}/statement/").json()
        self.assertEqual((statement["paid"], statement["outstanding"]), ("475.05", "25.00"))
        self.assertEqual(self.get_fee("overview/").json()["collected_this_month"], "475.05")
        statement_csv = self.get_fee("reports/outstanding/export/").content.decode("utf-8-sig")
        self.assertIn("'=طالب علم", statement_csv)
        self.make(f"payments/{posted['id']}/reverse", {"reason": "Duplicate bank entry"}, 200)
        self.assertContains(self.get_fee(f"payments/{posted['id']}/receipt/"), "Reversed")
        self.assertEqual(self.get_fee("overview/").json()["outstanding"], "225.02")

    def test_adjustment_requires_approval_and_expired_read_access(self):
        student, _ = self.setup_fees()
        invoice = self.invoice(student)
        result = self.write("patch", "fees/settings/", {"dual_approval": True})
        self.assertEqual(result.status_code, 200, result.content)
        adj = self.make(
            "adjustments",
            {
                "invoice": invoice.pk,
                "kind": "credit",
                "amount": "20.05",
                "reason": "Corrected charge",
                "idempotency_key": uuid4(),
            },
        )
        self.make(f"adjustments/{adj['id']}/approve", {}, 403)
        approver = User.objects.create_superuser(username="fee-approver")
        self.client.force_login(approver)
        self.make(f"adjustments/{adj['id']}/approve", {}, 200)
        self.assertEqual(self.get_fee(f"invoices/{invoice.pk}/").json()["total"], "480.00")
        with patch("apps.licensing.service.utc_now", return_value=self.now + timedelta(days=5)):
            self.make("payments", self.payment(student, invoice, "20.00"), 403)
            self.get_fee(f"invoices/{invoice.pk}/challan/")
            self.get_fee("reports/aging/export/")
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(API + "fees/overview/").status_code, 403)

    def test_distinct_one_time_charges_and_multi_invoice_allocation(self):
        student, _ = self.setup_fees()
        invoice = self.invoice(student)
        item = self.make(
            "categories", {"name": "Lab registration", "code": "LAB", "recurrence": "one_time"}
        )
        self.make(
            "assignments",
            {
                "enrollment": student.enrollments.get().pk,
                "category": item["id"],
                "amount": "100.00",
                "start_date": self.term.start_date,
                "end_date": self.term.end_date,
            },
        )
        criteria = {
            "session": self.term.pk,
            "period": self.day.replace(day=1),
            "reference": "lab-a",
        }
        self.assertEqual(self.make("billing/generate", criteria)["total"], "100.00")
        self.assertEqual(self.make("billing/generate", criteria)["invoices"], 0)
        self.assertEqual(
            self.make("billing/generate", criteria | {"reference": "lab-b"})["invoices"], 1
        )
        one_time = FeeInvoice.objects.exclude(pk=invoice.pk).first()
        body = self.payment(student, invoice, "80.00")
        body["allocations"] = [
            {"invoice": invoice.pk, "amount": "70.00"},
            {"invoice": one_time.pk, "amount": "10.00"},
        ]
        result = self.make("payments", body)
        self.assertEqual(len(result["allocations"]), 2)
        self.make("payments", body | {"external_reference": "Changed reference"}, 409)
        self.assertEqual(self.get_fee(f"invoices/{invoice.pk}/").json()["outstanding"], "430.05")

    def test_proration_and_stale_billing_preview(self):
        student, _ = self.setup_fees()
        criteria = {"session": self.term.pk, "period": self.day.replace(day=1)}
        original = self.make("billing/preview", criteria, 200)
        result = self.write("patch", "fees/settings/", {"prorate": True, "due_day": 28})
        self.assertEqual(result.status_code, 200, result.content)
        self.make("billing/generate", criteria | {"preview_key": original["preview_key"]}, 409)
        result = self.make("billing/preview", criteria, 200)
        last = monthrange(self.day.year, self.day.month)[1]
        gross = round_money(Decimal("1000.10") * Decimal(last - self.day.day + 1) / Decimal(last))
        self.assertEqual(result["subtotal"], str(gross))
        self.make("billing/generate", criteria | {"preview_key": result["preview_key"]})
        snapshot = FeeInvoice.objects.get(student=student)
        placement = student.enrollments.get()
        placement.status = "withdrawn"
        placement.ended_on = self.day
        placement.save(update_fields=["status", "ended_on"])
        revised = self.make("billing/preview", criteria, 200)
        self.assertEqual(revised["eligible"], 0)
        self.assertEqual(FeeInvoice.objects.get(pk=snapshot.pk).issued_total, snapshot.issued_total)


@override_settings(LICENSE_PUBLIC_KEYS_FILE="")
class PostgreSQLFeeConcurrencyTests(TransactionTestCase):
    token = FeeWorkflowTests.token
    write = FeeWorkflowTests.write
    admission = FeeWorkflowTests.admission
    add_student = FeeWorkflowTests.add_student
    make = FeeWorkflowTests.make
    setup_fees = FeeWorkflowTests.setup_fees
    payment = FeeWorkflowTests.payment

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent fee posting requires PostgreSQL row locks.")
        with transaction.atomic():
            FeeWorkflowTests.setUpTestData.__func__(self)
        FeeWorkflowTests.setUp(self)

    def race(self, route, payloads):
        barrier = Barrier(2)
        clients = [APIClient(), APIClient()]
        for client in clients:
            client.force_login(self.operator)

        def post(client, payload):
            try:
                barrier.wait(timeout=10)
                response = client.post(API + "fees/" + route + "/", payload, format="json")
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(post, clients, payloads))

    def test_concurrent_generation_and_collection(self):
        student, _ = self.setup_fees()
        criteria = {"session": self.term.pk, "period": self.day.replace(day=1)}
        attempts = self.race("billing/generate", [criteria, criteria])
        self.assertEqual([status for status, _ in attempts], [201, 201])
        self.assertEqual(sorted(data["invoices"] for _, data in attempts), [0, 1])
        invoice = FeeInvoice.objects.get()
        payment = self.payment(student, invoice, "300.00")
        attempts = self.race("payments", [payment, payment])
        self.assertEqual(sorted(status for status, _ in attempts), [200, 201])
        attempts = self.race(
            "payments", [self.payment(student, invoice, "150.00") for _ in range(2)]
        )
        self.assertEqual(sorted(status for status, _ in attempts), [201, 409])
        self.assertEqual(FeePayment.objects.count(), 2)
