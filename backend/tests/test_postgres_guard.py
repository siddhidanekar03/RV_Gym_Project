"""
Unit tests for the fail-closed PostgreSQL test safety guard.
Verifies all safety checks without connecting to a real database:
1. Missing opt-in flag (ALLOW_DESTRUCTIVE_POSTGRES_TESTS)
2. Missing or empty URL
3. Unapproved host
4. Protected database names (prod, staging, live, system databases)
5. Invalid database identity (mismatched catalog on live inspection)
6. Dedicated integration test role mismatch
7. Rejection of production and staging environments
8. Approved disposable test target validation
9. Password masking across logs, exceptions, and sanitization
"""
import pytest
from backend.app.core.postgres_test_guard import (
    sanitize_db_url,
    validate_disposable_test_target,
    verify_live_database_identity,
    get_approved_test_hosts,
    get_approved_test_ports,
)


def test_sanitize_db_url_masks_password():
    """Verify that credentials are fully masked and never leaked."""
    raw = "postgresql://test_user:SuperSecretPassword123@127.0.0.1:5432/rvfitness_test"
    sanitized = sanitize_db_url(raw)
    assert "SuperSecretPassword123" not in sanitized
    assert sanitized == "postgresql://test_user:***@127.0.0.1:5432/rvfitness_test"


def test_sanitize_db_url_handles_empty_and_malformed():
    """Verify safe handling of empty and malformed URLs."""
    assert sanitize_db_url(None) == "<empty>"
    assert sanitize_db_url("") == "<empty>"
    assert sanitize_db_url("   ") == "<empty>"


def test_rejects_missing_opt_in(monkeypatch):
    """Verify that absent or false ALLOW_DESTRUCTIVE_POSTGRES_TESTS triggers immediate abort."""
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", raising=False)
    monkeypatch.setenv("POSTGRESQL_TEST_URL", "postgresql://user:pass@127.0.0.1:5432/rvfitness_test")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(RuntimeError, match="Destructive PostgreSQL tests require explicit opt-in"):
        validate_disposable_test_target("postgresql://user:pass@127.0.0.1:5432/rvfitness_test")

    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "false")
    with pytest.raises(RuntimeError, match="Destructive PostgreSQL tests require explicit opt-in"):
        validate_disposable_test_target("postgresql://user:pass@127.0.0.1:5432/rvfitness_test")


def test_rejects_missing_url(monkeypatch):
    """Verify that unset or empty POSTGRESQL_TEST_URL triggers immediate abort."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ValueError, match="POSTGRESQL_TEST_URL is unset or empty"):
        validate_disposable_test_target(None)

    with pytest.raises(ValueError, match="POSTGRESQL_TEST_URL is unset or empty"):
        validate_disposable_test_target("")

    with pytest.raises(ValueError, match="POSTGRESQL_TEST_URL is unset or empty"):
        validate_disposable_test_target("   ")


def test_rejects_unapproved_host(monkeypatch):
    """Verify that unapproved hosts are rejected and credentials in URL are masked in error."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APPROVED_POSTGRES_TEST_HOSTS", raising=False)

    rogue_url = "postgresql://u:RoguePass999@remote-prod-db.internal:5432/rvfitness_test"
    with pytest.raises(RuntimeError, match="is not an approved disposable test host") as exc_info:
        validate_disposable_test_target(rogue_url)

    # Password must be masked in exception
    assert "RoguePass999" not in str(exc_info.value)
    assert "***" in str(exc_info.value)


def test_rejects_protected_database_names(monkeypatch):
    """Verify that database names mentioning prod, staging, live, or system databases are rejected."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Protected keyword: prod
    with pytest.raises(RuntimeError, match="contains protected keyword"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/rvfitness_prod_test")

    # Protected keyword: staging
    with pytest.raises(RuntimeError, match="contains protected keyword"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/staging_test")

    # Protected keyword: live
    with pytest.raises(RuntimeError, match="contains protected keyword"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/live_test")

    # System database: postgres
    with pytest.raises(RuntimeError, match="is a system database"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/postgres")

    # Name without _test suffix: rvfitness_development
    with pytest.raises(RuntimeError, match="must explicitly end with '_test'"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/rvfitness_development")


def test_rejects_production_and_staging_environments(monkeypatch):
    """Verify that ENVIRONMENT=production or staging blocks destructive tests."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    test_url = "postgresql://u:p@127.0.0.1:5432/rvfitness_test"

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="cannot run when ENVIRONMENT=production"):
        validate_disposable_test_target(test_url)

    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(RuntimeError, match="cannot run when ENVIRONMENT=staging"):
        validate_disposable_test_target(test_url)


def test_rejects_unsupported_scheme(monkeypatch):
    """Verify that non-PostgreSQL URLs are rejected."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ValueError, match="Only PostgreSQL disposable test databases are permitted"):
        validate_disposable_test_target("sqlite:///./test.db")


def test_dedicated_role_validation(monkeypatch):
    """Verify that expected dedicated test role is enforced when configured."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("EXPECTED_POSTGRES_TEST_USER", "rvf_test_runner")

    # Mismatched user
    with pytest.raises(RuntimeError, match="does not match expected integration test role 'rvf_test_runner'"):
        validate_disposable_test_target("postgresql://wrong_user:p@127.0.0.1:5432/rvfitness_test")

    # Matching user
    result = validate_disposable_test_target("postgresql://rvf_test_runner:p@127.0.0.1:5432/rvfitness_test")
    assert result["user"] == "rvf_test_runner"
    assert result["status"] == "preflight_ok"


