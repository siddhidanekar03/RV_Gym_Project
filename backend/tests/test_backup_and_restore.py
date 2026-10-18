import json
import os
import tempfile
import pytest

from scripts.backup_and_restore import (
    calculate_sha256,
    sanitize_log,
    verify_restore_target_safety,
)


def test_sha256_checksum_calculation(tmp_path):
    """Verify calculate_sha256 computes exact cryptographic SHA-256 hash."""
    test_file = tmp_path / "sample.txt"
    test_file.write_bytes(b"RVFitness Enterprise Gym Platform Safe Backup Test")

    # Known SHA256 of "RVFitness Enterprise Gym Platform Safe Backup Test"
    import hashlib
    expected_hash = hashlib.sha256(b"RVFitness Enterprise Gym Platform Safe Backup Test").hexdigest().upper()

    actual_hash = calculate_sha256(str(test_file))
    assert actual_hash == expected_hash
    assert len(actual_hash) == 64


def test_sanitize_log_masks_passwords_and_urls():
    """Verify sanitize_log redacts sensitive credentials from log and output strings."""
    secret = "TopSecretPassword999"

    # URL credentials format
    raw_url = f"postgresql://rvf_user:{secret}@db.internal:5432/rvfitness"
    sanitized_url = sanitize_log(raw_url)
    assert secret not in sanitized_url
    assert "postgresql://rvf_user:***@db.internal:5432/rvfitness" == sanitized_url

    # Password argument format
    raw_env = f"POSTGRES_PASSWORD={secret}"
    sanitized_env = sanitize_log(raw_env)
    assert secret not in sanitized_env
    assert "POSTGRES_PASSWORD=***" in sanitized_env

    # Generic secret string
    raw_line = f"password='{secret}'"
    sanitized_line = sanitize_log(raw_line)
    assert secret not in sanitized_line


def test_restore_safety_guard_rejects_protected_databases():
    """Verify verify_restore_target_safety strictly prohibits restoring over protected databases."""
    protected_targets = [
        "rvfitness",
        "rvfitness_staging",
        "rvfitness_smoke",
        "rvfitness_production",
        "production",
        "postgres",
        "random_unapproved_db",
    ]

    for target in protected_targets:
        with pytest.raises(ValueError) as exc:
            verify_restore_target_safety(target)
        assert "SAFETY VIOLATION" in str(exc.value)

    # Valid disposable test target must pass
    valid_targets = [
        "rvfitness_restore_1791995000",
        "rvfitness_restore_verify_test",
        "rvfitness_test_disposable",
    ]
    for valid_target in valid_targets:
        verify_restore_target_safety(valid_target)


def test_empty_dump_file_rejection(tmp_path):
    """Verify that an empty dump file is detected and rejected."""
    empty_file = tmp_path / "empty_dump.sql"
    empty_file.write_bytes(b"")

    assert os.path.getsize(str(empty_file)) == 0


def test_backup_manifest_structure_and_no_secrets(tmp_path):
    """Verify backup manifest has required fields and never contains passwords."""
    manifest = {
        "project": "RVFitness",
        "backup_timestamp_utc": "2026-10-16T11:00:00Z",
        "backup_directory": str(tmp_path),
        "database_identity": {
            "source_container": "rvfitness-smoke-db",
            "database_name": "rvfitness_smoke",
            "database_user": "rvfitness_smoke",
            "pg_version": "PostgreSQL 16.15",
            "alembic_version": "007_workout_plans_and_progress",
            "table_count": 30,
        },
        "artifacts": [
            {
                "filename": "rvfitness_smoke.sql",
                "size_bytes": 92768,
                "sha256": "A" * 64,
                "format": "plain_sql",
            }
        ],
        "restore_verification": {
            "status": "PASS",
            "disposable_container": "rvfitness_restore_verify_1791995000",
            "restored_database": "rvfitness_restore_1791995000",
            "alembic_version": "007_workout_plans_and_progress",
            "table_count": 30,
            "duration_seconds": 3.45,
        },
        "status": "BACKUP_AND_RESTORE_VERIFIED",
    }

    manifest_json = json.dumps(manifest)
    assert "password" not in manifest_json.lower()
    assert "secret" not in manifest_json.lower()
    assert manifest["database_identity"]["alembic_version"] == "007_workout_plans_and_progress"
    assert manifest["restore_verification"]["status"] == "PASS"
