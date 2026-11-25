from django.urls import path

from . import authentication as auth
from . import management_api as api
from .institution import InstitutionView, LogoView

urlpatterns = [
    path("auth/csrf/", auth.CsrfView.as_view()),
    path("auth/login/", auth.LoginView.as_view()),
    path("auth/logout/", auth.LogoutView.as_view()),
    path("auth/me/", auth.MeView.as_view()),
    path("auth/change-password/", auth.ChangePasswordView.as_view()),
    path("institution/", InstitutionView.as_view()),
    path("institution/logo/", LogoView.as_view()),
    path("users/", api.UserList.as_view()),
    path("users/<uuid:pk>/", api.UserDetail.as_view()),
    path("users/<uuid:pk>/permissions/", api.UserPermissions.as_view()),
    path("users/<uuid:pk>/activate/", api.UserOperation.as_view(operation="activate")),
    path("users/<uuid:pk>/deactivate/", api.UserOperation.as_view(operation="deactivate")),
    path("users/<uuid:pk>/reset-password/", api.UserOperation.as_view(operation="reset")),
    path("roles/", api.RoleList.as_view()),
    path("roles/<uuid:pk>/", api.RoleDetail.as_view()),
    path("roles/<uuid:pk>/permissions/", api.RolePermissions.as_view()),
    path("permissions/", api.CatalogView.as_view()),
    path("audit/", api.AuditList.as_view()),
    path("audit/<uuid:pk>/", api.AuditDetail.as_view()),
]
