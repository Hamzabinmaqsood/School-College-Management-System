from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from apps.audit.models import AuditEvent

from .access import (
    ADMIN,
    administrators,
    authority_lock,
    catalog,
    catalog_codes,
    codes,
    guard_admin_loss,
    permission_codes,
    permission_rows,
    require,
)
from .authentication import audit, check_password_strength
from .institution import ManagementView
from .models import Role, User


class Pagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


def paginate(request, queryset, serialize, **extra):
    page = Pagination()
    items = page.paginate_queryset(queryset, request)
    response = page.get_paginated_response([serialize(item) for item in items])
    response.data.update(extra)
    return response


class UserFields(serializers.ModelSerializer):
    password = serializers.CharField(
        max_length=256, trim_whitespace=False, write_only=True, required=False
    )
    role_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=100)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "password", "role_ids")

    def validate_username(self, value):
        return User.normalize_username(value)


class PasswordInput(serializers.Serializer):
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


def user_record(user):
    return {
        "id": str(user.pk),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name(),
        "email": user.email,
        "phone": user.phone,
        "active": user.is_active,
        "last_login": user.last_login,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "password_change_required": user.password_change_required,
        "roles": [
            {"id": str(role.pk), "name": role.group.name, "active": role.active}
            for role in Role.objects.filter(group__user=user)
            .select_related("group")
            .order_by("group__name")
        ],
    }


def guard_target(actor, target):
    if actor.is_superuser:
        if target.is_superuser and actor.pk != target.pk:
            raise PermissionDenied("Manage superusers using local administration.")
        return
    if (
        target.groups.filter(role__key=ADMIN).exists()
        and not administrators().filter(pk=actor.pk).exists()
    ):
        raise PermissionDenied("Only installation administrators can manage this account.")
    if (
        target.is_superuser
        or target.is_staff
        or not permission_codes(target, include_inactive=True) <= permission_codes(actor)
    ):
        raise PermissionDenied("You cannot manage this account.")


def assign_roles(request, target, ids):
    actor = request.user
    require(actor, "accounts.assign_roles")
    if actor.pk == target.pk:
        raise PermissionDenied("Your own role assignments cannot be changed here.")
    roles = list(Role.objects.filter(pk__in=ids))
    if len(roles) != len(set(ids)) or any(not role.active for role in roles):
        raise serializers.ValidationError({"role_ids": "Select existing active roles."})
    current = Role.objects.filter(group__user=target)
    is_admin = current.filter(key=ADMIN).exists()
    becomes_admin = any(role.key == ADMIN for role in roles)
    if is_admin != becomes_admin and not administrators().filter(pk=actor.pk).exists():
        raise PermissionDenied(
            "Only installation administrators can change administrator membership."
        )
    if is_admin and not becomes_admin:
        guard_admin_loss(target)
    grants = set().union(*(codes(role.group.permissions) for role in roles))
    if not grants <= permission_codes(actor):
        raise PermissionDenied("You cannot assign a role with permissions you do not possess.")
    target.groups.remove(*current.values_list("group_id", flat=True))
    target.groups.add(*(role.group_id for role in roles))
    audit(request, "ROLES_ASSIGNED", "user", target, role_ids=[str(role.pk) for role in roles])


class UserList(ManagementView):
    def get(self, request):
        require(request.user, "accounts.view_user")
        users = User.objects.order_by("username", "pk")
        summary = {"total": users.count(), "active": users.filter(is_active=True).count()}
        summary["inactive"] = summary["total"] - summary["active"]
        query = request.query_params.get("search", "").strip()[:150]
        status = request.query_params.get("active")
        role = request.query_params.get("role")
        if query:
            users = users.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        if status in ("true", "false"):
            users = users.filter(is_active=(status == "true"))
        if role:
            role_id = serializers.UUIDField().run_validation(role)
            users = users.filter(groups__role__pk=role_id)
        return paginate(request, users, user_record, summary=summary)

    @transaction.atomic
    def post(self, request):
        authority_lock()
        require(request.user, "accounts.add_user")
        fields = UserFields(data=request.data)
        fields.is_valid(raise_exception=True)
        values = dict(fields.validated_data)
        password = values.pop("password", None)
        ids = values.pop("role_ids", [])
        if not password:
            raise serializers.ValidationError({"password": "A temporary password is required."})
        target = User(**values, password_change_required=True)
        check_password_strength(password, target)
        target.set_password(password)
        target.save()
        audit(request, "USER_CREATED", "user", target)
        if ids:
            assign_roles(request, target, ids)
        return Response(user_record(target), status=201)


