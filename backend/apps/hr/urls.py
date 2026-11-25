from django.urls import path
from rest_framework.routers import SimpleRouter

from . import models
from .api import Attendance, Contracts, DepartmentFields, Leaves, Settings, registry
from .leave_balance import Balances, Policy
from .overtime import Policies, Requests
from .payroll import Adjustments, Advances, Assignments, Payments, Payroll, Periods, Structures
from .people import Documents, EmployeeAssignments
from .reports import Reports

router = SimpleRouter()
for route, view in (
    (
        "departments",
        registry(
            models.Department,
            "accounts.view_staff",
            "accounts.manage_hr_registry",
            filters=("active",),
            serializer=DepartmentFields,
            search=("name", "code"),
        ),
    ),
    (
        "designations",
        registry(
            models.Designation,
            "accounts.view_staff",
            "accounts.manage_hr_registry",
            filters=("active", "teaching"),
            search=("name", "code"),
        ),
    ),
    ("leave-types", Policy),
    ("leave-balances", Balances),
    ("employees", EmployeeAssignments),
    ("documents", Documents),
    ("contracts", Contracts),
    ("attendance", Attendance),
    ("leaves", Leaves),
    ("salary-structures", Structures),
    ("salary-assignments", Assignments),
    ("advances", Advances),
    ("periods", Periods),
    ("payroll", Payroll),
    ("overtime-policies", Policies),
    ("overtime", Requests),
    ("salary-payments", Payments),
    ("payroll-adjustments", Adjustments),
):
    router.register(route, view, basename="hr-" + route)

urlpatterns = [
    path("overview/", Reports.as_view({"get": "overview"})),
    path("settings/", Settings.as_view({"get": "retrieve", "patch": "partial_update"})),
    path("payslips/", Reports.as_view({"get": "payslips"})),
    path("payslips/<uuid:pk>/", Reports.as_view({"get": "payslip"})),
    path("employees/<uuid:employee_id>/payslips/", Reports.as_view({"get": "statement"})),
    path("reports/<slug:kind>/", Reports.as_view({"get": "report"})),
    path("reports/<slug:kind>/export/", Reports.as_view({"get": "export"})),
    *router.urls,
]
