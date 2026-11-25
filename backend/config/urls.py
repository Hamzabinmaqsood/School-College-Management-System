"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from apps.core.views import HealthView, ReadyView
from django.contrib import admin
from django.db import transaction
from django.urls import include, path

# Health and readiness must handle a database outage outside ATOMIC_REQUESTS.
urlpatterns = [
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.academics.urls")),
    path("api/v1/", include("apps.attendance.urls")),
    path("api/v1/fees/", include("apps.fees.urls")),
    path("api/v1/examinations/", include("apps.examinations.urls")),
    path("api/v1/hr/", include("apps.hr.urls")),
    path("api/v1/timetables/", include("apps.timetables.urls")),
    path("api/v1/license/", include("apps.licensing.urls")),
    path("admin/", admin.site.urls),
    path("api/v1/health/", transaction.non_atomic_requests(HealthView.as_view()), name="health"),
    path("api/v1/ready/", transaction.non_atomic_requests(ReadyView.as_view()), name="ready"),
]
