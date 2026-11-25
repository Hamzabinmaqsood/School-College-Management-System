from typing import ClassVar

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.academics.access import Conflict, RecordsView, school
from apps.academics.models import AcademicClass, AcademicSession
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit

from .access import BROAD, assignments_for, group_allowed, scoped
from .models import LeaveDecision, StudentLeaveRequest
from .register_api import student_name
from .serializers import LeaveFields, ReviewFields
from .service import eligible, policy


class StudentChoices(serializers.Serializer):
    session = serializers.PrimaryKeyRelatedField(queryset=AcademicSession.objects.all())
    date = serializers.DateField()


class Leaves(RecordsView):
    queryset = StudentLeaveRequest.objects.select_related(
        "student", "session", "enrollment__academic_class"
    )
    serializer_class = LeaveFields
    institution_lookup = "session__institution"
    license_feature = "attendance"
    http_method_names = ("get", "post", "head", "options")
    filterset_fields: ClassVar = {
        "session": ["exact"],
        "status": ["exact"],
        "student": ["exact"],
        "enrollment__academic_class": ["exact"],
    }
    search_fields = ("student__first_name", "student__last_name", "student__admission_number")
    ordering = ("-start_date", "-created_at", "pk")
    permission_map: ClassVar = {
        "list": "attendance.view_studentleaverequest",
        "sessions": "attendance.view_studentleaverequest",
        "classes": "attendance.view_studentleaverequest",
        "retrieve": "attendance.view_studentleaverequest",
        "create": "attendance.add_studentleaverequest",
        "choices": "attendance.add_studentleaverequest",
        "approve": "accounts.review_attendance_leave",
        "reject": "accounts.review_attendance_leave",
        "cancel": "accounts.cancel_attendance_leave",
    }

    def get_queryset(self):
        rows = scoped(
            super().get_queryset(),
            self.request.user,
            "enrollment__",
            leave=True,
            operational=self.request.method not in {"GET", "HEAD", "OPTIONS"},
        )
        for key, lookup in (("from_date", "end_date__gte"), ("to_date", "start_date__lte")):
            if value := self.request.query_params.get(key):
                rows = rows.filter(**{lookup: serializers.DateField().run_validation(value)})
        return rows

    def retrieve(self, request, *args, **kwargs):
        leave = self.get_object()
        history = list(
            leave.decisions.order_by("created_at").values(
                "status", "remarks", "actor_id", "created_at"
            )
        )
        return Response(
            dict(self.get_serializer(leave).data) | {"decisions": history},
            headers={"Cache-Control": "no-store"},
        )

    def perform_create(self, serializer):
        data = serializer.validated_data
        enrollment = (
            eligible(data["session"], data["start_date"]).filter(student=data["student"]).first()
        )
        if not enrollment or (enrollment.ended_on and enrollment.ended_on <= data["end_date"]):
            raise serializers.ValidationError(
                "Choose leave dates within one eligible placement. Split leave at a transfer date."
            )
        if not group_allowed(
            self.request.user,
            {
                "session": enrollment.session,
                "academic_class": enrollment.academic_class,
                "section": enrollment.section,
                "date": data["start_date"],
                "end_date": data["end_date"],
            },
        ):
            raise PermissionDenied("This student is outside your teaching assignments.")
        if StudentLeaveRequest.objects.filter(
            student=data["student"],
            session=data["session"],
            status__in=("pending", "approved"),
            start_date__lte=data["end_date"],
            end_date__gte=data["start_date"],
        ).exists():
            raise Conflict("A pending or approved leave request overlaps these dates.")
        leave = serializer.save(enrollment=enrollment, submitted_by=self.request.user)
        LeaveDecision.objects.create(leave=leave, status="pending", actor=self.request.user)
        audit(self.request, "ATTENDANCE_LEAVE_SUBMITTED", "studentleave", leave)

    @action(detail=False, methods=["get"])
    def sessions(self, request):
        rows = AcademicSession.objects.filter(institution=school()).order_by("-start_date")

        if BROAD not in permission_codes(request.user):
            rows = rows.filter(
                pk__in=assignments_for(request.user, operational=True)
                .filter(subject__isnull=True)
                .values("session_id")
            )
        return Response(list(rows.values("id", "name", "is_current")))

    @action(detail=False, methods=["get"])
    def classes(self, request):
        rows = AcademicClass.objects.filter(institution=school()).order_by("name")
        if BROAD not in permission_codes(request.user):
            rows = rows.filter(
                pk__in=assignments_for(request.user, operational=True)
                .filter(subject__isnull=True)
                .values("academic_class_id")
            )
        return Response(list(rows.values("id", "name")))

    @action(detail=False, methods=["get"])
    def choices(self, request):
        form = StudentChoices(data=request.query_params)
        form.is_valid(raise_exception=True)
        session, date = form.validated_data["session"], form.validated_data["date"]
        if (
            session.institution_id != school().pk
            or not session.start_date <= date <= session.end_date
        ):
            raise serializers.ValidationError("Choose a date inside this institution's session.")
        rows = (
            scoped(eligible(session, date), request.user, enrollment=True, day=date)
            .select_related("student")
            .order_by("student__first_name", "student__admission_number", "pk")
        )
        if query := request.query_params.get("search"):
            from django.db.models import Q

            rows = rows.filter(
                Q(student__first_name__icontains=query[:150])
                | Q(student__admission_number__icontains=query[:150])
            )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(
            [
                {
                    "id": row.student_id,
                    "name": student_name(row.student),
                    "admission_number": row.student.admission_number,
                }
                for row in page
            ]
        )

    def decide(self, request, status):
        def change():
            leave = self.get_object()
            form = ReviewFields(data=request.data)
            form.is_valid(raise_exception=True)
            remarks = form.validated_data.get("remarks", "")
            if leave.status == status:
                return Response(self.get_serializer(leave).data)
            allowed = ("pending", "approved") if status == "cancelled" else ("pending",)
            if leave.status not in allowed:
                raise Conflict("This leave request cannot make that transition.")
            if status == "rejected" and policy().require_rejection_reason and not remarks:
                raise serializers.ValidationError({"remarks": "Give a reason for rejection."})
            leave.status, leave.reviewed_by, leave.reviewed_at = (
                status,
                request.user,
                timezone.now(),
            )
            leave.review_remarks = remarks
            leave.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "review_remarks",
                    "updated_at",
                ]
            )
            decision = LeaveDecision.objects.create(
                leave=leave, status=status, actor=request.user, remarks=remarks
            )
            audit(
                request,
                "ATTENDANCE_LEAVE_" + status.upper(),
                "studentleave",
                leave,
                decision_id=str(decision.pk),
            )
            return Response(self.get_serializer(leave).data)

        return self.write(change)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.decide(request, "approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.decide(request, "rejected")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.decide(request, "cancelled")
