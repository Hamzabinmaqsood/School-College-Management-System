from django.urls import path
from rest_framework.routers import SimpleRouter

from . import api
from .schedule import Schedule

router = SimpleRouter()
for name, view in (
    ("shifts", api.Shifts),
    ("periods", api.Periods),
    ("rooms", api.Rooms),
    ("teacher-availability", api.Availability),
    ("workload-policies", api.Workload),
    ("plans", api.Plans),
    ("entries", api.Entries),
    ("teaching-groups", api.Groups),
    ("exceptions", api.Exceptions),
    ("subject-requirements", api.Requirements),
):
    router.register(name, view, basename="timetable-" + name)

urlpatterns = [
    path("settings/", api.Settings.as_view({"get": "retrieve", "patch": "partial_update"})),
    path("daily/", Schedule.as_view()),
    path("weekly/", Schedule.as_view(mode="weekly")),
    path("reports/export/", Schedule.as_view(mode="export")),
    path("teachers/", api.Tools.as_view({"get": "teachers"})),
    path("validate/", api.Tools.as_view({"post": "validate"})),
    path("suggestions/", api.Suggestions.as_view({"get": "list"})),
    path("group-members/", api.GroupMembers.as_view({"get": "list"})),
    *[
        path("reports/" + name + "/", Schedule.as_view(mode=mode, report=name))
        for name, mode in (
            ("class", "weekly"),
            ("section", "weekly"),
            ("teacher-weekly", "weekly"),
            ("teacher-daily", "daily"),
            ("rooms", "weekly"),
            ("workload", "weekly"),
            ("allocations", "weekly"),
            ("unassigned", "weekly"),
            ("conflicts", "weekly"),
            ("substitutions", "weekly"),
            ("cancellations", "weekly"),
            ("reschedules", "weekly"),
            ("revisions", "weekly"),
            ("attendance", "weekly"),
        )
    ],
    *router.urls,
]
