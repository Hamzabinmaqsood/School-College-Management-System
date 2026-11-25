from django.db import transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.academics.catalog import ACADEMIC_PERMISSIONS
from apps.accounts.access import administrators, authority_lock, permission_codes, require
from apps.accounts.authentication import error
from apps.accounts.institution import ManagementView
from apps.accounts.management_api import paginate
from apps.accounts.models import User
from apps.attendance.catalog import ATTENDANCE_PERMISSIONS
from apps.examinations.catalog import EXAM_PERMISSIONS
from apps.fees.catalog import FEE_PERMISSIONS
from apps.hr.catalog import HR_PERMISSIONS

from .protocol import MAX_TOKEN, LicenseError, verify
from .service import activate, installation, license_status, trusted_keys

VIEW = "accounts.view_subscription"
MANAGE = "accounts.manage_subscription"


def can_bootstrap(user, identity):
    return bool(
        identity
        and not identity.current_id
        and not identity.activations.exists()
        and administrators().filter(pk=user.pk).exists()
    )


def can_manage(user, identity):
    return MANAGE in permission_codes(user) or can_bootstrap(user, identity)


def require_details(user, identity):
    if VIEW not in permission_codes(user) and not can_manage(user, identity):
        raise PermissionDenied("You do not have access to subscription information.")


class StatusView(ManagementView):
    def get(self, request):
        grants = permission_codes(request.user)
        academic_codes = {
            code
            for actions in (
                ACADEMIC_PERMISSIONS
                | ATTENDANCE_PERMISSIONS
                | FEE_PERMISSIONS
                | EXAM_PERMISSIONS
                | HR_PERMISSIONS
            ).values()
            for code in actions.values()
        }
        if not grants.intersection({VIEW, MANAGE, "accounts.view_dashboard"} | academic_codes):
            require_details(request.user, installation())
        status = license_status(request)
        status["available_features"] = (
            status.get("license", {}).get("features", []) if status.get("license") else []
        )
        if not grants & {VIEW, MANAGE}:
            status.pop("license")
        return Response(status, headers={"Cache-Control": "no-store"})


class InstallationView(ManagementView):
    def get(self, request):
        identity = installation()
        require_details(request.user, identity)
        if not identity:
            return error(
                409,
                "INSTITUTION_REQUIRED",
                "Complete institution setup before activating a license.",
            )
        return Response(
            {
                "installation_id": identity.installation_id,
                "institution_id": identity.institution_id,
                "institution_name": identity.institution.name,
                "can_activate": can_manage(request.user, identity),
            }
        )


class ActivateView(ManagementView):
    @transaction.atomic
    def post(self, request):
        authority_lock()
        if not User.objects.filter(
            pk=request.user.pk,
            is_active=True,
            password_change_required=False,
            session_version=request.user.session_version,
        ).exists():
            raise PermissionDenied("You do not have permission to activate licenses.")
        identity = installation(lock=True)
        if not can_manage(request.user, identity):
            require(request.user, MANAGE)
        if not identity:
            return error(
                409,
                "INSTITUTION_REQUIRED",
                "Complete institution setup before activating a license.",
            )
        if not hasattr(request.data, "get"):
            return error(400, "INVALID_LICENSE", "Submit a license file or activation code.")
        upload = request.FILES.get("file")
        token = request.data.get("token")
        if upload:
            if token or upload.size > MAX_TOKEN + 2:
                return error(
                    400, "INVALID_LICENSE", "Submit one license file no larger than 16 KB."
                )
            try:
                token = upload.read(MAX_TOKEN + 3).decode("ascii")
            except UnicodeError:
                return error(
                    400, "INVALID_LICENSE", "The license file must contain an activation code."
                )
        if not isinstance(token, str) or len(token) > MAX_TOKEN + 2 or not token.strip():
            return error(
                400,
                "INVALID_LICENSE",
                "Submit a license file or activation code no larger than 16 KB.",
            )
        result, failure = activate(identity, request, token.strip())
        if failure:
            return error(
                409
                if failure.code in {"LICENSE_REPLAY", "CLOCK_REVIEW_REQUIRED", "OLDER_LICENSE"}
                else 400,
                failure.code,
                str(failure),
            )
        return Response(result, status=200 if result["duplicate"] else 201)


class HistoryView(ManagementView):
    def get(self, request):
        identity = installation()
        require_details(request.user, identity)
        keys = trusted_keys()
        activations = identity.activations.order_by("-activated_at", "-pk") if identity else []
        valid = []
        for activation in activations:
            try:
                payload = verify(activation.token, keys)
            except LicenseError:
                continue
            if payload["institution_id"] != str(identity.institution_id) or payload[
                "license_id"
            ] != str(activation.pk):
                continue
            valid.append(
                payload
                | {
                    "activated_at": activation.activated_at,
                    "current": activation.pk == identity.current_id,
                }
            )
        return paginate(request, valid, lambda item: item)