def test_approved_disposable_test_target_succeeds(monkeypatch):
    """Verify that valid target with opt-in succeeds and returns expected metadata."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("EXPECTED_POSTGRES_TEST_USER", raising=False)

    url = "postgresql+psycopg2://postgres:secret123@127.0.0.1:5432/rvfitness_test"
    result = validate_disposable_test_target(url)

    assert result["status"] == "preflight_ok"
    assert result["database"] == "rvfitness_test"
    assert result["host"] == "127.0.0.1"
    assert result["user"] == "postgres"
    assert "secret123" not in result["sanitized_url"]


def test_verify_live_database_identity_rejects_catalog_mismatch():
    """Verify that live connection returning unexpected catalog triggers fail closed."""
    mock_connector = lambda: {
        "database": "rvfitness_production",
        "user": "postgres",
        "server_ip": "127.0.0.1",
    }
    with pytest.raises(RuntimeError, match="Live connected database 'rvfitness_production' does not match expected test database 'rvfitness_test'"):
        verify_live_database_identity(mock_connector, expected_db="rvfitness_test")


def test_verify_live_database_identity_rejects_unapproved_server_ip():
    """Verify that live connection resolving to unapproved network address triggers fail closed."""
    mock_connector = lambda: {
        "database": "rvfitness_test",
        "user": "postgres",
        "server_ip": "198.51.100.44",
    }
    with pytest.raises(RuntimeError, match="Connected server IP address '198.51.100.44' is not an approved test host"):
        verify_live_database_identity(
            mock_connector,
            expected_db="rvfitness_test",
            approved_hosts=["127.0.0.1", "localhost"],
        )


def test_verify_live_database_identity_succeeds():
    """Verify that live connection matching expected database and approved host succeeds."""
    mock_connector = lambda: {
        "database": "rvfitness_test",
        "user": "postgres",
        "server_ip": "127.0.0.1",
    }
    res = verify_live_database_identity(mock_connector, expected_db="rvfitness_test")
    assert res["status"] == "verified"
    assert res["database"] == "rvfitness_test"
    assert res["user"] == "postgres"


def test_approved_ports_succeed(monkeypatch):
    """Verify that default approved ports (5432, 15432, 5433) are accepted."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APPROVED_POSTGRES_TEST_PORTS", raising=False)

    for port in [5432, 15432, 5433]:
        url = f"postgresql://u:p@127.0.0.1:{port}/rvfitness_test"
        res = validate_disposable_test_target(url)
        assert res["port"] == port


def test_unapproved_port_rejected(monkeypatch):
    """Verify that unapproved port is rejected and credentials remain masked."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APPROVED_POSTGRES_TEST_PORTS", raising=False)

    rogue_url = "postgresql://user:SecretTunnelPassword@127.0.0.1:54320/rvfitness_test"
    with pytest.raises(RuntimeError, match="is not an approved disposable test port") as exc_info:
        validate_disposable_test_target(rogue_url)

    assert "SecretTunnelPassword" not in str(exc_info.value)
    assert "***" in str(exc_info.value)


def test_invalid_port_range_rejected(monkeypatch):
    """Verify that out-of-range port numbers raise ValueError."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    with pytest.raises(ValueError, match="out of.*range"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:70000/rvfitness_test")


def test_malformed_approved_ports_environment_variable(monkeypatch):
    """Verify that malformed APPROVED_POSTGRES_TEST_PORTS fails closed."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    monkeypatch.setenv("APPROVED_POSTGRES_TEST_PORTS", "abc,5432")
    with pytest.raises(ValueError, match="contains invalid port 'abc'"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/rvfitness_test")

    monkeypatch.setenv("APPROVED_POSTGRES_TEST_PORTS", "-500")
    with pytest.raises(ValueError, match="out of valid range"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:5432/rvfitness_test")


def test_environment_override_approved_ports(monkeypatch):
    """Verify that valid APPROVED_POSTGRES_TEST_PORTS override functions properly."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Set custom allowed ports
    monkeypatch.setenv("APPROVED_POSTGRES_TEST_PORTS", "5432,25432")

    # Port 25432 accepted
    res = validate_disposable_test_target("postgresql://u:p@127.0.0.1:25432/rvfitness_test")
    assert res["port"] == 25432

    # Port 15432 is no longer approved under this custom override
    with pytest.raises(RuntimeError, match="Port '15432' is not an approved disposable test port"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:15432/rvfitness_test")


def test_port_rejection_occurs_before_database_connection(monkeypatch):
    """Verify that port rejection happens in static preflight before opening any socket."""
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "true")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Completely non-existent unreachable port 59999
    with pytest.raises(RuntimeError, match="Port '59999' is not an approved disposable test port"):
        validate_disposable_test_target("postgresql://u:p@127.0.0.1:59999/rvfitness_test")

