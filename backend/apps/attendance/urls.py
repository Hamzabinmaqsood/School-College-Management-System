from django.urls import path
from rest_framework.routers import SimpleRouter

from .config_api import Assignments, Calendar, Settings
from .leave_api import Leaves
from .register_api import Attendance
from .report_api import Reports

router = SimpleRouter()
router.register("attendance/holidays", Calendar, basename="attendance-holidays")
router.register("attendance/assignments", Assignments, basename="attendance-assignments")
router.register("attendance/leaves", Leaves, basename="attendance-leaves")
router.register("attendance", Attendance, basename="attendance")
urlpatterns = [
    path("attendance/summary/", Reports.as_view({"get": "summary"})),
    path("attendance/report-filters/", Reports.as_view({"get": "filters"})),
    path("attendance/reports/", Reports.as_view({"get": "report"})),
    path("attendance/export/", Reports.as_view({"get": "export"})),
    path("attendance/print/", Reports.as_view({"get": "print_report"})),
    path("attendance/student/<uuid:student_id>/", Reports.as_view({"get": "student"})),
    path("attendance/settings/", Settings.as_view({"get": "retrieve", "patch": "partial_update"})),
    *router.urls,
]
