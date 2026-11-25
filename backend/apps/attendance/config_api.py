from typing import ClassVar

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academics.access import RecordsView, school
from apps.accounts.authentication import audit
from apps.accounts.models import User

from .models import AttendanceHoliday, TeachingAssignment
from .serializers import AssignmentFields, HolidayFields, SettingsFields
from .service import policy


class Calendar(RecordsView):
    license_feature = "attendance"
    queryset = AttendanceHoliday.objects.all()
    serializer_class = HolidayFields
    permission_map: ClassVar = {
        "list": "attendance.view_attendanceholiday",
        "retrieve": "attendance.view_attendanceholiday",
        "create": "accounts.manage_attendance_calendar",
        "partial_update": "accounts.manage_attendance_calendar",
    }
    filterset_fields = ("kind", "date")
    search_fields = ("name",)
    ordering = ("-date", "pk")

    def perform_create(self, serializer):
        entry = serializer.save(institution=school())
        audit(self.request, "ATTENDANCE_CALENDAR_CREATED", "attendanceholiday", entry)

    def perform_update(self, serializer):
        entry = serializer.save()
        audit(self.request, "ATTENDANCE_CALENDAR_UPDATED", "attendanceholiday", entry)


class Settings(RecordsView):
    license_feature = "attendance"
    permission_map: ClassVar = {
        "retrieve": "accounts.manage_attendance_settings",
        "partial_update": "accounts.manage_attendance_settings",
    }

    def retrieve(self, request):
        return Response(SettingsFields(policy()).data)

    def partial_update(self, request):
        def change():
            form = SettingsFields(policy(), data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            config = form.save()
            audit(
                request,
                "ATTENDANCE_SETTINGS_UPDATED",
                "attendancesettings",
                config,
                fields=sorted(form.validated_data),
            )
            return Response(form.data)

        return self.write(change)


class Assignments(RecordsView):
    license_feature = "attendance"
    queryset = TeachingAssignment.objects.select_related(
        "user", "session", "academic_class", "section", "subject"
    )
    serializer_class = AssignmentFields
    institution_lookup = "session__institution"
    permission_map: ClassVar = dict.fromkeys(
        ("list", "retrieve", "create", "partial_update", "users"),
        "accounts.manage_teaching_assignments",
    )
    filterset_fields = ("user", "session", "academic_class", "section", "subject", "active")
    search_fields = ("user__username", "academic_class__name")
    ordering = ("user__username", "session__name", "academic_class__name", "pk")

    def perform_create(self, serializer):
        entry = serializer.save()
        audit(self.request, "ATTENDANCE_ASSIGNMENT_CREATED", "teachingassignment", entry)

    def perform_update(self, serializer):
        fields = ("active", "effective_start", "effective_end")
        previous = AssignmentFields(serializer.instance).data
        entry = serializer.save()
        audit(
            self.request,
            "ATTENDANCE_ASSIGNMENT_UPDATED",
            "teachingassignment",
            entry,
            before={key: previous[key] for key in fields},
            after={key: serializer.data[key] for key in fields},
        )

    @action(detail=False, methods=["get"])
    def users(self, request):
        school()
        users = User.objects.filter(is_active=True).order_by("username", "pk")
        if query := request.query_params.get("search"):
            users = users.filter(username__icontains=query[:150])
        page = self.paginate_queryset(users)
        return self.get_paginated_response(
            [{"id": user.pk, "name": user.username} for user in page]
        )
