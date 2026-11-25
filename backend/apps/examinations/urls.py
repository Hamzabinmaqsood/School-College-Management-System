from django.urls import path
from rest_framework.routers import SimpleRouter

from .config_api import Exams, Groups, Registrations, Schedules, Schemes, Subjects, Types
from .marks_api import Marks
from .reports_api import Reports
from .result_api import Runs

router = SimpleRouter()
for name, view in (
    ("types", Types),
    ("grading-schemes", Schemes),
    ("exams", Exams),
    ("classes", Groups),
    ("subjects", Subjects),
    ("schedules", Schedules),
    ("registrations", Registrations),
    ("marks", Marks),
    ("results", Runs),
):
    router.register(name, view, basename=f"examination-{name}")

urlpatterns = [
    path("overview/", Reports.as_view({"get": "overview"})),
    path("date-sheet/", Reports.as_view({"get": "date_sheet"})),
    path("results/student/<uuid:student_id>/", Reports.as_view({"get": "student"})),
    path("results/class/<uuid:class_id>/", Reports.as_view({"get": "class_results"})),
    path("results/class/<uuid:class_id>/report-cards/", Reports.as_view({"get": "batch"})),
    path("results/<uuid:pk>/report-card/", Reports.as_view({"get": "card"})),
    path("reports/<slug:kind>/", Reports.as_view({"get": "report"})),
    path("reports/<slug:kind>/export/", Reports.as_view({"get": "export"})),
    *router.urls,
]
