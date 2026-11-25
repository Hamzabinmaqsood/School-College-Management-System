from django.urls import path
from rest_framework.routers import SimpleRouter

from .config_api import Assignments, Categories, Concessions, Settings, Structures
from .report_api import Reports
from .transactions_api import Adjustments, Billing, Invoices, Payments, Refunds

router = SimpleRouter()
for name, view in [
    ("categories", Categories),
    ("structures", Structures),
    ("assignments", Assignments),
    ("concessions", Concessions),
    ("invoices", Invoices),
    ("payments", Payments),
    ("adjustments", Adjustments),
    ("refunds", Refunds),
]:
    router.register(name, view, basename=f"fee-{name}")

urlpatterns = [
    path("settings/", Settings.as_view({"get": "retrieve", "patch": "partial_update"})),
    path("billing/preview/", Billing.as_view({"post": "preview"})),
    path("billing/generate/", Billing.as_view({"post": "generate"})),
    path("billing/history/", Billing.as_view({"get": "list"})),
    path("overview/", Reports.as_view({"get": "overview"})),
    path("lookups/", Reports.as_view({"get": "lookups"})),
    path("reports/<slug:kind>/", Reports.as_view({"get": "report"})),
    path("reports/<slug:kind>/export/", Reports.as_view({"get": "export"})),
    path("students/<uuid:student_id>/statement/", Reports.as_view({"get": "statement"})),
    path("students/<uuid:student_id>/outstanding/", Reports.as_view({"get": "outstanding"})),
    path("invoices/<uuid:pk>/challan/", Reports.as_view({"get": "challan"})),
    path("invoices/challans/", Reports.as_view({"get": "batch_challans"})),
    path("payments/<uuid:pk>/receipt/", Reports.as_view({"get": "receipt"})),
    *router.urls,
]
