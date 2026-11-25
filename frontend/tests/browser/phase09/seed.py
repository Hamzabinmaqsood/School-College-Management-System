import importlib.util
import json
import os
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from apps.academics.models import AcademicClass, AcademicSession, ClassSubject, Section, Subject
from apps.accounts.access import permission_codes, permission_rows, seed_roles
from apps.accounts.models import Institution, Role, User
from apps.admissions.models import StudentEnrollment
from apps.attendance.models import TeachingAssignment
from apps.examinations.models import (
    ExamAssessmentComponent,
    Examination,
    ExaminationClass,
    ExaminationSubject,
    MarksSubmission,
    StudentAssessmentMark,
    StudentExamRegistration,
)
from apps.hr.models import (
    Department,
    Designation,
    Employee,
    EmployeeAttendance,
    EmployeeDocument,
    EmployeeLeave,
    EmploymentContract,
    LeaveType,
)
from apps.licensing.models import InstallationIdentity
from apps.licensing.protocol import canonical, decode, encode
from apps.students.models import Student
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth.models import Group
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

spec = importlib.util.spec_from_file_location(
    "hr_tests", "backend/tests/test_examination_workflow.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
seed_roles()
school = Institution.objects.create(
    code="browser", name="Browser Academy", institution_type="academy"
)
identity = InstallationIdentity.objects.create(institution=school)
password = token_urlsafe(24)
user = User.objects.create_superuser(username="fixture-admin", password=password)
key = Ed25519PrivateKey.generate()
keys = {"test": encode(key.public_key().public_bytes_raw())}
Path(os.environ["LICENSE_PUBLIC_KEYS_FILE"]).write_text(json.dumps(keys))
token = module.ExaminationTests.token(
    SimpleNamespace(school=school, identity=identity, key=key), timezone.now()
)
payload = json.loads(decode(token.split(".")[1]))
features = {"attendance", "hr", "payroll"}
if os.environ.get("SMS_PHASE10"):
    features.add("timetables")
payload["features"] = sorted(set(payload["features"]) | features)
encoded = canonical(payload)
token = f"SMS1.{encode(encoded)}.{encode(key.sign(encoded))}"

client = APIClient(HTTP_HOST="localhost")
client.force_login(user)
result = client.post(
    "/api/v1/license/activate/", {"token": token}, format="json", HTTP_HOST="localhost"
)
assert result.status_code == 201, result.content
department = Department.objects.create(institution=school, name="Science", code="SCI")
designation = Designation.objects.create(
    institution=school, name="Teacher", code="TEACH", teaching=True
)
day = timezone.localdate()
employee = Employee.objects.create(
    institution=school,
    department=department,
    designation=designation,
    first_name="Browser",
    code="EMP-1",
    employment_type="Contract",
    joined_on=day,
)
staff_attendance = EmployeeAttendance.objects.create(
    employee=employee, status="present", date=day, recorded_by=user
)
teacher = User.objects.create_user(username="fixture-teacher")
teacher.groups.add(Group.objects.get(role__key="teacher"))
term = AcademicSession.objects.create(
    institution=school,
    name="Acceptance term",
    code="TERM",
    start_date=day - timedelta(days=20),
    end_date=day + timedelta(days=20),
    status="active",
    is_current=True,
)
grade = AcademicClass.objects.create(institution=school, name="Acceptance Class", code="GR")
section = Section.objects.create(academic_class=grade, name="Acceptance Section", code="ONE")
subject = Subject.objects.create(institution=school, name="Acceptance Subject", code="SUB")
ClassSubject.objects.create(academic_class=grade, subject=subject)
case = module.ExaminationTests()
case.client, case.school, case.day, case.term, case.grade = client, school, day, term, grade
_, exam_group = case.setup_exam()
submission = MarksSubmission.objects.order_by("pk").first()
marks_path = f"marks/{submission.pk}/"
draft = case.get_exam(marks_path).json()
saved_marks = case.make(
    marks_path + "save",
    {
        "version": draft["version"],
        "marks": [
            {"registration": row["registration"], "status": "marked", "obtained": "64.00"}
            for row in draft["marks"]
        ],
    },
    200,
)
submitted = case.make(marks_path + "submit", {"version": saved_marks["version"]}, 200)
case.make(marks_path + "verify", {"version": submitted["version"]}, 200)
result_run = case.make("results", {"group": exam_group["id"]})
case.make(f"results/{result_run['id']}/approve", {}, 200)
csrf_response = client.get("/api/v1/auth/csrf/").json()
response = client.post(
    "/api/v1/admissions/",
    case.admission("ATT-D", section, roll="2", name="Attendance Student"),
    format="json",
    HTTP_HOST="localhost",
)
TestCase().assertEqual(response.status_code, 201, response.content)
student = Student.objects.get(admission_number="ATT-D")
register = client.post(
    "/api/v1/attendance/",
    {
        "session": term.pk,
        "academic_class": grade.pk,
        "section": section.pk,
        "subject": subject.pk,
        "date": day,
        "mode": "period",
        "period": "P8",
    },
    format="json",
)
TestCase().assertEqual(register.status_code, 201, register.content)
record = register.json()
register_path = f"/api/v1/attendance/{record['id']}/"
saved = client.post(
    register_path + "save/",
    {
        "version": record["version"],
        "marks": [{"record": row["id"], "status": "present"} for row in record["records"]],
    },
    format="json",
)
TestCase().assertEqual(saved.status_code, 200, saved.content)
final = client.post(
    register_path + "finalize/", {"version": saved.json()["version"]}, format="json"
)
TestCase().assertEqual(final.status_code, 200, final.content)
teacher_password = token_urlsafe(24)
teacher.set_password(teacher_password)
teacher.save()
teacher.user_permissions.add(
    *permission_rows(
        {
            "accounts.view_attendance",
            "accounts.view_student_details",
            "accounts.view_attendance_history",
            "attendance.view_attendancesession",
            "attendance.add_attendancesession",
            "attendance.change_attendancerecord",
            "accounts.finalize_attendance",
            "accounts.view_exam_marks",
            "accounts.enter_exam_marks",
            "accounts.update_exam_marks",
            "accounts.submit_exam_marks",
        }
    )
)
TeachingAssignment.objects.create(
    user=teacher,
    session=term,
    academic_class=grade,
    section=section,
    subject=subject,
    effective_start=day,
    effective_end=day,
)
exam_assignment = TeachingAssignment.objects.create(
    user=teacher,
    session=term,
    academic_class=grade,
    subject=Subject.objects.get(code="MATH"),
    effective_start=day,
    effective_end=day,
)
image = BytesIO()
Image.new("RGB", (4, 4)).save(image, format="PNG")
content = image.getvalue()
document = EmployeeDocument.objects.create(
    employee=employee,
    label="Acceptance due scan",
    kind="contract",
    content=content,
    size=len(content),
    uploaded_by=user,
    review_on=day,
)
accounts = {
    "admin": {"username": user.username, "password": password},
    "teacher": {"username": teacher.username, "password": teacher_password},
}
for name, grants in {
    "hr": (
        "accounts.view_staff",
        "accounts.change_employee",
        "accounts.view_staff_attendance",
        "accounts.view_staff_leave",
    ),
    "payroll": ("accounts.view_payroll", "accounts.view_salary_setup"),
    "restricted": (),
}.items():
    secret = token_urlsafe(24)
    account = User.objects.create_user(username=f"fixture-{name}", password=secret)
    if name == "payroll" and os.environ.get("SMS_PHASE09_FINANCE"):
        grants = (
            *grants,
            "accounts.manage_salary_setup",
            "accounts.generate_payroll",
            "accounts.review_payroll",
            "accounts.approve_payroll",
            "accounts.finalize_payroll",
            "accounts.pay_salary",
            "accounts.print_payslip",
            "accounts.export_hr",
            "accounts.export_payroll",
            "accounts.view_staff",
        )
    if name == "payroll" and os.environ.get("SMS_PHASE09_FINANCE") == "desktop":
        grants = (*grants, "accounts.submit_payroll", "accounts.correct_payroll")
    if name == "payroll" and os.environ.get("SMS_PHASE09_APPROVAL"):
        grants = (
            *grants,
            "accounts.view_salary_structure_approvals",
            "accounts.approve_salary_structure",
        )
    if name in {"hr", "payroll"}:
        group = Group.objects.create(name=f"Acceptance {name} grants")
        role_record = Role.objects.create(group=group)
        if name == "hr":
            hr_role = role_record
        else:
            payroll_role = role_record
        group.permissions.set(permission_rows(grants))
        account.groups.add(group)
    else:
        account.user_permissions.add(*permission_rows(grants))
    accounts[name] = {"username": account.username, "password": secret}
other_class = AcademicClass.objects.create(institution=school, name="Unrelated class", code="OTHER")
other_section = Section.objects.create(academic_class=grade, name="Unrelated section", code="OTHER")
ClassSubject.objects.create(academic_class=other_class, subject=subject)
unrelated = Subject.objects.create(institution=school, name="Unrelated subject", code="OTHER")
ClassSubject.objects.create(academic_class=grade, subject=unrelated)
blocked = {}
for status in ("future", "expired", "inactive"):
    extra = Section.objects.create(academic_class=grade, name=status.title(), code=status)
    start = day + timedelta(days=1) if status == "future" else day - timedelta(days=2)
    end = day - timedelta(days=1) if status == "expired" else day + timedelta(days=3)
    TeachingAssignment.objects.create(
        user=teacher,
        session=term,
        academic_class=grade,
        section=extra,
        subject=subject,
        active=status != "inactive",
        effective_start=start,
        effective_end=end,
    )
    blocked[status] = str(extra.pk)
primary_component = submission.component
primary_paper = primary_component.subject
primary_exam = primary_paper.group.exam
scope_exam = Examination.objects.create(
    institution=school,
    exam_type=primary_exam.exam_type,
    session=term,
    scheme=primary_exam.scheme,
    code="SCOPE",
    name="Scope fixtures",
    start_date=day,
    end_date=day,
    status="open",
    created_by=user,
)
scope_group = ExaminationClass.objects.create(exam=scope_exam, academic_class=grade)
other_exam_class = ExaminationClass.objects.create(exam=scope_exam, academic_class=other_class)
section_paper = ExaminationSubject.objects.create(
    group=scope_group,
    subject=primary_paper.subject,
    subject_name=primary_paper.subject_name,
)
section_component = ExamAssessmentComponent.objects.create(
    subject=section_paper,
    name="Theory",
    maximum=primary_component.maximum,
)
exam_scope = {}
for name, group, exam_subject in (
    ("unrelated-class", other_exam_class, primary_paper.subject),
    ("unrelated-subject", scope_group, unrelated),
):
    paper = ExaminationSubject.objects.create(
        group=group,
        subject=exam_subject,
        subject_name=exam_subject.name,
    )
    component = ExamAssessmentComponent.objects.create(
        subject=paper,
        name="Theory",
        maximum=primary_component.maximum,
    )
    exam_scope[name] = str(MarksSubmission.objects.create(component=component).pk)
exam_scope["unrelated-section"] = str(
    MarksSubmission.objects.create(
        component=section_component,
        section=other_section,
    ).pk
)
write_targets = {}
for role_name in accounts:
    row = Employee.objects.create(
        institution=school,
        code=f"WRITE-{role_name}",
        first_name="Prior",
        department=department,
        designation=designation,
        employment_type="Contract",
        joined_on=day,
    )
    write_targets[role_name] = str(row.pk)
output = {
    "accounts": accounts,
    "writeTargets": write_targets,
    "employeeFields": {
        "department": str(department.pk),
        "designation": str(designation.pk),
        "employment_type": "Contract",
        "joined_on": day.isoformat(),
    },
    "institution": str(school.pk),
    "permissions": {
        key: sorted(permission_codes(User.objects.get(username=value["username"])))
        for key, value in accounts.items()
    },
    "employee": str(employee.pk),
    "day": day.isoformat(),
    "document": str(document.pk),
    "staffAttendance": str(staff_attendance.pk),
    "marks": str(submission.pk),
    "examAssignment": str(exam_assignment.pk),
    "examScope": exam_scope,
    "result": result_run["id"],
    "hrRole": str(hr_role.pk),
    "control": {
        "cookie": "; ".join(f"{key}={item.value}" for key, item in client.cookies.items()),
        "csrf": csrf_response["csrf_token"],
    },
    "student": str(student.pk),
    "attendance": {
        "session": str(term.pk),
        "academic_class": str(grade.pk),
        "section": str(section.pk),
        "subject": str(subject.pk),
        "date": day.isoformat(),
        "mode": "period",
        "period": "P9",
    },
    "unrelated": {
        "class": str(other_class.pk),
        "section": str(other_section.pk),
        "subject": str(unrelated.pk),
        **blocked,
    },
}
if os.environ.get("SMS_PHASE09_TEACHER"):
    teacher_grants = permission_codes(teacher)
    teacher_group = Group.objects.create(name="Acceptance teacher grants")
    teacher_role = Role.objects.create(group=teacher_group)
    teacher_group.permissions.set(permission_rows(teacher_grants))
    teacher.groups.set([teacher_group])
    teacher.user_permissions.clear()
    source = submission.marks.first().registration
    registration = StudentExamRegistration.objects.create(
        group=scope_group,
        enrollment=source.enrollment,
        student=source.student,
        details=source.details,
    )
    writable = MarksSubmission.objects.create(component=section_component)
    StudentAssessmentMark.objects.create(submission=writable, registration=registration)
    unrelated_marks = {}
    for label, submission_id in exam_scope.items():
        scoped_submission = MarksSubmission.objects.select_related(
            "component__subject__group",
            "section",
        ).get(pk=submission_id)
        group = scoped_submission.component.subject.group
        if label == "unrelated-subject":
            assigned = registration
        else:
            code = "SCOPE-" + label.upper()
            payload = case.admission(code, scoped_submission.section, roll="3", name=label)
            payload["enrollment"]["academic_class"] = str(group.academic_class_id)
            response = client.post("/api/v1/admissions/", payload, format="json")
            TestCase().assertEqual(response.status_code, 201, response.content)
            enrolled = StudentEnrollment.objects.get(student__admission_number=code)
            assigned = StudentExamRegistration.objects.create(
                group=group,
                enrollment=enrolled,
                student=enrolled.student,
                section=scoped_submission.section,
                details={**source.details, "roll": "3"},
            )
        StudentAssessmentMark.objects.create(submission=scoped_submission, registration=assigned)
        unrelated_marks[label] = {
            "submission": str(scoped_submission.pk),
            "registration": str(assigned.pk),
        }
    output["teacherWrite"] = {
        "role": str(teacher_role.pk),
        "draft": str(writable.pk),
        "registration": str(registration.pk),
        "unrelated": unrelated_marks,
    }
if os.environ.get("SMS_PHASE10"):
    secret = token_urlsafe(24)
    reviewer = User.objects.create_user(username="fixture-timetable-reviewer", password=secret)
    reviewer_group = Group.objects.create(name="Timetable approval fixtures")
    reviewer_role = Role.objects.create(group=reviewer_group)
    reviewer.groups.add(reviewer_group)
    reviewer_group.permissions.set(
        permission_rows(
            [
                "accounts.view_dashboard",
                "accounts.view_timetable",
                "accounts.approve_timetable",
                "accounts.view_sessions",
                "accounts.view_classes",
                "accounts.view_sections",
                "accounts.view_subjects",
            ]
        )
    )
    output["timetableReviewerRole"] = str(reviewer_role.pk)
    output["timetableReviewerGrants"] = sorted(permission_codes(reviewer))
    output["timetableReviewer"] = {"username": reviewer.username, "password": secret}
    output["timetableTeacher"] = str(teacher.pk)
    output["timetableWeekday"] = day.weekday()
    if os.environ.get("SMS_PHASE10B"):
        output["timetableUnassignedTeacher"] = str(
            User.objects.create_user(username="fixture-unassigned-teacher").pk
        )
        ClassSubject.objects.filter(academic_class=grade, subject=subject).update(mandatory=False)
        TeachingAssignment.objects.filter(
            user=teacher,
            session=term,
            section=section,
            subject=subject,
        ).update(effective_end=day + timedelta(days=20))
        alternative = Subject.objects.create(
            institution=school, code="TT-ALT", name="Unstaffed curriculum"
        )
        foreign = Subject.objects.create(
            institution=school, code="TT-OTHER", name="Other class curriculum"
        )
        inactive = Subject.objects.create(
            institution=school,
            code="TT-INACTIVE",
            name="Inactive curriculum",
            active=False,
        )
        ClassSubject.objects.create(academic_class=grade, subject=alternative)
        ClassSubject.objects.create(academic_class=other_class, subject=foreign)
        ClassSubject.objects.create(academic_class=grade, subject=inactive)
        output["timetableCurriculum"] = {
            "alternative": str(alternative.pk),
            "foreign": str(foreign.pk),
        }
        alternate_term = AcademicSession.objects.create(
            institution=school,
            name="Other curriculum term",
            code="TT-TERM",
            start_date=day,
            end_date=day + timedelta(days=20),
            status="active",
        )
        alternate_section = Section.objects.create(
            academic_class=other_class,
            name="Other curriculum section",
            code="TT-SECT",
        )
        outside_term = Subject.objects.create(
            institution=school,
            code="TT-TERM-ONLY",
            name="Other term curriculum",
        )
        ClassSubject.objects.create(
            academic_class=grade, subject=outside_term, session=alternate_term
        )
        ClassSubject.objects.create(
            academic_class=other_class,
            subject=subject,
            session=alternate_term,
            active=False,
        )
        output["timetableCurriculum"].update(
            session=str(alternate_term.pk),
            section=str(alternate_section.pk),
        )
        covering_teacher = User.objects.create_user(username="fixture-cover-teacher")
        TeachingAssignment.objects.create(
            user=covering_teacher,
            session=term,
            academic_class=grade,
            section=section,
            subject=subject,
            effective_start=day,
            effective_end=day + timedelta(days=20),
        )
        teacher_employee = Employee.objects.create(
            institution=school,
            department=department,
            designation=designation,
            user=teacher,
            first_name="Scheduling",
            code="TT-FIXTURE",
            employment_type="Contract",
            joined_on=day,
        )
        leave_type = LeaveType.objects.create(
            institution=school, name="Timetable fixture", code="TT"
        )
        leave_date = day + timedelta(days=1)
        EmployeeLeave.objects.create(
            employee=teacher_employee,
            leave_type=leave_type,
            start_date=leave_date,
            end_date=leave_date,
            days=1,
            status="approved",
            reason="Disposable timetable fixture",
            submitted_by=user,
        )
        output["timetableCoverTeacher"] = str(covering_teacher.pk)
        output["timetableEnrollment"] = str(
            StudentEnrollment.objects.get(
                student=student,
                session=term,
                section=section,
            ).pk
        )
if os.environ.get("SMS_PHASE09_APPROVAL"):
    output["approvalReviewerRole"] = str(payroll_role.pk)
if os.environ.get("SMS_PHASE09_WORKFLOWS"):
    from apps.hr.models import OvertimePolicy, StaffOvertime

    policy = OvertimePolicy.objects.create(
        institution=school,
        name="Acceptance overtime",
        start_date=day,
        end_date=day,
        rate="12.50",
        maximum_hours=8,
    )
    leave_policy = LeaveType.objects.create(
        institution=school,
        name="Acceptance request policy",
        code="WORKFLOW",
        paid=False,
        annual_days=12,
    )
    ledger_policy = LeaveType.objects.create(
        institution=school,
        name="Acceptance ledger policy",
        code="WF-LEDGER",
        accrual_mode="manual",
    )
    output["workflow"] = {
        "policy": str(policy.pk),
        "leavePolicy": str(leave_policy.pk),
        "ledgerPolicy": str(ledger_policy.pk),
        "roles": {},
    }
    for role, target in write_targets.items():
        person = Employee.objects.get(pk=target)
        mark_target = Employee.objects.create(
            institution=school,
            code=f"MARK-{role}",
            first_name="Mark fixture",
            department=department,
            designation=designation,
            joined_on=day,
            user=User.objects.create_user(username=f"assignment-{role}"),
        )
        absence = EmployeeAttendance.objects.create(
            employee=person,
            status="present",
            date=day,
            recorded_by=user,
            remarks=f"Correction target {role}",
        )
        overtime = StaffOvertime.objects.create(
            attendance=absence,
            policy=policy,
            requested_hours="2.00",
            requested_by=teacher,
        )
        leave = EmployeeLeave.objects.create(
            employee=person,
            leave_type=leave_policy,
            start_date=day,
            end_date=day,
            days=1,
            reason=f"Request target {role}",
            status="pending",
            submitted_by=user,
        )
        output["workflow"]["roles"][role] = {
            "correction": str(absence.pk),
            "overtime": str(overtime.pk),
            "leave": str(leave.pk),
            "markTarget": str(mark_target.pk),
        }
if os.environ.get("SMS_PHASE09_REVISIONS"):
    ledger_year = day.year - 1
    ledger_owner = Employee.objects.create(
        institution=school,
        code="LEDGER-TEST",
        first_name="Leave fixture",
        department=department,
        designation=designation,
        employment_type="Contract",
        joined_on=day.replace(year=ledger_year - 1, month=1, day=1),
    )
    shift_start = date(ledger_year, 2, 1)
    EmploymentContract.objects.create(
        employee=ledger_owner,
        kind="Night shift fixture",
        start_date=shift_start,
        end_date=date(ledger_year, 2, 28),
        weekdays=list(range(7)),
        shift_start="22:00",
        shift_end="06:00",
        created_by=user,
        leave_entitlements={"month-ui": "48"},
    )
    EmployeeAttendance.objects.create(
        employee=ledger_owner,
        date=shift_start,
        status="present",
        check_in="22:10",
        check_out="05:45",
        recorded_by=user,
    )
    EmployeeAttendance.objects.create(
        employee=ledger_owner,
        date=date(ledger_year, 2, 2),
        status="absent",
        recorded_by=user,
    )
    calendar_leave = LeaveType.objects.create(
        institution=school,
        code="CAL-FIXTURE",
        name="Calendar fixture leave",
    )
    EmployeeLeave.objects.create(
        employee=ledger_owner,
        leave_type=calendar_leave,
        start_date=date(ledger_year, 2, 3),
        end_date=date(ledger_year, 2, 3),
        days=1,
        status="approved",
        submitted_by=user,
    )
    output["revisionLeave"] = {"employee": str(ledger_owner.pk), "year": ledger_year}
if os.environ.get("SMS_PHASE09_FINANCE"):
    reviewer_password = token_urlsafe(24)
    reviewer = User.objects.create_superuser(
        username="fixture-salary-reviewer", password=reviewer_password
    )
    reviewer_client = APIClient(HTTP_HOST="localhost")
    reviewer_client.force_login(reviewer)
    reviewer_csrf = reviewer_client.get("/api/v1/auth/csrf/").json()
    output["salaryReviewer"] = {
        "username": reviewer.username,
        "password": reviewer_password,
        "cookie": "; ".join(
            f"{key}={value.value}" for key, value in reviewer_client.cookies.items()
        ),
        "csrf": reviewer_csrf["csrf_token"],
    }

if os.environ.get("SMS_PHASE09_FINANCE"):

    def hr_post(route, payload, expected=201):
        response = client.post(f"/api/v1/hr/{route}/", payload, format="json")
        TestCase().assertEqual(response.status_code, expected, response.content)
        return response.json()

    pay_person = Employee.objects.create(
        institution=school,
        code="FIN-TEST",
        first_name="Financial fixture",
        department=department,
        designation=designation,
        employment_type="Contract",
        joined_on=day - timedelta(days=30),
    )
    structure = hr_post(
        "salary-structures",
        {
            "name": "Finance fixture",
            "code": "FIN",
            "basis": "monthly",
            "basic": "1234.56",
            "active": False,
            "components": [],
        },
    )
    approval = hr_post(f"salary-structures/{structure['id']}/submit", {})
    approve_response = reviewer_client.post(
        f"/api/v1/hr/salary-structures/{structure['id']}/approve/",
        {"approval": approval["id"]},
        format="json",
    )
    TestCase().assertEqual(approve_response.status_code, 200, approve_response.content)
    hr_post(f"salary-structures/{structure['id']}/activate", {"approval": approval["id"]}, 200)
    assignment = hr_post(
        "salary-assignments",
        {
            "employee": pay_person.pk,
            "structure": structure["id"],
            "start_date": day - timedelta(days=30),
            "end_date": day,
        },
    )
    periods = {}
    for offset, name in enumerate((*accounts, "control"), start=1):
        period_date = day - timedelta(days=offset)
        periods[name] = hr_post(
            "periods",
            {
                "name": f"Fixture {name}",
                "start_date": period_date,
                "end_date": period_date,
                "separate_approver": False,
            },
        )["id"]
    run = hr_post("payroll/generate", {"period": periods["control"], "key": uuid4()})
    for step in ("submit", "review", "approve", "finalize"):
        hr_post(f"payroll/{run['id']}/{step}", {}, 200)
    detail = client.get(f"/api/v1/hr/payroll/{run['id']}/").json()
    entry = detail["entries"]["results"][0]
    payment = hr_post(
        "salary-payments",
        {
            "entry": entry["id"],
            "amount": "100.00",
            "date": day,
            "method": "cash",
            "key": uuid4(),
        },
    )
    advance = hr_post(
        "advances",
        {
            "employee": pay_person.pk,
            "reference": uuid4(),
            "amount": "50.00",
            "installment": "10.00",
            "recover_from": day,
        },
    )
    hr_post(f"advances/{advance['id']}/approve", {}, 200)
    output["finance"] = {
        "structure": structure["id"],
        "assignment": assignment["id"],
        "employee": str(pay_person.pk),
        "periods": periods,
        "run": run["id"],
        "entry": entry["id"],
        "payment": payment["id"],
        "advance": advance["id"],
        "payrollRole": str(payroll_role.pk),
    }
Path(os.environ["SMS_PHASE09_FIXTURES"]).write_text(json.dumps(output))
