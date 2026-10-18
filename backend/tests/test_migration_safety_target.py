"""
Automated unit tests for fail-closed staging migration target verification.
Tests prove that incorrect environments, SQLite databases, conflicting URLs,
unapproved hosts, mismatched roles, and mismatched databases are strictly rejected.
"""
import pytest
from backend.app.cli.verify_staging_migration_target import (
    run_target_verification,
    get_effective_alembic_url,
    sanitize_db_url,
)


def test_sanitize_db_url():
    """Verify that credentials are fully redacted from database URLs."""
    raw = "postgresql+psycopg2://migrator_user:VerySecretPassword123@staging-db.internal:5432/rvfitness_staging"
    sanitized = sanitize_db_url(raw)
    assert "VerySecretPassword123" not in sanitized
    assert sanitized == "postgresql+psycopg2://migrator_user:***@staging-db.internal:5432/rvfitness_staging"


def test_rejects_non_staging_environment(monkeypatch):
    """Verify that any environment other than 'staging' triggers an immediate abort."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@staging-db.internal:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="ENVIRONMENT must be strictly 'staging'"):
        run_target_verification()


def test_rejects_sqlite_database(monkeypatch):
    """Verify that SQLite connection strings are strictly rejected."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./staging.db")
    with pytest.raises(ValueError, match="SQLite database detected"):
        run_target_verification()


def test_rejects_ambiguous_conflicting_urls(monkeypatch):
    """Verify that conflicting POSTGRESQL_TEST_URL and DATABASE_URL fail closed."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("POSTGRESQL_TEST_URL", "postgresql://user:pass@127.0.0.1:5432/test_db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@staging-db.internal:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="Ambiguous database configuration"):
        run_target_verification()


def test_rejects_unapproved_database_host(monkeypatch):
    """Verify that attempting to migrate an unapproved host is rejected."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:pass@rogue-host.external:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="is not in approved staging hosts list"):
        run_target_verification(approved_hosts=["staging-db.internal"])


def test_rejects_database_name_mismatch(monkeypatch):
    """Verify that a database name differing from EXPECTED_STAGING_DB_NAME is rejected."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:pass@staging-db.internal:5432/rvfitness_prod")
    with pytest.raises(ValueError, match="does not match expected staging database"):
        run_target_verification(
            expected_db="rvfitness_staging",
            approved_hosts=["staging-db.internal"],
        )


def test_rejects_connected_catalog_mismatch(monkeypatch):
    """Verify that if live connection reveals a different database than claimed, it aborts."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:pass@staging-db.internal:5432/rvfitness_staging")

    mock_connector = lambda url: {
        "database": "rvfitness_prod",  # Pretend server connected to prod
        "user": "rvf_staging_migrator",
        "server_ip": "10.0.1.5",
    }

    with pytest.raises(ValueError, match="Connected catalog is 'rvfitness_prod', expected 'rvfitness_staging'"):
        run_target_verification(
            connector=mock_connector,
            expected_db="rvfitness_staging",
            approved_hosts=["staging-db.internal"],
        )


def test_rejects_unauthorized_user_role(monkeypatch):
    """Verify that connecting as an unexpected or non-migrator role is rejected."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://unprivileged_user:pass@staging-db.internal:5432/rvfitness_staging")

    mock_connector = lambda url: {
        "database": "rvfitness_staging",
        "user": "unprivileged_user",
        "server_ip": "10.0.1.5",
    }

    with pytest.raises(ValueError, match="expected privileged migrator role 'rvf_staging_migrator'"):
        run_target_verification(
            connector=mock_connector,
            expected_db="rvfitness_staging",
            expected_user="rvf_staging_migrator",
            approved_hosts=["staging-db.internal"],
        )


def test_successful_staging_verification(monkeypatch):
    """Verify that when all parameters match the approved staging target, verification passes."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:secret123@staging-db.internal:5432/rvfitness_staging")

    mock_connector = lambda url: {
        "database": "rvfitness_staging",
        "user": "rvf_staging_migrator",
        "server_ip": "10.0.1.5",
    }

    result = run_target_verification(
        connector=mock_connector,
        expected_db="rvfitness_staging",
        expected_user="rvf_staging_migrator",
        approved_hosts=["staging-db.internal", "10.0.1.5"],
    )

    assert result["status"] == "verified"
    assert result["database"] == "rvfitness_staging"
    assert result["user"] == "rvf_staging_migrator"
    assert "secret123" not in result["sanitized_url"]


