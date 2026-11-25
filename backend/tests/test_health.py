from unittest.mock import patch

from django.db.utils import OperationalError
from django.urls import reverse
from rest_framework.test import APITestCase


class HealthEndpointTests(APITestCase):
    def test_health_is_available(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_reports_database_unavailable_without_details(self):
        with patch(
            "apps.core.views.connection.ensure_connection",
            side_effect=OperationalError("internal detail"),
        ):
            response = self.client.get(reverse("ready"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "not_ready", "database": "unavailable"})
