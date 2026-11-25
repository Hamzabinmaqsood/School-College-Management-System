from typing import ClassVar

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.academics.access import Conflict, school
from apps.academics.models import ClassSubject
from apps.accounts.access import permission_codes
from apps.accounts.authentication import audit
from apps.admissions.models import StudentEnrollment
from apps.attendance.models import AttendanceSession, TeachingAssignment
from apps.hr.api import HRView, input_data, schema, today

from . import models, service, workload

VIEW = "accounts.view_timetable"
MANAGE = "accounts.manage_timetable"
SETTINGS = "accounts.change_timetable_settings"
EXCEPTIONS = "accounts.change_timetable_exceptions"
OWN = "accounts.view_own_timetable"
CONFIG = {"list": VIEW, "retrieve": VIEW, "create": SETTINGS, "partial_update": SETTINGS}
DRAFT = {"list": VIEW, "retrieve": VIEW, "create": MANAGE, "partial_update": MANAGE}


class TimetableView(HRView):
    license_feature = "timetables"


class Settings(TimetableView):
    permission_map: ClassVar = {"retrieve": VIEW, "partial_update": SETTINGS}

    def retrieve(self, request):
        row = models.Settings.objects.filter(institution=school()).first() or models.Settings()
        return Response(schema(models.Settings)(row).data)

    def partial_update(self, request):
        def save():
            row, _ = models.Settings.objects.get_or_create(institution=school())
            form = schema(models.Settings)(row, data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            form.save()
            audit(request, "TIMETABLE_SETTINGS_UPDATED", "timetablesettings", row)
            return Response(form.data)

        return self.write(save)


class Shifts(TimetableView):
    queryset = models.Shift.objects.all()
    serializer_class = schema(models.Shift)
    permission_map: ClassVar = CONFIG
    search_fields = ("name", "code")

    @staticmethod
    def validate(form):
        row, data = form.instance, form.validated_data
        if row and row.plan_set.exists():
            raise Conflict("Referenced shifts are immutable. Create a new shift configuration.")
        days = data.get("weekdays", getattr(row, "weekdays", []))
        if (
            not isinstance(days, list)
            or not days
            or any(type(day) is not int or not 0 <= day <= 6 for day in days)
            or len(set(days)) != len(days)
        ):
            raise ValidationError("Choose distinct weekdays from 0 (Monday) through 6 (Sunday).")
        if data.get("starts_at", getattr(row, "starts_at", None)) >= data.get(
            "ends_at", getattr(row, "ends_at", None)
        ):
            raise ValidationError("Shift start must precede shift end on the same day.")

    def perform_create(self, serializer):
        self.validate(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self.validate(serializer)
        super().perform_update(serializer)


class Periods(Shifts):
    queryset = models.Period.objects.all()
    serializer_class = schema(models.Period, ())
    institution_lookup = "shift__institution"
    filterset_fields = ("shift", "teaching")

    @staticmethod
    def validate(form):
        row, values = form.instance, form.validated_data
        shift = values.get("shift", getattr(row, "shift", None))
        start = values.get("starts_at", getattr(row, "starts_at", None))
        end = values.get("ends_at", getattr(row, "ends_at", None))
        if len(values.get("code", getattr(row, "code", ""))) > 32:
            raise ValidationError("Use at most 32 characters for the period code.")
        if (
            shift.institution_id != school().pk
            or not shift.starts_at <= start < end <= shift.ends_at
        ):
            raise ValidationError("The period must fit inside its institution shift.")
        if row and (row.entry_set.exists() or row.exception_set.exists()):
            raise Conflict("Referenced periods are immutable.")
        if (
            shift.periods.exclude(pk=getattr(row, "pk", None))
            .filter(
                starts_at__lt=end,
                ends_at__gt=start,
            )
            .exists()
        ):
            raise Conflict("This period overlaps another period or protected break.")


class Rooms(TimetableView):
    queryset = models.Room.objects.all()
    serializer_class = schema(models.Room)
    permission_map: ClassVar = CONFIG
    search_fields = ("name", "code", "kind")
    filterset_fields = ("active", "kind")


class Availability(TimetableView):
    queryset = models.Availability.objects.all()
    serializer_class = schema(models.Availability)
    permission_map: ClassVar = CONFIG
    filterset_fields = ("teacher", "weekday")

    def perform_create(self, serializer):
        teacher = serializer.validated_data["teacher"]
        if not TeachingAssignment.objects.filter(
            user=teacher, session__institution=school()
        ).exists():
            raise ValidationError("Choose a teacher assigned in this institution.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        teacher = serializer.validated_data.get("teacher", serializer.instance.teacher)
        if not TeachingAssignment.objects.filter(
            user=teacher, session__institution=school()
        ).exists():
            raise ValidationError("Choose a teacher assigned in this institution.")
        super().perform_update(serializer)


class Dates(serializers.Serializer):
    effective_start = serializers.DateField()
    effective_end = serializers.DateField()


class PlanForm(schema(models.Plan)):
    effective_start = serializers.DateField(write_only=True)
    effective_end = serializers.DateField(write_only=True)

    def validate(self, data):
        session, section, shift = (data[key] for key in ("session", "section", "shift"))
        if {
            session.institution_id,
            section.academic_class.institution_id,
            shift.institution_id,
        } != {school().pk}:
            raise ValidationError("Session, section and shift must belong to this institution.")
        if (
            not section.active
            or not section.academic_class.active
            or not shift.active
            or session.status == "closed"
        ):
            raise ValidationError("Choose an active class, section and shift in an open session.")
        return data

    def create(self, values):
        dates = {key: values.pop(key) for key in ("effective_start", "effective_end")}
        plan = super().create(values)
        service.validate_version_bounds(
            plan, **{key.removeprefix("effective_"): value for key, value in dates.items()}
        )
        plan.versions.create(number=1, created_by=self.context["request"].user, **dates)
        return plan


VersionData = schema(models.Version, ())


class Plans(TimetableView):
    queryset = models.Plan.objects.all()
    serializer_class = PlanForm
    filterset_fields = ("session", "section", "shift")
    permission_map: ClassVar = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "versions": VIEW,
        "new_version": MANAGE,
        "subject_allocation": VIEW,
        "lesson_options": MANAGE,
        "submit": "accounts.submit_timetable",
        "approve": "accounts.approve_timetable",
        "reject": "accounts.approve_timetable",
        "publish": "accounts.publish_timetable",
    }

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        return Response(VersionData(self.get_object().versions.order_by("-number"), many=True).data)

    @action(detail=True, methods=["get"], url_path="lesson-options")
    def lesson_options(self, request, pk=None):
        plan = self.get_object()
        version_id = serializers.UUIDField().run_validation(request.query_params.get("version"))
        weekday = serializers.IntegerField(min_value=0, max_value=6).run_validation(
            request.query_params.get("weekday")
        )
        version = plan.versions.filter(pk=version_id, status="draft").first()
        if not version:
            raise ValidationError("Select a draft version from this plan.")
        start = service.first_on(version.effective_start, weekday)
        end = service.last_on(version.effective_end, weekday)
        curriculum = {}
        for item in (
            ClassSubject.objects.filter(
                academic_class=plan.section.academic_class,
            )
            .filter(Q(session=plan.session) | Q(session__isnull=True))
            .select_related("subject")
        ):
            if item.session_id or item.subject_id not in curriculum:
                curriculum[item.subject_id] = item
        groups = {}
        for group in models.TeachingGroup.objects.filter(
            session=plan.session,
            section=plan.section,
            enrollments__isnull=False,
        ).distinct():
            try:
                service.validate_roster(group, version, start, end)
            except ValidationError:
                continue
            groups.setdefault(group.subject_id, []).append(group)
        subjects = [
            item
            for item in curriculum.values()
            if item.active
            and item.subject.active
            and (item.mandatory or groups.get(item.subject_id))
        ]
        selected = next(
            (row for row in subjects if str(row.subject_id) == request.query_params.get("subject")),
            None,
        )
        teachers = {}
        if selected and start <= end and weekday in plan.shift.weekdays:
            period_id = request.query_params.get("period")
            period = (
                plan.shift.periods.filter(
                    pk=serializers.UUIDField().run_validation(period_id)
                ).first()
                if period_id
                else None
            )
            for assignment in service.eligible_assignments(
                plan,
                selected.subject,
                start,
                end,
            ).select_related("user"):
                teacher = assignment.user
                if (
                    period
                    and period.teaching
                    and (
                        service.unavailable(plan, teacher, weekday, period, start, end)
                        or service.recurring_employment_issue(plan, teacher, period, start, end)
                    )
                ):
                    continue
                teachers[teacher.pk] = {"id": teacher.pk, "name": teacher.get_username()}
        return Response(
            {
                "subjects": [{"id": row.subject_id, "name": row.subject.name} for row in subjects],
                "teachers": list(teachers.values()),
                "groups": [
                    {"id": group.pk, "name": group.name}
                    for group in groups.get(selected.subject_id, [])
                ]
                if selected and not selected.mandatory
                else [],
            }
        )

    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        def save():
            plan = self.get_object()
            dates = input_data(Dates, request)
            service.validate_version_bounds(plan, dates["effective_start"], dates["effective_end"])
            if plan.versions.exclude(status="published").exists():
                raise Conflict(
                    "Complete the existing draft and review before creating another version."
                )
            prior = plan.versions.order_by("-number").first()
            if (
                dates["effective_start"] <= prior.effective_start
                or dates["effective_start"] <= today()
            ):
                raise ValidationError(
                    "A revision must start on a future date after the previous version."
                )
            version = plan.versions.create(
                number=prior.number + 1, created_by=request.user, **dates
            )
            models.Entry.objects.bulk_create(
                [
                    models.Entry(
                        version=version,
                        period=row.period,
                        weekday=row.weekday,
                        subject=row.subject,
                        teacher=row.teacher,
                        group=row.group,
                        room=row.room,
                        notes=row.notes,
                    )
                    for row in prior.entries.all()
                ]
            )
            audit(request, "TIMETABLE_VERSION_CREATED", "timetableversion", version)
            return Response(VersionData(version).data, status=201)

        return self.write(save)

    @action(detail=True, methods=["get"], url_path="subject-allocation")
    def subject_allocation(self, request, pk=None):
        plan = self.get_object()
        identifier = serializers.UUIDField().run_validation(request.query_params.get("version"))
        version = plan.versions.filter(pk=identifier).first()
        if not version:
            raise ValidationError("Select a timetable version from this plan.")
        return Response(service.subject_requirements(version))

    def transition(self, request, before, after):
        def save():
            plan = self.get_object()
            key = serializers.UUIDField().run_validation(request.data.get("version"))
            version = plan.versions.filter(pk=key).first()
            if version is None or version.status != before:
                raise Conflict("Select a timetable version in the required state.")
            # Older integration clients can still use the state-based transition.
            if "expected_decision_at" in request.data and before in {"review", "approved"}:
                expected = serializers.DateTimeField().run_validation(
                    request.data["expected_decision_at"]
                )
                current = version.submitted_at if before == "review" else version.approved_at
                if expected != current:
                    raise Conflict("This review or approval changed. Reload the timetable version.")
            now = timezone.now()
            settings = models.Settings.objects.filter(institution=plan.institution).first()
            separation = settings is None or settings.separate_approver
            if after == "review":
                if not version.entries.exists():
                    raise ValidationError("Add teaching entries before submitting.")
                version.submitted_by, version.submitted_at = request.user, now
                version.separate_approver = separation
            if after == "approved":
                if (version.separate_approver or separation) and request.user.pk in {
                    version.created_by_id,
                    version.submitted_by_id,
                }:
                    raise PermissionDenied(
                        "A different authorized user must approve the timetable."
                    )
                version.approved_by, version.approved_at = request.user, now
            if after == "published":
                if (
                    service.published(
                        plan.institution, version.effective_start, version.effective_end
                    )
                    .exclude(plan=plan)
                    .filter(plan__section=plan.section)
                    .exists()
                ):
                    raise Conflict(
                        "Another published plan covers this section and effective dates."
                    )
                if not version.approved_by_id:
                    raise Conflict("An explicit approval is required.")
                prior = (
                    plan.versions.filter(status="published").order_by("-effective_start").first()
                )
                if prior and (version.effective_start <= max(prior.effective_start, today())):
                    raise Conflict(
                        "A replacement must start after the previous version and the current date."
                    )
                if (
                    prior
                    and models.Exception.objects.filter(
                        Q(date__gte=version.effective_start)
                        | Q(destination_date__gte=version.effective_start),
                        Q(entry__version=prior) | Q(destination_version=prior),
                    ).exists()
                ):
                    raise Conflict(
                        "Resolve future daily exceptions before publishing the replacement."
                    )
                if prior and service.end_of(prior) >= version.effective_start:
                    prior.superseded_on = version.effective_start
                    prior.save(update_fields=["superseded_on", "updated_at"])
                version.published_by, version.published_at = request.user, now
            if after in {"review", "approved", "published"}:
                for requirement in service.subject_requirements(version):
                    if (
                        not requirement["minimum"]
                        <= requirement["allocated"]
                        <= requirement["maximum"]
                    ):
                        raise Conflict(
                            f"Weekly allocation for {requirement['subject_name']} is out of bounds."
                        )
                for entry in version.entries.select_related("period", "room", "teacher", "subject"):
                    service.validate_slot(entry)
                    workload.check(entry)
                    if conflict := service.check_conflicts(entry):
                        raise Conflict(f"The timetable has a {conflict} conflict.")
            reason = ""
            if after == "draft":
                reason = serializers.CharField(max_length=400).run_validation(
                    request.data.get("reason")
                )
                version.approved_by = version.approved_at = None
            version.status = after
            version.save()
            audit(request, "TIMETABLE_" + after.upper(), "timetableversion", version, reason=reason)
            return Response(VersionData(version).data)

        return self.write(save)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self.transition(request, "draft", "review")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.transition(request, "review", "approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.transition(request, "review", "draft")

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return self.transition(request, "approved", "published")


class EntryForm(schema(models.Entry, ())):
    def validate(self, values):
        if self.instance and values.get("version", self.instance.version) != self.instance.version:
            raise ValidationError("An entry cannot move to a different timetable version.")
        fields = ("version", "period", "weekday", "subject", "teacher", "room", "notes", "group")
        entry = models.Entry(
            **{
                key: values.get(key, getattr(self.instance, key, None))
                for key in fields
                if key != "notes" or key in values
            }
        )
        entry.pk = getattr(self.instance, "pk", None)
        if entry.version.plan.institution_id != school().pk or entry.version.status != "draft":
            raise Conflict("Only drafts in this institution can be edited.")
        service.validate_slot(entry)
        self.warnings = workload.check(entry)
        self.preference_score = service.preference_score(entry)
        if conflict := service.check_conflicts(entry):
            raise Conflict(f"The lesson has a {conflict} conflict.")
        return values


class Entries(TimetableView):
    queryset = models.Entry.objects.all()
    institution_lookup = "version__plan__institution"
    serializer_class = EntryForm
    permission_map: ClassVar = DRAFT
    filterset_fields = ("version", "teacher", "room", "weekday")

    http_method_names: ClassVar = [*TimetableView.http_method_names, "delete"]
    permission_map: ClassVar = {**DRAFT, "destroy": MANAGE}

    def destroy(self, request, *args, **kwargs):
        def remove():
            entry = self.get_object()
            if entry.version.status != "draft":
                raise Conflict("Only draft lesson entries can be removed.")
            audit(request, "TIMETABLE_ENTRY_REMOVED", "entry", entry)
            entry.delete()
            return Response(status=204)

        return self.write(remove)


ExceptionData = schema(
    models.Exception, ("recorded_by",), ("destination_version", "destination_group")
)


class ExceptionForm(ExceptionData):
    class Meta(ExceptionData.Meta):
        validators = ()

    def validate(self, values):
        entry, day, kind = (values[key] for key in ("entry", "date", "kind"))
        plan = entry.version.plan
        period, teacher, room = (values.get(key) for key in ("period", "teacher", "room"))
        destination = values.get("destination_date") or day
        if entry.weekday != day.weekday() or not any(
            row[0].pk == entry.pk and row[0].version_id == entry.version_id
            for row in service.daily(school(), day)
        ):
            raise ValidationError("Choose a lesson in the published schedule for this date.")
        if models.Exception.objects.filter(entry=entry, date=day).exists():
            raise Conflict("A dated exception already exists for this lesson.")
        if kind != "rescheduled" and values.get("destination_date"):
            raise ValidationError("Only a rescheduling can specify a destination date.")
        if kind == "cancelled":
            if period or teacher or room:
                raise ValidationError("A cancellation has no replacement time, teacher or room.")
            return values
        if kind == "substitute" and (not teacher or teacher == entry.teacher or period or room):
            raise ValidationError("Choose a different teacher for the original period and room.")
        if kind == "rescheduled" and (
            not period or (period == entry.period and destination == day)
        ):
            raise ValidationError("Choose a different date or teaching period.")
        destination_version = entry.version
        group = entry.group
        if kind == "rescheduled":
            destination_version = (
                service.published(school(), destination, destination)
                .filter(
                    plan=plan,
                )
                .first()
            )
            if not destination_version:
                raise ValidationError("Choose a date in a published revision of this timetable.")
            if destination_version.pk != entry.version_id:
                while group:
                    successor = models.TeachingGroup.objects.filter(
                        predecessor=group,
                        effective_version__plan=plan,
                        effective_version__status="published",
                        effective_version__effective_start__lte=destination,
                    ).first()
                    if not successor:
                        break
                    group = successor
                values["destination_version"] = destination_version
                values["destination_group"] = group
        if not service.working_date(plan, destination):
            raise ValidationError("The destination must be a working day without a closure.")
        if (
            kind == "rescheduled"
            and AttendanceSession.objects.filter(
                session=plan.session,
                section=plan.section,
                date=day,
                mode="period",
                subject=entry.subject,
                period__iexact=entry.period.code,
            ).exists()
        ):
            raise Conflict("Attendance already exists. The original lesson cannot be moved.")
        if (
            kind == "rescheduled"
            and AttendanceSession.objects.filter(
                session=plan.session,
                section=plan.section,
                date=destination,
                mode="period",
                subject=entry.subject,
                period__iexact=period.code,
            ).exists()
        ):
            raise Conflict("Attendance already exists for the destination lesson.")
        proposed = models.Entry(
            version=destination_version,
            period=period or entry.period,
            weekday=destination.weekday(),
            subject=entry.subject,
            group=group,
            teacher=teacher or entry.teacher,
            room=room or entry.room,
        )
        service.validate_slot(proposed, destination, destination)
        if service.staff_issue(proposed.teacher, destination, proposed.period):
            raise ValidationError("The replacement teacher is unavailable on this date.")
        if kind == "rescheduled" and service.exam_conflict(proposed, destination):
            raise Conflict("The proposed date, section or room overlaps an examination.")
        for other, other_period, other_teacher, other_room, change in service.daily(
            school(), destination
        ):
            if (destination == day and other.pk == entry.pk) or service.inactive(
                change, destination
            ):
                continue
            effective = models.Entry(
                version=other.version,
                group=other.group,
                period=other_period,
                teacher=other_teacher,
                room=other_room,
            )
            if conflict := service.conflict_kind(proposed, effective):
                raise Conflict(f"The proposed change has a {conflict} conflict.")
        workload.check(proposed, date=destination, omit=(entry.pk, day))
        return values


class Exceptions(TimetableView):
    queryset = models.Exception.objects.all()
    institution_lookup = "entry__version__plan__institution"
    serializer_class = ExceptionForm
    permission_map: ClassVar = {"list": VIEW, "retrieve": VIEW, "create": EXCEPTIONS}
    filterset_fields = ("date", "kind")

    def perform_create(self, serializer):
        row = serializer.save(recorded_by=self.request.user)
        audit(
            self.request,
            "TIMETABLE_EXCEPTION_CREATED",
            "timetableexception",
            row,
            source_version=str(row.entry.version_id),
            destination_version=str(row.destination_version_id or row.entry.version_id),
        )


class Tools(TimetableView):
    permission_map: ClassVar = {"validate": MANAGE, "teachers": VIEW}

    def validate(self, request):
        form = EntryForm(data=request.data)
        form.is_valid(raise_exception=True)
        return Response(
            {"valid": True, "warnings": form.warnings, "preference_score": form.preference_score}
        )

    def teachers(self, request):
        results = (
            TeachingAssignment.objects.filter(
                session__institution=school(),
                active=True,
                user__is_active=True,
            )
            .order_by("user__username")
            .values("user_id", "user__username")
            .distinct()
        )
        return Response([{"id": row["user_id"], "name": row["user__username"]} for row in results])


class RequirementForm(schema(models.SubjectRequirement)):
    def validate(self, values):
        row = self.instance
        session, section, subject = [
            values.get(key, getattr(row, key, None)) for key in ("session", "section", "subject")
        ]
        if {
            session.institution_id,
            section.academic_class.institution_id,
            subject.institution_id,
        } != {school().pk}:
            raise ValidationError("Choose academic records from this institution.")
        minimum = values.get("minimum", getattr(row, "minimum", 0))
        maximum = values.get("maximum", getattr(row, "maximum", 0))
        if not 0 <= minimum <= maximum <= 70:
            raise ValidationError(
                "The weekly maximum must cover the weekly minimum and be at most 70."
            )
        return values


class Requirements(TimetableView):
    queryset = models.SubjectRequirement.objects.all()
    serializer_class = RequirementForm
    permission_map: ClassVar = CONFIG
    filterset_fields = ("session", "section", "subject")


class SlotQuery(serializers.Serializer):
    version = serializers.UUIDField()
    subject = serializers.UUIDField()
    teacher = serializers.UUIDField()
    room = serializers.UUIDField(required=False)
    weekday = serializers.IntegerField(min_value=0, max_value=6, required=False)
    group = serializers.UUIDField(required=False)


class Suggestions(TimetableView):
    permission_map: ClassVar = {"list": VIEW}

    def list(self, request):
        form = SlotQuery(data=request.query_params)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        version = models.Version.objects.filter(
            pk=values["version"], plan__institution=school()
        ).first()
        if not version or version.status != "draft":
            raise ValidationError("Select a draft timetable.")
        from apps.academics.models import Subject
        from apps.accounts.models import User

        subject = Subject.objects.filter(pk=values["subject"], institution=school()).first()
        teacher = User.objects.filter(pk=values["teacher"], is_active=True).first()
        room = (
            models.Room.objects.filter(pk=values["room"], institution=school()).first()
            if "room" in values
            else None
        )
        if not subject or not teacher or ("room" in values and not room):
            raise ValidationError("Choose a valid subject, teacher and room.")
        group = models.TeachingGroup.objects.filter(
            pk=values.get("group"), institution=school()
        ).first()
        if "group" in values and not group:
            raise ValidationError("Choose a valid teaching group.")
        days = [values["weekday"]] if "weekday" in values else version.plan.shift.weekdays
        answer = []
        for period in version.plan.shift.periods.filter(teaching=True).order_by("starts_at"):
            for day in days:
                candidate = models.Entry(
                    version=version,
                    subject=subject,
                    teacher=teacher,
                    room=room,
                    group=group,
                    weekday=day,
                    period=period,
                )
                try:
                    service.validate_slot(candidate)
                    warnings = workload.check(candidate)
                except ValidationError:
                    continue
                if not service.check_conflicts(candidate):
                    answer.append(
                        {
                            "weekday": day,
                            "period": period.pk,
                            "label": period.name,
                            "starts_at": period.starts_at,
                            "ends_at": period.ends_at,
                            "preference_score": service.preference_score(candidate),
                            "warnings": warnings,
                        }
                    )
        return Response(sorted(answer, key=lambda row: -row["preference_score"]))


class Workload(TimetableView):
    queryset = models.WorkloadPolicy.objects.all()
    serializer_class = schema(models.WorkloadPolicy)
    permission_map: ClassVar = CONFIG
    filterset_fields = ("teacher",)

    def save_policy(self, serializer, operation):
        row = serializer.instance
        values = serializer.validated_data
        teacher, start, end = [
            values.get(key, getattr(row, key, None))
            for key in ("teacher", "effective_start", "effective_end")
        ]
        if not TeachingAssignment.objects.filter(
            user=teacher, session__institution=school()
        ).exists():
            raise ValidationError("Choose an assigned teacher.")
        if start > end:
            raise ValidationError("Choose an ordered range of effective dates.")
        if (
            self.get_queryset()
            .exclude(pk=getattr(row, "pk", None))
            .filter(teacher=teacher, effective_start__lte=end, effective_end__gte=start)
            .exists()
        ):
            raise Conflict("Choose a date range outside the existing teacher workload rules.")
        operation(serializer)

    def perform_create(self, serializer):
        self.save_policy(serializer, super().perform_create)

    def perform_update(self, serializer):
        self.save_policy(serializer, super().perform_update)


class GroupForm(schema(models.TeachingGroup, read_only=("predecessor", "effective_version"))):
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and "accounts.view_students" not in permission_codes(request.user):
            fields.pop("enrollments", None)
        return fields

    def validate(self, values):
        row = self.instance
        session, section, subject = [
            values.get(key, getattr(row, key, None)) for key in ("session", "section", "subject")
        ]
        if row and row.entry_set.exclude(version__status="draft").exists():
            raise Conflict("Membership is fixed after timetable submission.")
        if {
            session.institution_id,
            section.academic_class.institution_id,
            subject.institution_id,
        } != {school().pk}:
            raise ValidationError("Choose records from this institution.")
        curriculum = service.curriculum_for(session, section.academic_class, subject)
        if not curriculum or not curriculum.active or curriculum.mandatory or not subject.active:
            raise ValidationError("Select an active optional subject in the section curriculum.")
        if (row is None or row.predecessor_id is None) and models.TeachingGroup.objects.filter(
            session=session,
            section=section,
            subject=subject,
            predecessor__isnull=True,
        ).exclude(pk=row.pk if row else None).exists():
            raise ValidationError("The fields session, section, subject must make a unique set.")
        enrollment = values.get("enrollments", list(row.enrollments.all()) if row else [])
        if any(
            item.section_id != section.pk or item.session_id != session.pk for item in enrollment
        ):
            raise ValidationError("Group members must be enrolled in this session and section.")
        if row and row.effective_version_id:
            anchor = row.effective_version
            if (session.pk, section.pk, subject.pk) != (
                row.session_id,
                row.section_id,
                row.subject_id,
            ):
                raise ValidationError("A successor roster cannot change its academic scope.")
            allowed = service.eligible_group_members(
                row, anchor.effective_start, anchor.effective_end
            )
            if allowed.filter(pk__in=[item.pk for item in enrollment]).count() != len(enrollment):
                raise ValidationError("Choose students enrolled for the successor revision dates.")
        capacity = values.get("capacity", getattr(row, "capacity", None))
        if capacity is not None and len(enrollment) > capacity:
            raise ValidationError("Membership exceeds group capacity.")
        return values


class Groups(TimetableView):
    queryset = models.TeachingGroup.objects.all()
    serializer_class = GroupForm
    filterset_fields = ("session", "section", "subject")
    permission_map: ClassVar = {**DRAFT, "successor": (MANAGE, "accounts.view_students")}

    @action(detail=True, methods=["post"])
    def successor(self, request, pk=None):
        def create_successor():
            previous = self.get_object()
            identifier = serializers.UUIDField().run_validation(request.data.get("version"))
            version = models.Version.objects.filter(
                pk=identifier,
                plan__institution=school(),
                plan__session=previous.session,
                plan__section=previous.section,
                status="draft",
                effective_start__gt=today(),
            ).first()
            if not version or not version.entries.filter(group=previous).exists():
                raise ValidationError("Choose a future draft containing this roster.")
            if not previous.entry_set.filter(
                version__plan=version.plan,
                version__status="published",
                version__effective_start__lt=version.effective_start,
            ).exists():
                raise ValidationError("The roster must have an earlier publication in this plan.")
            if models.TeachingGroup.objects.filter(predecessor=previous).exists():
                raise Conflict("A successor already exists for this roster.")
            current = models.TeachingGroup.objects.create(
                institution=previous.institution,
                session=previous.session,
                section=previous.section,
                subject=previous.subject,
                name=previous.name,
                code=previous.code,
                capacity=previous.capacity,
                predecessor=previous,
                effective_version=version,
            )
            eligible = service.eligible_group_members(
                current,
                version.effective_start,
                version.effective_end,
            )
            current.enrollments.set(previous.enrollments.filter(pk__in=eligible))
            version.entries.filter(group=previous).update(group=current)
            audit(
                request,
                "TIMETABLE_GROUP_SUCCESSOR_CREATED",
                "teachinggroup",
                current,
                predecessor=str(previous.pk),
                version=str(version.pk),
            )
            return Response(self.get_serializer(current).data, status=201)

        return self.write(create_successor)


class GroupMembers(TimetableView):
    permission_map: ClassVar = {"list": (MANAGE, "accounts.view_students")}

    def list(self, request):
        key = serializers.UUIDField().run_validation(request.query_params.get("section"))
        session = serializers.UUIDField().run_validation(request.query_params.get("session"))
        query = (
            StudentEnrollment.objects.filter(
                session_id=session,
                session__institution=school(),
                section_id=key,
                status="active",
            )
            .select_related("student")
            .order_by("roll_number", "pk")
        )
        page = self.paginate_queryset(query)
        return self.get_paginated_response(
            [
                {
                    "id": row.pk,
                    "name": f"{row.roll_number} · {row.student.first_name} {row.student.last_name}",
                }
                for row in page
            ]
        )
