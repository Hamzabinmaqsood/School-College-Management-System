from datetime import date, timedelta
from typing import ClassVar
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict, RecordsView, school
from apps.accounts.authentication import audit
from apps.attendance.models import AttendanceHoliday
from apps.attendance.service import policy as attendance_policy

from . import models
from .accrual import balance, post_leave, post_plan
from .calendar import month_rows
from .leave_policy import resolve_effective_leave_policy
from .schedule import elapsed, is_overnight, scheduled_day


def today():
    return timezone.localdate(timezone=ZoneInfo(school().timezone))


def input_data(schema, request, **kwargs):
    form = schema(data=request.data, **kwargs)
    form.is_valid(raise_exception=True)
    return form.validated_data


def schema(model, exclude=("institution",), read_only=()):
    meta = type("Meta", (), {"model": model, "exclude": exclude, "read_only_fields": read_only})
    return type(model.__name__ + "Serializer", (serializers.ModelSerializer,), {"Meta": meta})


class HRView(RecordsView):
    license_feature = "hr"

    def finalize_response(self, request, response, *args, **kwargs):
        result = super().finalize_response(request, response, *args, **kwargs)
        result["Cache-Control"] = "no-store"
        return result

    def perform_create(self, serializer):
        values = {"institution": school()} if self.institution_lookup == "institution" else {}
        row = serializer.save(**values)
        audit(self.request, "HR_CREATED", row._meta.model_name, row)

    def perform_update(self, serializer):
        row = serializer.save()
        audit(self.request, "HR_UPDATED", row._meta.model_name, row)


def registry(
    model,
    view,
    write,
    *,
    scope="institution",
    excludes=("institution",),
    read_only=(),
    filters=(),
    search=(),
    feature="hr",
    editable=True,
    serializer=None,
):
    grants = {"list": view, "retrieve": view, "create": write}
    if editable:
        grants["partial_update"] = write
    return type(
        model.__name__ + "View",
        (HRView,),
        {
            "queryset": model.objects.all(),
            "serializer_class": serializer or schema(model, excludes, read_only),
            "institution_lookup": scope,
            "permission_map": grants,
            "filterset_fields": filters,
            "search_fields": search,
            "license_feature": feature,
        },
    )


def employment(employee, day):
    return employee.joined_on <= day and (not employee.ended_on or day <= employee.ended_on)


def contract_for(employee, day):
    return models.EmploymentContract.objects.filter(
        employee=employee, start_date__lte=day, end_date__gte=day, active=True
    ).first()


class EmployeeSerializer(schema(models.Employee)):
    code = serializers.SlugField(max_length=40, required=False)

    def validate(self, values):
        current = self.instance
        start = values.get("joined_on", getattr(current, "joined_on", None))
        end = values.get("ended_on", getattr(current, "ended_on", None))
        if end and end < start:
            raise ValidationError("Exit date must follow the joining date.")
        status = values.get("status", getattr(current, "status", "active"))
        if status not in {"active", "on_leave", "suspended"} and not end:
            raise ValidationError("An exit date is required for ended employment.")
        return values


class Employees(HRView):
    queryset = models.Employee.objects.select_related("department", "designation")
    serializer_class = EmployeeSerializer
    filterset_fields = ("department", "designation", "status", "designation__teaching")
    search_fields = ("code", "first_name", "last_name", "display_name")
    permission_map: ClassVar = {
        "list": "accounts.view_staff",
        "retrieve": "accounts.view_staff",
        "create": "accounts.add_employee",
        "partial_update": "accounts.change_employee",
        "history": "accounts.view_staff",
    }

    def history_row(self, row):
        models.EmployeePositionHistory.objects.create(
            employee=row,
            effective=today(),
            changed_by=self.request.user,
            details={
                "department": row.department.name,
                "designation": row.designation.name,
                "status": row.status,
                "employment_type": row.employment_type,
            },
        )
        return row

    def perform_create(self, serializer):
        institution = school()
        extra = {}
        if not serializer.validated_data.get("code"):
            settings, _ = models.HRSettings.objects.get_or_create(institution=institution)
            while True:
                code = f"{settings.employee_prefix}-{settings.next_employee_number:05d}"
                settings.next_employee_number += 1
                if not self.get_queryset().filter(code__iexact=code).exists():
                    break
            settings.save(update_fields=["next_employee_number", "updated_at"])
            extra["code"] = code
        row = self.history_row(serializer.save(institution=institution, **extra))
        audit(self.request, "HR_EMPLOYEE_CREATED", "employee", row)

    def perform_update(self, serializer):
        row = serializer.save()
        if set(serializer.validated_data) & {
            "department",
            "designation",
            "status",
            "employment_type",
        }:
            self.history_row(row)
        audit(
            self.request,
            "HR_EMPLOYEE_UPDATED",
            "employee",
            row,
            fields=sorted(serializer.validated_data),
        )

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(
            list(
                models.EmployeePositionHistory.objects.filter(employee=self.get_object())
                .order_by("-effective", "-created_at")
                .values("id", "effective", "details")
            )
        )


