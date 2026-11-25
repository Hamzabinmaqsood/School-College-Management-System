"""Read-only checks for the provisioned local PostgreSQL development database."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

pytestmark = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Run with --ds=config.settings.development for PostgreSQL integration.",
)


def test_migrated_postgresql_schema(django_db_blocker):
    with django_db_blocker.unblock():
        tables = set(connection.introspection.table_names())
        assert {
            "accounts_user",
            "auth_group",
            "auth_permission",
            "audit_auditevent",
            "django_migrations",
        } <= tables
        executor = MigrationExecutor(connection)
        assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []


def test_live_readiness(client, django_db_blocker):
    with django_db_blocker.unblock():
        response = client.get(reverse("ready"), HTTP_HOST="localhost")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
