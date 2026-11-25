from django.db import connection
from django.db.utils import OperationalError
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        return Response({"status": "ok", "service": "school-management-backend"})


class ReadyView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        try:
            connection.ensure_connection()
        except OperationalError:
            return Response(
                {"status": "not_ready", "database": "unavailable"},
                status=503,
            )
        return Response({"status": "ready", "database": "connected"})