class AttendanceSerializer(schema(models.EmployeeAttendance, exclude=("recorded_by",))):
    def validate(self, values):
        employee, day = values["employee"], values["date"]
        if not employment(employee, day) or day > today():
            raise ValidationError("Choose a date during employment through today.")
        start, end = values.get("check_in"), values.get("check_out")
        contract = contract_for(employee, day)
        if start and end and elapsed(start, end, overnight=is_overnight(contract)) <= timedelta():
            raise ValidationError("Check-out must follow check-in.")
        if values.get("overtime", 0) < 0:
            raise ValidationError("Overtime cannot be negative.")
        holiday = AttendanceHoliday.objects.filter(
            institution=employee.institution, date=day
        ).first()
        if values["status"] not in {"holiday", "excused"} and not scheduled_day(
            day, contract, holiday, attendance_policy().non_teaching_weekdays
        ):
            raise ValidationError("This date is outside the employee's scheduled workdays.")
        return values


class Attendance(HRView):
    queryset = models.EmployeeAttendance.objects.all()
    institution_lookup = "employee__institution"
    serializer_class = AttendanceSerializer
    filterset_fields = ("date", "employee", "employee__department", "status")
    permission_map: ClassVar = {
        "list": "accounts.view_staff_attendance",
        "retrieve": "accounts.view_staff_attendance",
        "create": "accounts.mark_staff_attendance",
        "correct": "accounts.correct_staff_attendance",
        "bulk": "accounts.mark_staff_attendance",
        "calendar": "accounts.view_staff_attendance",
        "corrections": "accounts.view_staff_attendance",
    }

    def perform_create(self, serializer):
        row = serializer.save(recorded_by=self.request.user)
        audit(self.request, "HR_ATTENDANCE_RECORDED", "employeeattendance", row)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        month = request.query_params.get("month", today().strftime("%Y-%m"))
        try:
            first_day = date.fromisoformat(f"{month}-01")
        except ValueError as error:
            raise ValidationError({"month": "Use YYYY-MM."}) from error
        institution = school()
        if department_id := request.query_params.get("department"):
            identifier = serializers.UUIDField().run_validation(department_id)
            department = get_object_or_404(
                models.Department, institution=institution, pk=identifier
            )
            entries = self.get_queryset().filter(
                employee__department=department,
                date__year=first_day.year,
                date__month=first_day.month,
            )
            return Response(
                {
                    "department": department.pk,
                    "month": month,
                    "totals": list(
                        entries.values("date", "status")
                        .annotate(count=Count("pk"))
                        .order_by("date", "status")
                    ),
                }
            )
        identifier = serializers.UUIDField().run_validation(request.query_params.get("employee"))
        employee = get_object_or_404(models.Employee, institution=institution, pk=identifier)
        return Response(
            {
                "employee": employee.pk,
                "month": month,
                "days": list(month_rows(employee, first_day, institution)),
            }
        )

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        def operation():
            data = input_data(
                self.serializer_class, request, many=True, allow_empty=False, max_length=500
            )
            rows = [models.EmployeeAttendance(**item, recorded_by=request.user) for item in data]
            models.EmployeeAttendance.objects.bulk_create(rows)
            audit(request, "HR_ATTENDANCE_BULK", "employeeattendance", count=len(rows))
            return Response({"created": len(rows)}, status=201)

        return self.write(operation)

    @action(detail=True, methods=["get"])
    def corrections(self, request, pk=None):
        entry = self.get_object()
        records = models.EmployeeAttendanceCorrection.objects.filter(entry=entry).order_by(
            "-created_at", "-pk"
        )
        page = self.paginate_queryset(records)
        return self.get_paginated_response(
            schema(models.EmployeeAttendanceCorrection, ("entry",))(page, many=True).data
        )

    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        def operation():
            row = self.get_object()
            reason = serializers.CharField(max_length=400).run_validation(
                request.data.get("reason")
            )
            previous = self.get_serializer(row).data
            update = {
                field: request.data[field]
                for field in ("status", "check_in", "check_out", "overtime", "remarks")
                if field in request.data
            }
            form = self.get_serializer(row, data={**previous, **update})
            form.is_valid(raise_exception=True)
            row = form.save()
            models.EmployeeAttendanceCorrection.objects.create(
                entry=row,
                previous={key: previous[key] for key in update},
                revised={key: form.data[key] for key in update},
                reason=reason,
                actor=request.user,
            )
            audit(request, "HR_ATTENDANCE_CORRECTED", "employeeattendance", row)
            return Response(form.data)

        return self.write(operation)


