#!/usr/bin/env python3
"""Vendor-only license issuance CLI."""

import argparse
import getpass
import json
import os
import sys
import warnings
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from apps.licensing.protocol import (  # noqa: E402
    DURATIONS,
    IDENTIFIER,
    MAX_TOKEN,
    LicenseError,
    calendar_end,
    canonical,
    encode,
    timestamp,
    validate,
    verify,
)


def write_new(path, data, mode=0o644):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "wb") as handle:
        handle.write(data)


def private_path(path):
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(ROOT):
        raise ValueError("Store signing keys outside the project and customer distribution.")
    return resolved


def passphrase(prompt):
    if not sys.stdin.isatty():
        raise ValueError("Use an interactive vendor terminal for encrypted keys.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt).encode()
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning) as exc:
        raise ValueError("A secure passphrase prompt was not available.") from exc


def keygen(args):
    path = private_path(args.private_key)
    if not IDENTIFIER.fullmatch(args.key_id):
        raise ValueError("Invalid signing key ID.")
    if path.exists() or args.public_keys.exists() or path == args.public_keys.resolve():
        raise ValueError("Select new and distinct output files.")
    encryption = serialization.NoEncryption()
    if not args.test_only:
        first = passphrase("Private key passphrase: ")
        if len(first) < 12 or first != passphrase("Confirm passphrase: "):
            raise ValueError("Use matching passphrases of at least 12 bytes.")
        encryption = serialization.BestAvailableEncryption(first)
    key = Ed25519PrivateKey.generate()
    write_new(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption,
        ),
        mode=0o600,
    )
    write_new(
        args.public_keys,
        (json.dumps({args.key_id: encode(key.public_key().public_bytes_raw())}) + "\n").encode(),
    )
    print(f"Created key {args.key_id} and its public verification manifest.")


def utc_datetime(value):
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time(), UTC)
    return timestamp(value)


def wire(value):
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign(payload, key):
    raw = canonical(validate(payload))
    token = f"SMS1.{encode(raw)}.{encode(key.sign(raw))}"
    if len(token) > MAX_TOKEN:
        raise LicenseError("INVALID_LICENSE", "The license exceeds the allowed size.")
    return token


def issue(args):
    start = utc_datetime(args.valid_from)
    months = DURATIONS[args.duration]
    if not months and not args.expires_at:
        raise ValueError("A custom duration requires --expires-at.")
    end = utc_datetime(args.expires_at) if args.expires_at else calendar_end(start, months)
    if months and end != calendar_end(start, months):
        raise ValueError("Expiration does not match the selected calendar-month duration.")
    if not args.approve:
        raise ValueError(
            f"Review the UTC interval {wire(start)} to {wire(end)} exclusive. Use --approve."
        )
    key = serialization.load_pem_private_key(
        private_path(args.private_key).read_bytes(),
        password=None if args.test_only else passphrase("Private key passphrase: "),
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The signing key must be Ed25519.")
    payload = {
        "version": 1,
        "license_id": str(uuid4()),
        "institution_id": str(args.institution_id),
        "institution_name": args.institution_name,
        "installation_id": str(args.installation_id),
        "edition": args.edition,
        "issued_at": wire(datetime.now(UTC)),
        "valid_from": wire(start),
        "expires_at": wire(end),
        "duration": args.duration,
        "features": sorted(set(args.feature)),
        "key_id": args.key_id,
        "grace_days": args.grace_days,
    }
    write_new(args.out, (sign(payload, key) + "\n").encode())
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def inspect(args):
    keys = json.loads(args.public_keys.read_bytes())
    with args.license.open("rb") as handle:
        token = handle.read(16_387).decode("ascii").strip()
    payload = verify(token, keys)
    now = datetime.now(UTC)
    state = (
        "not_yet_valid"
        if now < max(timestamp(payload["valid_from"]), timestamp(payload["issued_at"]))
        else ("expired" if now >= timestamp(payload["expires_at"]) else "in_period")
    )
    print(
        json.dumps(
            {"signature": "verified", "period": state, "license": payload},
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    from uuid import UUID

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    generate_key = commands.add_parser("keygen")
    create_license = commands.add_parser("issue")
    for command in (generate_key, create_license):
        command.add_argument("--key-id", required=True)
        command.add_argument("--private-key", type=Path, required=True)
        command.add_argument(
            "--test-only", action="store_true", help="Use an unencrypted disposable test key."
        )
    generate_key.add_argument("--public-keys", type=Path, required=True)
    generate_key.set_defaults(handler=keygen)
    create_license.add_argument("--institution-id", type=UUID, required=True)
    create_license.add_argument("--installation-id", type=UUID, required=True)
    create_license.add_argument("--institution-name", required=True)
    create_license.add_argument("--edition", required=True)
    create_license.add_argument("--valid-from", required=True)
    create_license.add_argument("--expires-at")
    create_license.add_argument("--duration", choices=DURATIONS, required=True)
    create_license.add_argument("--grace-days", type=int, default=0)
    create_license.add_argument("--feature", action="append", default=[])
    create_license.add_argument("--approve", action="store_true")
    create_license.add_argument("--out", type=Path, required=True)
    create_license.set_defaults(handler=issue)
    verify_license = commands.add_parser("verify", aliases=["inspect"])
    verify_license.add_argument("--public-keys", type=Path, required=True)
    verify_license.add_argument("--license", type=Path, required=True)
    verify_license.set_defaults(handler=inspect)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(1, f"License operation failed: {exc}\n")


if __name__ == "__main__":
    main()
