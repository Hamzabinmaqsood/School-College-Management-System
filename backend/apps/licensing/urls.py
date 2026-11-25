from django.urls import path

from .views import ActivateView, HistoryView, InstallationView, StatusView

urlpatterns = [
    path("status/", StatusView.as_view()),
    path("installation/", InstallationView.as_view()),
    path("activate/", ActivateView.as_view()),
    path("history/", HistoryView.as_view()),
]
