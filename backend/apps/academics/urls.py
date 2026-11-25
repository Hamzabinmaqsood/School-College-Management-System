from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.admissions.api import Admissions
from apps.students.api import Guardians, Students
from apps.students.related_api import AdmissionPolicy, Documents, GuardiansForStudent

from .api import Assignments, Classes, Sections, Sessions, Subjects

router = SimpleRouter()
for prefix, view in (
    ("academic-sessions", Sessions),
    ("classes", Classes),
    ("sections", Sections),
    ("subjects", Subjects),
    ("class-subjects", Assignments),
    ("students", Students),
    ("guardians", Guardians),
    ("admissions", Admissions),
):
    router.register(prefix, view, basename=prefix)


urlpatterns = [
    path(
        "admission-policy/", AdmissionPolicy.as_view({"get": "retrieve", "patch": "partial_update"})
    ),
    path("student-document-types/", Documents.as_view({"get": "kinds"})),
    path(
        "students/<uuid:student_id>/guardians/",
        GuardiansForStudent.as_view({"get": "list", "post": "create"}),
    ),
    path(
        "students/<uuid:student_id>/guardians/<uuid:pk>/",
        GuardiansForStudent.as_view({"patch": "partial_update"}),
    ),
    path(
        "students/<uuid:student_id>/documents/",
        Documents.as_view({"get": "list", "post": "create"}),
    ),
    path(
        "students/<uuid:student_id>/documents/<uuid:pk>/download/",
        Documents.as_view({"get": "download"}),
    ),
    path(
        "students/<uuid:student_id>/documents/<uuid:pk>/preview/",
        Documents.as_view({"get": "preview"}),
    ),
    path(
        "students/<uuid:student_id>/documents/<uuid:pk>/archive/",
        Documents.as_view({"post": "archive"}),
    ),
    *router.urls,
]
