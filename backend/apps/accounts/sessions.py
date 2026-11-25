import time

from django.conf import settings
from django.contrib.auth import logout
from rest_framework.authentication import SessionAuthentication


class LocalSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"

    def authenticate(self, request):
        result = super().authenticate(request)
        if not result:
            return None
        session = request.session
        now = int(time.time())
        last = session.get("app_last_seen", now)
        started = session.get("app_started", now)
        if now - last >= settings.APP_SESSION_IDLE or now - started >= settings.APP_SESSION_MAX:
            logout(request._request)
            return None
        if "app_started" not in session or now - last >= min(
            15, max(1, settings.APP_SESSION_IDLE // 4)
        ):
            session["app_started"] = started
            session["app_last_seen"] = now
        return result
