from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class LocalAdminSite(AdminSite):
    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser


class LocalAdminConfig(AdminConfig):
    default_site = "apps.accounts.admin_site.LocalAdminSite"