class UserDetail(ManagementView):
    def get(self, request, pk):
        require(request.user, "accounts.view_user_details")
        return Response(user_record(get_object_or_404(User, pk=pk)))

    @transaction.atomic
    def patch(self, request, pk):
        authority_lock()
        target = get_object_or_404(User.objects.select_for_update(), pk=pk)
        guard_target(request.user, target)
        fields = UserFields(target, data=request.data, partial=True)
        fields.is_valid(raise_exception=True)
        values = dict(fields.validated_data)
        ids = values.pop("role_ids", None)
        if "password" in values:
            raise serializers.ValidationError({"password": "Use the password reset operation."})
        if values:
            require(request.user, "accounts.change_user")
            for key, value in values.items():
                setattr(target, key, value)
            target.save(update_fields=[*values, "updated_at"])
            audit(request, "USER_UPDATED", "user", target, fields=sorted(values))
        if ids is not None:
            assign_roles(request, target, ids)
        return Response(user_record(target))


class UserPermissions(ManagementView):
    def get(self, request, pk):
        require(request.user, "accounts.view_user_details")
        return Response({"permissions": sorted(permission_codes(get_object_or_404(User, pk=pk)))})


class UserOperation(ManagementView):
    operation = ""

    @transaction.atomic
    def post(self, request, pk):
        authority_lock()
        permission = (
            "accounts.reset_user_password" if self.operation == "reset" else "accounts.suspend_user"
        )
        require(request.user, permission)
        target = get_object_or_404(User.objects.select_for_update(), pk=pk)
        guard_target(request.user, target)
        if target.pk == request.user.pk:
            raise PermissionDenied(
                "Use your own password page. Account status requires another administrator."
            )
        if self.operation == "reset":
            fields = PasswordInput(data=request.data)
            fields.is_valid(raise_exception=True)
            password = fields.validated_data["password"]
            check_password_strength(password, target)
            target.set_password(password)
            target.password_change_required = True
            target.save(update_fields=["password", "password_change_required", "updated_at"])
            audit(request, "PASSWORD_RESET", "user", target)
        else:
            active = self.operation == "activate"
            if target.is_active != active:
                if not active:
                    guard_admin_loss(target)
                    target.session_version += 1
                target.is_active = active
                target.save(update_fields=["is_active", "session_version", "updated_at"])
                audit(request, "USER_ACTIVATED" if active else "USER_DEACTIVATED", "user", target)
        return Response(user_record(target))


class RoleFields(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=400, allow_blank=True, required=False)
    active = serializers.BooleanField(required=False)


def role_record(role):
    return {
        "id": str(role.pk),
        "name": role.group.name,
        "description": role.description,
        "key": role.key,
        "active": role.active,
        "system": role.system,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
        "member_count": role.group.user_set.count(),
    }


def guard_role(actor, role):
    if role.key == ADMIN or not codes(role.group.permissions) <= permission_codes(actor):
        raise PermissionDenied("This role is protected or contains permissions you cannot manage.")


def ensure_group_name(name, existing=None):
    groups = Group.objects.filter(name__iexact=name)
    if existing:
        groups = groups.exclude(pk=existing.pk)
    if groups.exists():
        raise serializers.ValidationError({"name": "This role name is already in use."})


class RoleList(ManagementView):
    def get(self, request):
        require(request.user, "auth.view_group")
        roles = Role.objects.select_related("group").order_by("group__name", "pk")
        if query := request.query_params.get("search"):
            roles = roles.filter(group__name__icontains=query[:150])
        if (active := request.query_params.get("active")) in ("true", "false"):
            roles = roles.filter(active=(active == "true"))
        if (system := request.query_params.get("system")) in ("true", "false"):
            roles = roles.filter(system=(system == "true"))
        return paginate(request, roles, role_record)

    @transaction.atomic
    def post(self, request):
        authority_lock()
        require(request.user, "auth.add_group")
        fields = RoleFields(data=request.data)
        fields.is_valid(raise_exception=True)
        values = dict(fields.validated_data)
        name = values.pop("name")
        ensure_group_name(name)
        role = Role.objects.create(group=Group.objects.create(name=name), **values)
        audit(request, "ROLE_CREATED", "role", role)
        return Response(role_record(role), status=201)


