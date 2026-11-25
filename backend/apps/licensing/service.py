import json
from datetime import timedelta
from math import ceil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils.timezone import now as utc_now

from apps.accounts.authentication import audit
from apps.accounts.models import Institution

from .models import InstallationIdentity, LicenseActivation
from .protocol import IDENTIFIER, LicenseError, decode, timestamp, verify

REMINDERS = (15, 7, 3, 0)
WRITABLE = {"ACTIVE", "EXPIRING_SOON"}


def trusted_keys():
    try:
        path = settings.LICENSE_PUBLIC_KEYS_FILE
        if not path:
            return settings.LICENSE_PUBLIC_KEYS
        with Path(path).open("rb") as handle:
            raw = handle.read(65_537)
        if len(raw) > 65_536:
            return {}
        keys = json.loads(raw)
        if not isinstance(keys, dict) or any(
            not IDENTIFIER.fullmatch(key) or len(decode(value)) != 32 for key, value in keys.items()
        ):
            return {}
        return keys
    except OSError, ValueError, TypeError, RecursionError:
        return {}


def installation(lock=False):
    institution = Institution.objects.first()
    if not institution:
        return None
    query = (
        InstallationIdentity.objects.select_for_update() if lock else InstallationIdentity.objects
    )
    identity, _ = query.get_or_create(institution=institution)
    return identity


def bound_license(token, identity, keys):
    payload = verify(token, keys)
    if payload["installation_id"] != str(identity.installation_id) or payload[
        "institution_id"
    ] != str(identity.institution_id):
        raise LicenseError(
            "INSTALLATION_MISMATCH", "This license belongs to another institution or installation."
        )
    return payload


def observe_clock(identity, request, now):
    previous = identity.last_verified_at
    if previous and previous - now > timedelta(seconds=settings.LICENSE_CLOCK_TOLERANCE):
        if not identity.clock_review:
            identity.clock_review = True
            identity.save(update_fields=["clock_review"])
            audit(request, "LICENSE_CLOCK_REVIEW", "installation", identity)
        return previous
    if identity.clock_review and previous and now >= previous:
        identity.clock_review = False
        audit(request, "LICENSE_CLOCK_RECOVERED", "installation", identity)
    if not previous or now > previous:
        identity.last_verified_at = now
    identity.save(update_fields=["last_verified_at", "clock_review"])
    return max(now, previous) if previous else now


def duration_left(moment, now):
    return max(0, ceil((moment - now).total_seconds() / 86400))


def evaluate(identity, request, now, keys):
    if not identity or not identity.current_id:
        return {"status": "NOT_ACTIVATED", "write_allowed": False, "license": None}
    try:
        payload = bound_license(identity.current.token, identity, keys)
    except LicenseError as exc:
        return {"status": exc.code, "write_allowed": False, "license": None}
    effective = observe_clock(identity, request, now)
    start, end = timestamp(payload["valid_from"]), timestamp(payload["expires_at"])
    grace_end = end + timedelta(days=min(payload["grace_days"], settings.LICENSE_MAX_GRACE_DAYS))
    days = duration_left(end, effective)

    if identity.clock_review:
        state = "CLOCK_REVIEW_REQUIRED"
    elif effective < start or effective < timestamp(payload["issued_at"]):
        state = "NOT_YET_VALID"
    elif effective >= grace_end:
        state = "EXPIRED"
    elif effective >= end:
        state = "GRACE_PERIOD"
    elif days <= REMINDERS[0]:
        state = "EXPIRING_SOON"
    else:
        state = "ACTIVE"

    return {
        "status": state,
        "days_remaining": days,
        "grace_deadline": grace_end if grace_end > end else None,
        "reminder_days": next(
            (threshold for threshold in reversed(REMINDERS) if days <= threshold), None
        ),
        "write_allowed": state in WRITABLE
        or (state == "GRACE_PERIOD" and settings.LICENSE_GRACE_WRITES),
        "license": payload | {"activated_at": identity.current.activated_at},
    }


@transaction.atomic
def license_status(request, now=None):
    return evaluate(installation(lock=True), request, now or utc_now(), trusted_keys())


def validate_replacement(payload, identity, now, keys):
    if timestamp(payload["valid_from"]) > now or timestamp(payload["issued_at"]) > now:
        raise LicenseError(
            "NOT_YET_VALID", "The license is not valid yet. Check the server time and start date."
        )
    if now >= timestamp(payload["expires_at"]):
        raise LicenseError("EXPIRED", "The license has already expired.")
    if identity.current_id:
        try:
            previous = bound_license(identity.current.token, identity, keys)
        except LicenseError:
            return
        if timestamp(payload["issued_at"]) < timestamp(previous["issued_at"]) or (
            timestamp(payload["expires_at"]) <= timestamp(previous["expires_at"])
        ):
            raise LicenseError(
                "OLDER_LICENSE", "A renewal must extend the current expiration date."
            )


@transaction.atomic
def activate(identity, request, token, now=None):
    now = now or utc_now()
    keys = trusted_keys()
    try:
        payload = bound_license(token, identity, keys)
        seen = LicenseActivation.objects.filter(pk=payload["license_id"]).first()
        if seen:
            if seen.pk == identity.current_id and seen.token == token:
                result = evaluate(identity, request, now, keys)
                return result | {"duplicate": True}, None
            raise LicenseError(
                "LICENSE_REPLAY", "This license ID was already used. Request a new license."
            )
        if identity.current_id:
            observed = evaluate(identity, request, now, keys)
            if observed["status"] == "CLOCK_REVIEW_REQUIRED":
                raise LicenseError(
                    "CLOCK_REVIEW_REQUIRED", "Correct the server clock before importing a license."
                )
        if identity.last_verified_at and identity.last_verified_at > now:
            if observe_clock(identity, request, now) > now and identity.clock_review:
                raise LicenseError(
                    "CLOCK_REVIEW_REQUIRED", "Correct the server clock before importing a license."
                )
        effective = max(now, identity.last_verified_at or now)
        validate_replacement(payload, identity, effective, keys)
        activation = LicenseActivation.objects.create(
            license_id=payload["license_id"],
            installation=identity,
            token=token,
        )
        renewed = identity.current_id is not None
        identity.current = activation
        identity.save(update_fields=["current"])
        audit(
            request,
            "LICENSE_RENEWED" if renewed else "LICENSE_ACTIVATED",
            "license",
            activation,
            key_id=payload["key_id"],
        )
        return evaluate(identity, request, now, keys) | {"duplicate": False}, None
    except LicenseError as exc:
        audit(request, "LICENSE_REJECTED", "installation", identity, reason=exc.code)
        return None, exc
