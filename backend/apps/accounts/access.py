from django.apps import apps
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.academics.catalog import ACADEMIC_PERMISSIONS
from apps.attendance.catalog import ATTENDANCE_PERMISSIONS
from apps.examinations.catalog import EXAM_PERMISSIONS
from apps.fees.catalog import FEE_PERMISSIONS
from apps.hr.catalog import HR_PERMISSIONS
from apps.timetables.catalog import TIMETABLE_PERMISSIONS

from .models import Institution, Role, User

ADMIN = "institution-administrator"
CATALOG = {
    "Dashboard": {"view": "accounts.view_dashboard"},
    "Institution": {"view": "accounts.view_institution", "update": "accounts.change_institution"},
    "Users": {
        "view": "accounts.view_user",
        "details": "accounts.view_user_details",
        "add": "accounts.add_user",
        "update": "accounts.change_user",
        "suspend": "accounts.suspend_user",
        "manage": "accounts.assign_roles",
        "verify": "accounts.reset_user_password",
    },
    "Roles": {
        "view": "auth.view_group",
        "add": "auth.add_group",
        "update": "auth.change_group",
        "delete": "auth.delete_group",
        "manage": "accounts.manage_role_permissions",
    },
    "Subscription": {
        "view": "accounts.view_subscription",
        "manage": "accounts.manage_subscription",
    },
    "Audit Logs": {"view": "audit.view_auditevent"},
    "Settings": {"view": "accounts.view_institution"},
    **ACADEMIC_PERMISSIONS,
    **ATTENDANCE_PERMISSIONS,
    **FEE_PERMISSIONS,
    **EXAM_PERMISSIONS,
    **HR_PERMISSIONS,
    **TIMETABLE_PERMISSIONS,
}
RESERVED = {
    "Students": "students",
    "Admissions": "admissions",
    "Teachers": "teachers",
    "Staff": "staff",
    "Academic Sessions": "sessions",
    "Classes": "classes",
    "Sections": "sections",
    "Subjects": "subjects",
    "Attendance": "attendance",
    "Fees": "fees",
    "Accounts": "accounts",
    "Payroll": "payroll",
    "Examinations": "examinations",
    "Timetable": "timetable",
    "Library": "library",
    "Transport": "transport",
    "Reports": "reports",
    "Backups": "backups",
    "Income": "income",
    "Expenses": "expenses",
}
TEMPLATES = {
    ADMIN: "Institution Administrator",
    "principal": "Principal",
    "accountant": "Accountant",
    "teacher": "Teacher",
    "receptionist": "Receptionist",
    "examination-officer": "Examination Officer",
    "attendance-officer": "Attendance Officer",
    "librarian": "Librarian",
    "transport-manager": "Transport Manager",
    "hr-officer": "HR Officer",
}


def catalog():
    return [
        {"module": module, "actions": actions, "reserved": False}
        for module, actions in CATALOG.items()
    ] + [
        {"module": module, "actions": {"view": f"accounts.view_{slug}"}, "reserved": True}
        for module, slug in RESERVED.items()
        if module
        not in (
            ACADEMIC_PERMISSIONS
            | ATTENDANCE_PERMISSIONS
            | FEE_PERMISSIONS
            | EXAM_PERMISSIONS
            | HR_PERMISSIONS
            | TIMETABLE_PERMISSIONS
        )
    ]


def catalog_codes():
    return {code for item in catalog() for code in item["actions"].values()}


def codes(query):
    return {
        f"{app}.{code}" for app, code in query.values_list("content_type__app_label", "codename")
    }


def permission_codes(user, *, include_inactive=False):
    if not user.is_active and not include_inactive:
        return set()
    if user.is_superuser:
        return catalog_codes()
    groups = user.groups.filter(role__active=True)
    return (
        codes(user.user_permissions) | codes(Permission.objects.filter(group__in=groups))
    ) & catalog_codes()


class LocalBackend(ModelBackend):
    def _get_group_permissions(self, user_obj):
        return super()._get_group_permissions(user_obj).filter(group__role__active=True)


def require(user, *required):
    if not User.objects.filter(
        pk=user.pk,
        is_active=True,
        password_change_required=False,
        session_version=user.session_version,
    ).exists() or (not set(required) <= permission_codes(user)):
        raise PermissionDenied("You do not have permission for this operation.")


def authority_lock():
    ContentType.objects.select_for_update().get(app_label="accounts", model="role")


def administrators():
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__role__key=ADMIN, groups__role__active=True))
        .exclude(password__startswith="!")
    )


def guard_admin_loss(target):
    if (
        administrators().filter(pk=target.pk).exists()
        and not administrators().exclude(pk=target.pk).exists()
    ):
        raise PermissionDenied("The installation must retain an active administrator.")


def permission_rows(requested):
    rows = Permission.objects.filter(codename__in=[code.split(".", 1)[1] for code in requested])
    return [
        row
        for row in rows.select_related("content_type")
        if f"{row.content_type.app_label}.{row.codename}" in requested
    ]


@transaction.atomic
def seed_roles():
    from apps.audit.models import AuditEvent

    authority_lock()
    targets = {
        "institution": Institution,
        "user": User,
        "group": Group,
        "auditevent": AuditEvent,
    }
    for key in catalog_codes():
        app, code = key.split(".", 1)
        model_name = code.split("_", 1)[-1]
        try:
            target = apps.get_model(app, model_name)
        except LookupError:
            target = targets.get(model_name, Role)
        if target._meta.app_label != app:
            target = Role
        content_type = ContentType.objects.get_for_model(target)
        if not Permission.objects.filter(content_type__app_label=app, codename=code).exists():
            Permission.objects.create(
                content_type=content_type, codename=code, name=code.replace("_", " ").capitalize()
            )
    for key, label in TEMPLATES.items():
        if Role.objects.filter(key=key).exists():
            continue
        group = Group.objects.create(
            name=label
            if not Group.objects.filter(name__iexact=label).exists()
            else f"{label} ({key} system)"
        )
        role = Role.objects.create(
            group=group, key=key, description=f"System template for {label}.", system=True
        )
        initial = catalog_codes() if role.key == ADMIN else {"accounts.view_dashboard"}
        if role.key == "teacher":
            initial.add("accounts.view_own_timetable")
        group.permissions.set(permission_rows(initial))