def test_rejects_unconfigured_approved_staging_hosts(monkeypatch):
    """Verify that missing APPROVED_STAGING_HOSTS fails closed rather than accepting default hosts."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.delenv("APPROVED_STAGING_HOSTS", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:pass@localhost:5432/rvfitness_staging")

    with pytest.raises(ValueError, match="APPROVED_STAGING_HOSTS must be explicitly configured"):
        run_target_verification(approved_hosts=None)


def test_rejects_unapproved_server_ip_identity(monkeypatch):
    """Verify that if live server IP resolves to an unapproved network address, it fails closed."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://rvf_staging_migrator:pass@staging-db.internal:5432/rvfitness_staging")

    mock_connector = lambda url: {
        "database": "rvfitness_staging",
        "user": "rvf_staging_migrator",
        "server_ip": "192.168.100.99",
    }

    with pytest.raises(ValueError, match="Connected server network address '192.168.100.99' is not in approved staging hosts list"):
        run_target_verification(
            connector=mock_connector,
            expected_db="rvfitness_staging",
            expected_user="rvf_staging_migrator",
            approved_hosts=["staging-db.internal", "10.0.1.5"],
        )


def test_rejects_conflicting_test_database_url_and_database_url(monkeypatch):
    """Verify that conflicting TEST_DATABASE_URL and DATABASE_URL fail closed."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://user:pass@test-host:5432/test_db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@staging-db.internal:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="Ambiguous database configuration"):
        run_target_verification(approved_hosts=["staging-db.internal"])


def test_rejects_alembic_ini_sqlalchemy_url_conflict(monkeypatch, tmp_path):
    """Verify that if alembic.ini defines sqlalchemy.url conflicting with environment variables, it fails closed."""
    custom_ini = tmp_path / "alembic.ini"
    custom_ini.write_text(
        "[alembic]\n"
        "sqlalchemy.url = postgresql+psycopg2://user:pass@config-host:5432/config_db\n"
    )
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("ALEMBIC_CONFIG", str(custom_ini))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://user:pass@staging-db.internal:5432/rvfitness_staging")

    with pytest.raises(ValueError, match="Ambiguous database configuration"):
        run_target_verification(approved_hosts=["staging-db.internal", "config-host"])


def test_uses_alembic_ini_sqlalchemy_url_when_unambiguous(monkeypatch, tmp_path):
    """Verify that if alembic.ini defines sqlalchemy.url and no conflicting environment exists, it is resolved."""
    custom_ini = tmp_path / "alembic.ini"
    custom_ini.write_text(
        "[alembic]\n"
        "sqlalchemy.url = postgresql+psycopg2://rvf_staging_migrator:pass@staging-db.internal:5432/rvfitness_staging\n"
    )
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("ALEMBIC_CONFIG", str(custom_ini))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRESQL_TEST_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    mock_connector = lambda url: {
        "database": "rvfitness_staging",
        "user": "rvf_staging_migrator",
        "server_ip": "staging-db.internal",
    }

    result = run_target_verification(
        connector=mock_connector,
        expected_db="rvfitness_staging",
        expected_user="rvf_staging_migrator",
        approved_hosts=["staging-db.internal"],
    )
    assert result["status"] == "verified"
    assert result["database"] == "rvfitness_staging"
