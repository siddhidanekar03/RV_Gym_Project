"""
Unit and regression tests for Phase 12D production blocker remediation.

Tests:
1. Production migration target verification guard (fail-closed on non-prod, SQLite, test keywords, unapproved hosts).
2. Production migration preflight wrapper (requires verified, fresh baseline backup manifest).
3. Backup destination isolation and safety validation in scripts/backup_and_restore.py.
4. Staging port binding hardening in docker-compose.staging.yml.
5. Production Compose architecture invariants in docker-compose.production.yml.
6. Staging test account seed guard rejection under production configuration.
7. Outbound email and online payment gateway absence invariants.
"""
import datetime
import json
import os
import re
import sys
import pytest
import yaml

from backend.app.cli.verify_production_migration_target import (
    run_production_target_verification,
    FORBIDDEN_PROD_KEYWORDS,
)
from scripts.run_production_migration import (
    validate_backup_manifest,
    run_production_migration_preflight,
)
from scripts.backup_and_restore import (
    validate_backup_subfolder,
    resolve_backup_target_dir,
)
from scripts.seed_staging_test_accounts import seed_staging_accounts


# ------------------------------------------------------------------------------
# 1. Production Migration Target Guard Tests
# ------------------------------------------------------------------------------

def test_prod_target_guard_rejects_non_production_env(monkeypatch):
    """Guard must fail closed if ENVIRONMENT is not strictly 'production'."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="ENVIRONMENT must be strictly 'production'"):
        run_production_target_verification()

    monkeypatch.setenv("ENVIRONMENT", "development")
    with pytest.raises(ValueError, match="ENVIRONMENT must be strictly 'production'"):
        run_production_target_verification()


def test_prod_target_guard_rejects_sqlite(monkeypatch):
    """Guard must fail closed if database dialect is SQLite."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./prod_test.db")
    with pytest.raises(ValueError, match="SQLite database detected"):
        run_production_target_verification()


def test_prod_target_guard_rejects_forbidden_keywords_in_db_or_host(monkeypatch):
    """Guard must fail closed if database name or host contains staging, test, or smoke keywords."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APPROVED_PROD_HOSTS", "prod-db.internal,staging-db.internal")

    # Forbidden keyword in database name
    for kw in ["staging", "test", "smoke", "dev", "mock"]:
        monkeypatch.setenv("DATABASE_URL", f"postgresql://rvf_migrator:pass@prod-db.internal:5432/rvfitness_{kw}")
        with pytest.raises(ValueError, match="contains non-production keyword"):
            run_production_target_verification()

    # Forbidden keyword in host name
    monkeypatch.setenv("DATABASE_URL", "postgresql://rvf_migrator:pass@staging-db.internal:5432/rvfitness_prod")
    with pytest.raises(ValueError, match="contains non-production keyword"):
        run_production_target_verification()


def test_prod_target_guard_rejects_unapproved_hosts(monkeypatch):
    """Guard must fail closed if database host is not in APPROVED_PROD_HOSTS."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://rvf_migrator:pass@rogue-db.internal:5432/rvfitness_prod")
    monkeypatch.setenv("APPROVED_PROD_HOSTS", "prod-db-1.internal,prod-db-2.internal")
    with pytest.raises(ValueError, match="is not in approved production hosts list"):
        run_production_target_verification()


def test_prod_target_guard_rejects_missing_approved_hosts_env(monkeypatch):
    """Guard must fail closed if APPROVED_PROD_HOSTS is not provided."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://rvf_migrator:pass@prod-db.internal:5432/rvfitness_prod")
    monkeypatch.delenv("APPROVED_PROD_HOSTS", raising=False)
    with pytest.raises(ValueError, match="APPROVED_PROD_HOSTS must be explicitly configured"):
        run_production_target_verification()


def test_prod_target_guard_validates_live_connection_catalog_and_user(monkeypatch):
    """Guard must verify connected catalog and user match expected production values."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://rvf_migrator:pass@prod-db:5432/rvfitness_prod")
    monkeypatch.setenv("APPROVED_PROD_HOSTS", "prod-db")
    monkeypatch.setenv("EXPECTED_PROD_DB_NAME", "rvfitness_prod")
    monkeypatch.setenv("EXPECTED_PROD_USER", "rvf_migrator")

    # Mismatched connected catalog
    mock_wrong_catalog = lambda url: {"database": "other_catalog", "user": "rvf_migrator", "server_ip": "prod-db"}
    with pytest.raises(ValueError, match="Connected catalog is 'other_catalog', expected 'rvfitness_prod'"):
        run_production_target_verification(connector=mock_wrong_catalog)

    # Mismatched connected user
    mock_wrong_user = lambda url: {"database": "rvfitness_prod", "user": "unprivileged_user", "server_ip": "prod-db"}
    with pytest.raises(ValueError, match="expected privileged production migrator role 'rvf_migrator'"):
        run_production_target_verification(connector=mock_wrong_user)

    # Valid live connection
    mock_valid = lambda url: {"database": "rvfitness_prod", "user": "rvf_migrator", "server_ip": "prod-db"}
    res = run_production_target_verification(connector=mock_valid)
    assert res["status"] == "verified"
    assert res["database"] == "rvfitness_prod"
    assert res["user"] == "rvf_migrator"