class Leaves(HRView):
    queryset = models.EmployeeLeave.objects.all()
    institution_lookup = "employee__institution"
    serializer_class = schema(models.EmployeeLeave, ("submitted_by",), ("days", "status"))
    filterset_fields = ("employee", "status", "leave_type")
    permission_map: ClassVar = {
        "list": "accounts.view_staff_leave",
        "retrieve": "accounts.view_staff_leave",
        "create": "accounts.request_staff_leave",
        "approve": "accounts.approve_staff_leave",
        "reject": "accounts.approve_staff_leave",
        "cancel": "accounts.approve_staff_leave",
    }

    def perform_create(self, serializer):
        data = serializer.validated_data
        start, end, person = data["start_date"], data["end_date"], data["employee"]
        if (
            start.year != end.year
            or start > end
            or not employment(person, start)
            or not employment(person, end)
        ):
            raise ValidationError("Choose a single-year range during employment.")
        terms, _ = resolve_effective_leave_policy(data["leave_type"], start)
        if (
            not terms.active
            or self.get_queryset()
            .filter(
                employee=person,
                start_date__lte=end,
                end_date__gte=start,
                status__in=("pending", "approved"),
            )
            .exists()
        ):
            raise Conflict("This leave overlaps a request or the leave type is inactive.")
        holidays = {
            row.date: row
            for row in AttendanceHoliday.objects.filter(
                institution=person.institution, date__range=(start, end)
            )
        }
        non_working = attendance_policy().non_teaching_weekdays
        days = 0
        day = start
        while day <= end:
            contract = contract_for(person, day)
            if scheduled_day(day, contract, holidays.get(day), non_working):
                days += 1
            day += timedelta(days=1)
        if not days:
            raise ValidationError("The request contains no scheduled working day.")
        row = serializer.save(days=days, submitted_by=self.request.user)
        audit(self.request, "HR_LEAVE_REQUESTED", "employeeleave", row)

    def transition(self, request, target):
        def operation():
            row = self.get_object()
            if row.status == target:
                return Response(self.get_serializer(row).data)
            if row.status != "pending" and not (target == "cancelled" and row.status == "approved"):
                raise Conflict("This request cannot change from its current state.")
            reason = serializers.CharField(max_length=400, allow_blank=True).run_validation(
                request.data.get("reason", "")
            )
            if target == "rejected" and not reason:
                raise ValidationError("Explain why the request is rejected.")
            terms, _ = resolve_effective_leave_policy(row.leave_type, row.start_date)
            managed = terms.paid and terms.accrual_mode != "legacy"
            if target == "approved" and managed:
                if row.start_date.year == today().year:
                    post_plan(row.employee, row.leave_type, today(), request.user)
                available = balance(row.employee, row.leave_type, row.start_date.year)
                if not terms.allow_negative and available < row.days:
                    raise Conflict("The employee does not have enough accrued leave.")
                post_leave(row, "consumption", request.user, reason)
            elif target == "cancelled" and row.balance_events.filter(event="consumption").exists():
                post_leave(row, "reversal", request.user, reason)
            elif target == "approved":
                used = (
                    self.get_queryset()
                    .filter(
                        employee=row.employee,
                        leave_type=row.leave_type,
                        status="approved",
                        start_date__year=row.start_date.year,
                    )
                    .aggregate(total=Sum("days"))["total"]
                    or 0
                )
                if terms.paid and used + row.days > terms.annual_days:
                    raise Conflict("The employee does not have enough entitlement.")
            row.status = target
            row.save(update_fields=["status", "updated_at"])
            models.LeaveDecision.objects.create(
                leave=row, status=target, actor=request.user, reason=reason
            )
            audit(request, "HR_LEAVE_" + target.upper(), "employeeleave", row)
            return Response(self.get_serializer(row).data)

        return self.write(operation)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.transition(request, "approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.transition(request, "rejected")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.transition(request, "cancelled")


class ScheduleTemplate(serializers.Serializer):
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        allow_empty=False,
    )
    shift_start = serializers.TimeField()
    shift_end = serializers.TimeField()
    break_minutes = serializers.IntegerField(min_value=0, default=0)
    late_tolerance_minutes = serializers.IntegerField(min_value=0, default=0)
    early_tolerance_minutes = serializers.IntegerField(min_value=0, default=0)

    def validated_schedule(self):
        self.is_valid(raise_exception=True)
        validate_schedule(self.validated_data)
        return self.validated_data


