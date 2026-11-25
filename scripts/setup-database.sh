#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -x .venv/bin/python && -f backend/.env ]] || {
  echo "Expected .venv/bin/python and backend/.env." >&2
  exit 1
}

exec .venv/bin/python - <<'PY'
import base64
import hashlib
import hmac
import os
import re
import secrets
import subprocess

import environ
import psycopg

# Read dotenv as data in isolation, without inherited database overrides.
values = {}
class FileEnv(environ.Env):
    ENVIRON = values

FileEnv.read_env("backend/.env")
expected = {
    "DB_NAME": "school_management_db",
    "DB_USER": "school_management_app",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5433",
}
for name, value in expected.items():
    if values.get(name) != value:
        raise SystemExit(f"backend/.env must set {name}={value} for local provisioning.")

password = values.get("DB_PASSWORD", "")
if not re.fullmatch(r"[!-~]{16,256}", password) or "replace" in password.lower():
    raise SystemExit("DB_PASSWORD must be a generated printable ASCII password.")

conninfo = {
    "hostaddr": expected["DB_HOST"],
    "port": expected["DB_PORT"],
    "dbname": expected["DB_NAME"],
    "user": expected["DB_USER"],
    "password": password,
    "connect_timeout": 5,
}
try:
    with psycopg.connect(**conninfo):
        password_clause = ""
except psycopg.OperationalError:
    # Send a SCRAM verifier over stdin, keeping the plaintext on the client.
    salt = secrets.token_bytes(16)
    iterations = 4096
    secret = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.digest(secret, b"Client Key", "sha256")
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.digest(secret, b"Server Key", "sha256")

    def encode(value):
        return base64.b64encode(value).decode()

    verifier = f"SCRAM-SHA-256${iterations}:{encode(salt)}${encode(stored_key)}:{encode(server_key)}"
    password_clause = f" PASSWORD '{verifier}'"

if subprocess.run(["sudo", "-v"], check=False).returncode:
    raise SystemExit("Run bash scripts/setup-database.sh in an interactive Ubuntu terminal.")

sql = r"""
SELECT pg_advisory_lock(351864, 5433);
DO $block$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_auth_members m
        JOIN pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'school_management_app'
    ) THEN
        RAISE EXCEPTION 'Application role has existing role memberships';
    END IF;
END
$block$;
SELECT 'CREATE ROLE school_management_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'school_management_app')
\gexec
"""
sql += (
    "ALTER ROLE school_management_app WITH LOGIN NOSUPERUSER NOCREATEDB "
    f"NOCREATEROLE NOREPLICATION NOBYPASSRLS{password_clause};\n"
)
sql += r"""
SELECT 'CREATE DATABASE school_management_db OWNER school_management_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'school_management_db')
\gexec
SELECT 'ALTER DATABASE school_management_db OWNER TO school_management_app'
FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba
WHERE d.datname = 'school_management_db' AND r.rolname <> 'school_management_app'
\gexec
"""

result = subprocess.run(
    [
        "sudo", "-n", "-u", "postgres", "--", "psql", "-X", "-w",
        "-h", "/var/run/postgresql", "-p", "5433", "-U", "postgres", "-d", "postgres",
        "-v", "ON_ERROR_STOP=1",
    ],
    env={key: value for key, value in os.environ.items() if not key.startswith("PG")},
    input=sql,
    text=True,
    capture_output=True,
    check=False,
)
if result.returncode:
    if "existing role memberships" in result.stderr:
        raise SystemExit("Review existing memberships of school_management_app before provisioning.")
    raise SystemExit("PostgreSQL provisioning failed. Verify sudo access and cluster 18/main on port 5433.")

try:
    with psycopg.connect(**conninfo) as conn:
        can_create = conn.execute(
            "SELECT has_schema_privilege(current_user, 'public', 'USAGE') AND "
            "has_schema_privilege(current_user, 'public', 'CREATE')"
        ).fetchone()[0]
except psycopg.Error:
    raise SystemExit("Provisioning ran, but application database verification failed.") from None
if not can_create:
    raise SystemExit("Review the public schema privileges in school_management_db.")
print("Application role and database verified on 127.0.0.1:5433.")
PY