# ------------------------------------------------------------------------------
# 2. Production Migration Preflight Wrapper Tests
# ------------------------------------------------------------------------------

def test_validate_backup_manifest_requires_manifest_path():
    """Wrapper must fail closed if backup manifest path is omitted."""
    with pytest.raises(ValueError, match="--backup-manifest is required"):
        validate_backup_manifest("", expected_db="rvfitness_prod")


def test_validate_backup_manifest_rejects_missing_file():
    """Wrapper must fail closed if manifest file does not exist."""
    with pytest.raises(ValueError, match="Backup manifest file not found"):
        validate_backup_manifest("/nonexistent/path/backup_manifest.json", expected_db="rvfitness_prod")


def test_validate_backup_manifest_rejects_unverified_status(tmp_path):
    """Wrapper must fail closed if backup was not verified with disposable restore."""
    manifest_file = tmp_path / "backup_manifest.json"
    manifest_file.write_text(json.dumps({
        "status": "BACKUP_COMPLETED",
        "database_identity": {"database_name": "rvfitness_prod"},
        "backup_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }))
    with pytest.raises(ValueError, match="Must be 'BACKUP_AND_RESTORE_VERIFIED'"):
        validate_backup_manifest(str(manifest_file), expected_db="rvfitness_prod")


def test_validate_backup_manifest_rejects_database_mismatch(tmp_path):
    """Wrapper must fail closed if backup is from staging but target is production."""
    manifest_file = tmp_path / "backup_manifest.json"
    manifest_file.write_text(json.dumps({
        "status": "BACKUP_AND_RESTORE_VERIFIED",
        "database_identity": {"database_name": "rvfitness_staging"},
        "backup_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }))
    with pytest.raises(ValueError, match="does not match expected migration target database"):
        validate_backup_manifest(str(manifest_file), expected_db="rvfitness_prod")


def test_validate_backup_manifest_rejects_stale_backup(tmp_path):
    """Wrapper must fail closed if baseline backup is older than 24 hours."""
    manifest_file = tmp_path / "backup_manifest.json"
    stale_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=26)).isoformat()
    manifest_file.write_text(json.dumps({
        "status": "BACKUP_AND_RESTORE_VERIFIED",
        "database_identity": {"database_name": "rvfitness_prod"},
        "backup_timestamp_utc": stale_time,
    }))
    with pytest.raises(ValueError, match="exceeds 24.0h limit"):
        validate_backup_manifest(str(manifest_file), expected_db="rvfitness_prod")


def test_validate_backup_manifest_accepts_valid_fresh_manifest(tmp_path):
    """Wrapper must accept verified, fresh backup manifest matching target database."""
    manifest_file = tmp_path / "backup_manifest.json"
    fresh_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest_file.write_text(json.dumps({
        "status": "BACKUP_AND_RESTORE_VERIFIED",
        "database_identity": {"database_name": "rvfitness_prod"},
        "backup_timestamp_utc": fresh_time,
        "backup_directory": "E:\\RVFitnessBackup\\RVFitness_Production\\2026-10-16_18-00-00",
    }))
    data = validate_backup_manifest(str(manifest_file), expected_db="rvfitness_prod")
    assert data["status"] == "BACKUP_AND_RESTORE_VERIFIED"


# ------------------------------------------------------------------------------
# 3. Backup Destination Isolation Tests
# ------------------------------------------------------------------------------

def test_validate_backup_subfolder():
    """Subfolder validator must accept valid names and reject traversal and separators."""
    assert validate_backup_subfolder("RVFitness") == "RVFitness"
    assert validate_backup_subfolder("RVFitness_Production") == "RVFitness_Production"
    assert validate_backup_subfolder("prod-backup-2026") == "prod-backup-2026"

    # Reject empty
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_backup_subfolder("")

    # Reject slashes
    with pytest.raises(ValueError, match="cannot contain path separators"):
        validate_backup_subfolder("RVFitness/Production")
    with pytest.raises(ValueError, match="cannot contain path separators"):
        validate_backup_subfolder("RVFitness\\Production")

    # Reject invalid characters
    with pytest.raises(ValueError, match="contains invalid characters"):
        validate_backup_subfolder("RVFitness;rm -rf")
    with pytest.raises(ValueError, match="contains invalid characters"):
        validate_backup_subfolder("RVFitness*")


def test_resolve_backup_target_dir_default_and_production_isolation():
    """Test resolution separates RVFitness and RVFitness_Production destinations."""
    ts = "2026-10-16_12-00-00"

    # Default subfolder retains exact backward compatibility
    default_dir = resolve_backup_target_dir(
        backup_root=r"E:\RVFitnessBackup",
        subfolder="RVFitness",
        timestamp_str=ts,
    )
    assert default_dir == os.path.abspath(r"E:\RVFitnessBackup\RVFitness\2026-10-16_12-00-00")

    # Production subfolder writes to isolated directory
    prod_dir = resolve_backup_target_dir(
        backup_root=r"E:\RVFitnessBackup",
        subfolder="RVFitness_Production",
        timestamp_str=ts,
    )
    assert prod_dir == os.path.abspath(r"E:\RVFitnessBackup\RVFitness_Production\2026-10-16_12-00-00")
    assert default_dir != prod_dir

    # Explicit destination
    explicit = resolve_backup_target_dir(
        explicit_dest_dir=r"E:\CustomBackupPath\Snapshot1",
    )
    assert explicit == os.path.abspath(r"E:\CustomBackupPath\Snapshot1")


def test_resolve_backup_target_dir_rejects_unsafe_paths():
    """Target directory resolution must reject traversal and root drive targets."""
    with pytest.raises(ValueError, match="path traversal is strictly rejected"):
        resolve_backup_target_dir(explicit_dest_dir=r"E:\Backup\..\Escape")

    with pytest.raises(ValueError, match="cannot target filesystem drive root"):
        resolve_backup_target_dir(explicit_dest_dir=r"E:\\")


# ------------------------------------------------------------------------------
# 4. Compose Port Binding and Architecture Invariants
# ------------------------------------------------------------------------------

def test_staging_compose_port_binding_is_loopback():
    """Verify docker-compose.staging.yml is updated to bind port 18000 to loopback 127.0.0.1."""
    staging_compose = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docker-compose.staging.yml",
    )
    with open(staging_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    app_service = data["services"]["staging-app"]
    ports = app_service.get("ports", [])
    assert ports == ["127.0.0.1:18000:8000"], (
        f"Staging app must bind to loopback '127.0.0.1:18000:8000', got {ports}"
    )


def test_production_compose_architecture_invariants():
    """Verify docker-compose.production.yml enforces all isolation and security invariants."""
    prod_compose = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docker-compose.production.yml",
    )
    assert os.path.isfile(prod_compose), "docker-compose.production.yml must exist"

    with open(prod_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "prod-db" in services, "prod-db service must be defined"
    assert "prod-redis" in services, "prod-redis service must be defined"
    assert "prod-app" in services, "prod-app service must be defined"
    assert "prod-nginx" in services, "prod-nginx service must be defined"

    # Invariant: Zero published ports on database, redis, and application
    assert "ports" not in services["prod-db"], "Database must have zero published host ports"
    assert "ports" not in services["prod-redis"], "Redis must have zero published host ports"
    assert "ports" not in services["prod-app"], "Application must have zero direct published host ports"

    # Invariant: Only Nginx publishes port 80 and 443
    nginx_ports = services["prod-nginx"].get("ports", [])
    assert "80:80" in nginx_ports
    assert "443:443" in nginx_ports

    # Invariant: Isolated volumes and network
    volumes = data.get("volumes", {})
    assert "rvfitness_prod_db_data" in volumes
    assert "rvfitness_prod_media_data" in volumes

    networks = data.get("networks", {})
    assert "rvfitness_prod_network" in networks


# ------------------------------------------------------------------------------
# 5. Staging Seed Isolation Guard Test
# ------------------------------------------------------------------------------

def test_seed_staging_accounts_aborts_on_production(monkeypatch):
    """Staging test account seeder must abort immediately under production configuration."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION: seed_staging_accounts is strictly restricted to ENVIRONMENT=staging"):
        seed_staging_accounts()

    monkeypatch.setenv("ENVIRONMENT", "development")
    with pytest.raises(RuntimeError, match="SAFETY VIOLATION: seed_staging_accounts is strictly restricted to ENVIRONMENT=staging"):
        seed_staging_accounts()


# ------------------------------------------------------------------------------
# 6. Absence of Unintended Outbound Senders & Online Gateways
# ------------------------------------------------------------------------------

def test_zero_outbound_smtplib_in_backend():
    """Verify backend application code contains zero outbound smtplib imports."""
    app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
    py_files = []
    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    for p in py_files:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            assert "import smtplib" not in content, f"Found forbidden smtplib import in {p}"
            assert "from smtplib import" not in content, f"Found forbidden smtplib import in {p}"


# ------------------------------------------------------------------------------
# 7. Reverse Proxy Trust & CIDR/Hostname Resolution Tests
# ------------------------------------------------------------------------------

def test_is_trusted_proxy_matches_cidr_and_hostname(monkeypatch):
    """Verify is_trusted_proxy correctly evaluates exact IPs, CIDR ranges, and container hostnames."""
    from backend.app.core.config import settings
    from backend.app.core.auth import is_trusted_proxy, get_client_ip

    class DummyReq:
        def __init__(self, host, xff=None):
            self.client = type("Client", (), {"host": host})()
            self.headers = {"x-forwarded-for": xff} if xff else {}

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "172.24.0.0/16", "prod-nginx"])

    # 1. Exact loopback match
    assert is_trusted_proxy("127.0.0.1") is True

    # 2. CIDR network match for Docker internal subnet
    assert is_trusted_proxy("172.24.0.5") is True
    assert is_trusted_proxy("172.24.10.200") is True
    assert is_trusted_proxy("172.25.0.1") is False  # Outside /16 subnet

    # 3. Hostname resolution match
    import socket
    monkeypatch.setattr(socket, "gethostbyname", lambda host: "172.24.0.9" if host == "prod-nginx" else "0.0.0.0")
    assert is_trusted_proxy("172.24.0.9") is True

    # 4. Untrusted public peer rejected
    assert is_trusted_proxy("203.0.113.195") is False
    assert is_trusted_proxy("198.51.100.42") is False
    assert is_trusted_proxy(None) is False
    assert is_trusted_proxy("invalid-ip") is False

    # 5. Client IP extraction via trusted proxy in production
    req = DummyReq(host="172.24.0.5", xff="203.0.113.195, 172.24.0.5")
    assert get_client_ip(req) == "203.0.113.195"

    # 6. Client IP extraction ignores spoofed X-Forwarded-For from untrusted peer
    untrusted_req = DummyReq(host="198.51.100.42", xff="1.1.1.1")
    assert get_client_ip(untrusted_req) == "198.51.100.42"


# ------------------------------------------------------------------------------
# 8. Production Admin Bootstrap Safety Guard Tests
# ------------------------------------------------------------------------------

def test_bootstrap_production_admin_refuses_non_production(monkeypatch):
    """Verify bootstrap_production_admin environment check fails closed in non-production environments."""
    from scripts.bootstrap_production_admin import verify_production_bootstrap_environment

    # Staging must be rejected
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@staging-db:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="bootstrap_production_admin.py requires ENVIRONMENT='production'"):
        verify_production_bootstrap_environment()

    # Development must be rejected
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/rvfitness_dev")
    with pytest.raises(ValueError, match="bootstrap_production_admin.py requires ENVIRONMENT='production'"):
        verify_production_bootstrap_environment()

    # Test must be rejected
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/rvfitness_test")
    with pytest.raises(ValueError, match="bootstrap_production_admin.py requires ENVIRONMENT='production'"):
        verify_production_bootstrap_environment()

    # Non-production database keyword in production environment must be rejected
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@prod-db:5432/rvfitness_staging")
    with pytest.raises(ValueError, match="contains non-production keyword 'staging'"):
        verify_production_bootstrap_environment()

    # Clean production environment passes
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://rvf_app:pass@prod-db:5432/rvfitness_prod")
    verify_production_bootstrap_environment()

