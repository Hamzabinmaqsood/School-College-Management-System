from typing import ClassVar

from django.db import IntegrityError, transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from apps.accounts.access import authority_lock, require
from apps.accounts.authentication import audit
from apps.accounts.models import Institution
from apps.licensing.permissions import LicensedBusinessWrites


class Conflict(APIException):
    status_code = 409
    default_detail = "The change conflicts with an existing record."


def school(*, lock=False):
    query = Institution.objects.select_for_update() if lock else Institution.objects
    instance = query.first()
    if not instance:
        raise serializers.ValidationError("Complete institution setup first.")
    return instance


class AcademicAccess(BasePermission):
    def has_permission(self, request, view):
        if request.user.password_change_required:
            return False
        permission = view.permission_map.get(getattr(view, "action", None))
        if not permission:
            return False
        if request.method not in SAFE_METHODS:
            authority_lock()
        require(request.user, *([permission] if isinstance(permission, str) else permission))
        return True


class RecordsView(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, AcademicAccess, LicensedBusinessWrites)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    http_method_names = ("get", "post", "patch", "head", "options")
    permission_map: ClassVar = {}
    lookup_value_regex = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
    license_feature = "academics"
    institution_lookup = "institution"
    ordering = ("id",)

    def get_queryset(self):
        return super().get_queryset().filter(**{self.institution_lookup: school()})

    def create(self, request, *args, **kwargs):
        return self.write(super().create, request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.write(super().partial_update, request, *args, **kwargs)

    @staticmethod
    def write(operation, *args, **kwargs):
        try:
            with transaction.atomic():
                school(lock=True)
                return operation(*args, **kwargs)
        except IntegrityError as exc:
            raise Conflict() from exc

    def perform_create(self, serializer):
        fields = {"institution": school()} if self.institution_lookup == "institution" else {}
        record = serializer.save(**fields)
        audit(self.request, "RECORD_CREATED", record._meta.model_name, record)

    def perform_update(self, serializer):
        record = serializer.save()
        audit(
            self.request,
            "RECORD_UPDATED",
            record._meta.model_name,
            record,
            fields=sorted(serializer.validated_data),
        )