class RoleDetail(ManagementView):
    def get(self, request, pk):
        require(request.user, "auth.view_group")
        role = get_object_or_404(Role, pk=pk)
        result = role_record(role)
        if "accounts.view_user" in permission_codes(request.user):
            members = role.group.user_set.order_by("username", "pk")
            result["members"] = [
                {"id": str(user.pk), "username": user.username} for user in members[:100]
            ]
        return Response(result)

    @transaction.atomic
    def patch(self, request, pk):
        authority_lock()
        require(request.user, "auth.change_group")
        role = get_object_or_404(Role, pk=pk)
        guard_role(request.user, role)
        fields = RoleFields(data=request.data, partial=True)
        fields.is_valid(raise_exception=True)
        values = dict(fields.validated_data)
        if "name" in values:
            ensure_group_name(values["name"], role.group)
            role.group.name = values.pop("name")
            role.group.save(update_fields=["name"])
        for key, value in values.items():
            setattr(role, key, value)
        role.save(update_fields=[*values, "updated_at"])
        audit(request, "ROLE_UPDATED", "role", role, fields=sorted(fields.validated_data))
        return Response(role_record(role))

    @transaction.atomic
    def delete(self, request, pk):
        authority_lock()
        require(request.user, "auth.delete_group")
        role = get_object_or_404(Role, pk=pk)
        guard_role(request.user, role)
        if role.system or role.group.user_set.exists():
            raise serializers.ValidationError("Only unassigned custom roles can be deleted.")
        audit(request, "ROLE_DELETED", "role", role)
        role.group.delete()
        return Response(status=204)


class CatalogView(ManagementView):
    def get(self, request):
        require(request.user, "auth.view_group")
        return Response(catalog())


class RolePermissions(ManagementView):
    def get(self, request, pk):
        require(request.user, "auth.view_group")
        role = get_object_or_404(Role, pk=pk)
        return Response(
            {
                "permissions": sorted(codes(role.group.permissions)),
                "editable": role.key != ADMIN
                and "accounts.manage_role_permissions" in permission_codes(request.user)
                and codes(role.group.permissions) <= permission_codes(request.user),
            }
        )

    @transaction.atomic
    def put(self, request, pk):
        authority_lock()
        require(request.user, "accounts.manage_role_permissions")
        role = get_object_or_404(Role, pk=pk)
        guard_role(request.user, role)
        submitted = serializers.ListField(
            child=serializers.CharField(max_length=120), max_length=300
        )
        fields = serializers.DictField(child=submitted)
        values = fields.run_validation(request.data)
        keys = set(submitted.run_validation(values.get("permissions")))
        if not keys <= catalog_codes():
            raise serializers.ValidationError({"permissions": "Unknown permission."})
        if not keys <= permission_codes(request.user):
            raise PermissionDenied("You cannot grant permissions you do not possess.")
        rows = permission_rows(keys)
        if len(rows) != len(keys):
            raise serializers.ValidationError(
                {"permissions": "Run seed_roles to initialize the catalog."}
            )
        previous = codes(role.group.permissions)
        role.group.permissions.set(rows)
        role.save(update_fields=["updated_at"])
        audit(
            request,
            "PERMISSIONS_CHANGED",
            "role",
            role,
            added=sorted(keys - previous),
            removed=sorted(previous - keys),
        )
        return Response({"permissions": sorted(keys), "editable": True})


class AuditList(ManagementView):
    def get(self, request):
        require(request.user, "audit.view_auditevent")
        events = AuditEvent.objects.select_related("acting_user").order_by("-timestamp", "-pk")
        if query := request.query_params.get("search"):
            events = events.filter(
                Q(action__icontains=query[:128])
                | Q(resource_type__icontains=query[:128])
                | Q(resource_id__icontains=query[:128])
                | Q(request_id__icontains=query[:128])
            )
        if action := request.query_params.get("action"):
            events = events.filter(action=action[:64])
        if actor := request.query_params.get("user"):
            events = events.filter(acting_user__username__iexact=actor[:150])
        for param, lookup in (("from", "timestamp__date__gte"), ("to", "timestamp__date__lte")):
            if value := request.query_params.get(param):
                events = events.filter(**{lookup: serializers.DateField().run_validation(value)})
        return paginate(request, events, audit_record)


def audit_record(event):
    return {
        "id": event.pk,
        "actor": event.acting_user.username if event.acting_user else None,
        "action": event.action,
        "resource": event.resource_type,
        "resource_id": event.resource_id,
        "timestamp": event.timestamp,
        "request_id": event.request_id,
        "metadata": event.sanitized_metadata,
    }


class AuditDetail(ManagementView):
    def get(self, request, pk):
        require(request.user, "audit.view_auditevent")
        return Response(audit_record(get_object_or_404(AuditEvent, pk=pk)))
