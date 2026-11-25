"""Isolated browser-only settings for advancing the HR date without changing host time."""

import os
from datetime import date
from pathlib import Path

from config.settings.development import *  # noqa: F403

_path = Path(os.environ["SMS_PHASE09_LEAVE_CLOCK"])


class LeaveClock:
    def __init__(self, get_response):
        from apps.hr import api, leave_balance

        self.get_response = get_response

        def fixture_today():
            return date.fromisoformat(_path.read_text().strip())

        api.today = fixture_today
        leave_balance.today = fixture_today

    def __call__(self, request):
        return self.get_response(request)


MIDDLEWARE = [*MIDDLEWARE, "leave_clock.LeaveClock"]  # noqa: F405
