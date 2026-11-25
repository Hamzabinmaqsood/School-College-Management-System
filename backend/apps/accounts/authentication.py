import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.views.csrf import csrf_failure
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent

from .access import permission_codes
from .models import Institution, LoginAttempt, Role, User


def audit(request, action, resource, target=None, **metadata):
    AuditEvent.objects.create(
        acting_user=request.user if request.user.is_authenticated else None,
        action=action,
        resource_type=resource,
        resource_id=str(target.pk) if target else "",
        request_id=str(getattr(request, "request_id", ""))[:128],
        sanitized_metadata=metadata,
    )


def error(status, code, message):
    return Response({"code": code, "message": message, "details": {}}, status=status)


def csrf_rejected(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"code": "CSRF_FAILED", "message": "Refresh the page and try again.", "details": {}},
            status=403,
        )
    return csrf_failure(request, reason=reason)


def branding(institution):
    if not institution:
        return None
    return {
        "id": str(institution.pk),
        "name": institution.name,
        "code": institution.code,
        "language": institution.language,
        "currency": institution.currency,
        "timezone": institution.timezone,
        "logo_url": (
            f"/api/v1/institution/logo/?v={int(institution.updated_at.timestamp() * 1_000_000)}"
            if institution.logo_png
            else None
        ),
    }


def current_user(request):
    user = request.user
    roles = (
        Role.objects.filter(group__user=user, active=True)
        .select_related("group")
        .order_by("group__name")
    )
    return {
        "id": str(user.pk),
        "username": user.username,
        "full_name": user.get_full_name(),
        "email": user.email,
        "active": user.is_active,
        "password_change_required": user.password_change_required,
        "roles": [{"id": str(role.pk), "name": role.group.name} for role in roles],
        "permissions": sorted(permission_codes(user)),
        "institution": branding(Institution.objects.first()),
        "session": {
            "idle_timeout_seconds": settings.APP_SESSION_IDLE,
            "absolute_timeout_seconds": settings.APP_SESSION_MAX,
        },
    }


def check_password_strength(password, user):
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages}) from exc


def allowed_attempt(request, username):
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.APP_LOGIN_WINDOW)
    address = request.META.get("REMOTE_ADDR", "")
    LoginAttempt.objects.filter(window__lt=cutoff - timedelta(days=1)).delete()
    for value, limit in [
        (f"ip:{address}", settings.APP_LOGIN_IP_LIMIT),
        (f"user:{username.casefold()}", settings.APP_LOGIN_LIMIT),
    ]:
        key = salted_hmac("accounts.login-limit", value, algorithm="sha256").hexdigest()
        entry, _ = LoginAttempt.objects.select_for_update().get_or_create(
            key=key, defaults={"window": now}
        )
        if entry.window <= cutoff:
            entry.window, entry.count = now, 0
        if entry.count >= limit:
            return False
        entry.count += 1
        entry.save(update_fields=["window", "count"])
    return True


class Credentials(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class PasswordChange(serializers.Serializer):
    current_password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class CsrfView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response(
            {
                "csrf_token": get_token(request),
                "institution": branding(Institution.objects.first()),
            },
            headers={"Cache-Control": "no-store"},
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        fields = Credentials(data=request.data)
        fields.is_valid(raise_exception=True)
        username = User.normalize_username(fields.validated_data["username"])
        if not allowed_attempt(request, username):
            audit(request, "LOGIN_LIMITED", "authentication")
            response = error(429, "LOGIN_LIMITED", "Too many sign-in attempts. Try again later.")
            response["Retry-After"] = str(settings.APP_LOGIN_WINDOW)
            return response
        user = authenticate(
            request._request, username=username, password=fields.validated_data["password"]
        )
        if user is None:
            audit(request, "LOGIN_FAILED", "authentication")
            return error(401, "INVALID_CREDENTIALS", "The username or password is incorrect.")
        login(request._request, user)
        request.user = user
        now = int(time.time())
        request.session["app_started"] = now
        request.session["app_last_seen"] = now
        request.session.set_expiry(settings.APP_SESSION_MAX)
        audit(request, "LOGIN_SUCCEEDED", "user", user)
        return Response(current_user(request), headers={"Cache-Control": "no-store"})


class MeView(APIView):
    def get(self, request):
        return Response(current_user(request), headers={"Cache-Control": "no-store"})


class LogoutView(APIView):
    def post(self, request):
        audit(request, "LOGOUT", "user", request.user)
        logout(request._request)
        return Response(status=204)


class ChangePasswordView(APIView):
    def post(self, request):
        fields = PasswordChange(data=request.data)
        fields.is_valid(raise_exception=True)
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.check_password(fields.validated_data["current_password"]):
            return error(400, "INVALID_PASSWORD", "The current password is incorrect.")
        password = fields.validated_data["new_password"]
        if user.check_password(password):
            return error(400, "PASSWORD_UNCHANGED", "Choose a different password.")
        check_password_strength(password, user)
        user.set_password(password)
        user.password_change_required = False
        user.save(update_fields=["password", "password_change_required", "updated_at"])
        update_session_auth_hash(request._request, user)
        request.user = user
        audit(request, "PASSWORD_CHANGED", "user", user)
        return Response(current_user(request), headers={"Cache-Control": "no-store"})