def validate_schedule(data):
    weekdays = data.get("weekdays", [])
    if not isinstance(weekdays, list) or any(
        type(day) is not int or not 0 <= day <= 6 for day in weekdays
    ):
        raise ValidationError("Use weekday numbers from 0 to 6.")
    begins, ends = data.get("shift_start"), data.get("shift_end")
    if (begins is None) != (ends is None) or (begins is not None and begins == ends):
        raise ValidationError("Configure distinct shift start and end times.")
    minutes = elapsed(begins, ends, overnight=True).total_seconds() / 60 if begins else 0
    if data.get("break_minutes", 0) and data["break_minutes"] >= minutes:
        raise ValidationError("The break must be shorter than the scheduled shift.")
    for field in ("late_tolerance_minutes", "early_tolerance_minutes"):
        if data.get(field, 0) and data[field] >= minutes:
            raise ValidationError({field: "Tolerance must be shorter than the scheduled shift."})


class DepartmentFields(schema(models.Department)):
    def validate_default_schedule(self, value):
        if value == {}:
            return value
        schedule = ScheduleTemplate(data=value).validated_schedule()
        return {
            key: item.isoformat() if key.startswith("shift_") else item
            for key, item in schedule.items()
        }


class ContractFields(schema(models.EmploymentContract, ("created_by",))):
    use_department_schedule = serializers.BooleanField(write_only=True, default=False)

    def validate_leave_entitlements(self, value):
        if not isinstance(value, dict):
            raise ValidationError("Map leave type codes to annual days.")
        parser = serializers.DecimalField(max_digits=6, decimal_places=2)
        result = {}
        for code, amount in value.items():
            number = parser.run_validation(str(amount))
            if not code.strip() or number < 0 or code.casefold() in result:
                raise ValidationError("Use unique leave type codes and nonnegative days.")
            result[code.casefold()] = str(number)
        return result


class Contracts(HRView):
    queryset = models.EmploymentContract.objects.all()
    institution_lookup = "employee__institution"
    serializer_class = ContractFields
    filterset_fields = ("employee", "active")
    permission_map: ClassVar = {
        "list": "accounts.view_staff",
        "retrieve": "accounts.view_staff",
        "create": "accounts.manage_hr_registry",
    }

    def perform_create(self, serializer):
        data = serializer.validated_data
        start, end = data["start_date"], data["end_date"]
        if start > end:
            raise ValidationError("Use ordered contract dates.")
        if data.pop("use_department_schedule", False):
            template = data["employee"].department.default_schedule
            if not template:
                raise ValidationError("Configure the department schedule before applying it.")
            data.update(ScheduleTemplate(data=template).validated_schedule())
        validate_schedule(data)
        if (
            data.get("active", True)
            and self.get_queryset()
            .filter(
                employee=data["employee"], start_date__lte=end, end_date__gte=start, active=True
            )
            .exists()
        ):
            raise Conflict("An active contract overlaps these dates.")
        row = serializer.save(created_by=self.request.user)
        audit(self.request, "HR_CONTRACT_CREATED", "employmentcontract", row)


class Settings(HRView):
    permission_map: ClassVar = {
        "retrieve": "accounts.manage_hr_registry",
        "partial_update": "accounts.manage_hr_registry",
    }

    def retrieve(self, request):
        model = models.HRSettings
        row = model.objects.filter(institution=school()).first() or model(institution=school())
        return Response(schema(model)(row).data)

    def partial_update(self, request):
        def operation():
            row, _ = models.HRSettings.objects.get_or_create(institution=school())
            form = schema(models.HRSettings)(row, data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            if form.validated_data.get("next_employee_number", 1) < 1:
                raise ValidationError("Employee numbering must start at one or above.")
            policies = form.validated_data.get("document_retention_by_kind", {})
            if not isinstance(policies, dict) or any(
                not kind.strip()
                or len(kind) > 40
                or type(days) is not int
                or not 1 <= days <= 36525
                for kind, days in policies.items()
            ):
                raise ValidationError(
                    {"document_retention_by_kind": "Map document types to days (1 to 36525)."}
                )
            row = form.save()
            audit(request, "HR_SETTINGS_UPDATED", "hrsettings", row)
            return Response(form.data)

        return self.write(operation)
