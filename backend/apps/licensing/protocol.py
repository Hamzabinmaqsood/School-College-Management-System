"""Version 1 wire format shared by offline verifiers and the vendor CLI."""

import base64
import calendar
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_TOKEN = 16_384
DURATIONS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12, "custom": 0}
FIELDS = {
    "version",
    "license_id",
    "institution_id",
    "institution_name",
    "installation_id",
    "edition",
    "issued_at",
    "valid_from",
    "expires_at",
    "duration",
    "features",
    "key_id",
    "grace_days",
}
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class LicenseError(ValueError):
    code = "INVALID_LICENSE"

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid base64url")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if encode(raw) != value:
        raise ValueError("Noncanonical base64url")
    return raw


def timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("Expected UTC timestamp with whole seconds")
    result = datetime.fromisoformat(value).astimezone(UTC)
    if not 2000 <= result.year <= 9998:
        raise ValueError("Timestamp outside supported range")
    return result


def calendar_end(start, months):
    year, month0 = divmod(start.year * 12 + start.month - 1 + months, 12)
    month = month0 + 1
    return start.replace(
        year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1])
    )


def validate(payload):
    try:
        if set(payload) != FIELDS or type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError
        for field in ("license_id", "institution_id", "installation_id"):
            if str(UUID(payload[field])) != payload[field]:
                raise ValueError
        name = payload["institution_name"]
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 180
            or not name.isprintable()
        ):
            raise ValueError
        for field in ("edition", "key_id"):
            if not IDENTIFIER.fullmatch(payload[field]):
                raise ValueError
        features = payload["features"]
        if not isinstance(features, list) or len(features) > 100:
            raise ValueError
        if any(not IDENTIFIER.fullmatch(feature) for feature in features) or features != sorted(
            set(features)
        ):
            raise ValueError
        issued, start, end = (
            timestamp(payload[field]) for field in ("issued_at", "valid_from", "expires_at")
        )
        if type(payload["grace_days"]) is not int or not 0 <= payload["grace_days"] <= 14:
            raise ValueError
        months = DURATIONS[payload["duration"]]
        if not start < end or not issued < end or (months and calendar_end(start, months) != end):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise LicenseError(
            "INVALID_LICENSE", "The license has an unsupported or invalid format."
        ) from exc
    return payload


def verify(token, keys):
    try:
        if len(token) > MAX_TOKEN:
            raise ValueError
        prefix, encoded, signature = token.split(".")
        if prefix != "SMS1":
            raise ValueError
        raw, sig = decode(encoded), decode(signature)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or canonical(payload) != raw:
            raise ValueError
        validate(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise LicenseError(
            "INVALID_LICENSE", "The license has an unsupported or invalid format."
        ) from exc
    try:
        key = decode(keys[payload["key_id"]])
        Ed25519PublicKey.from_public_bytes(key).verify(sig, raw)
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise LicenseError(
            "INVALID_SIGNATURE", "The signature is invalid or the signing key is untrusted."
        ) from exc
    return payload
