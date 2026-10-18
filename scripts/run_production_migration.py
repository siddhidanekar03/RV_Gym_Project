#!/usr/bin/env python3
"""
RVFitness Production Migration Preflight Wrapper.

Enforces strict deployment safety invariants before invoking Alembic DDL:
1. Production Target Guard: Validates host, user, database catalog, and ENVIRONMENT=production.
2. Verified Pre-Migration Backup Gate: Verifies that a valid, fresh baseline backup exists
   with verified restore status before any DDL statements are executed.
3. Invokes Alembic only after both gates pass cleanly.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from typing import Dict, Any

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from backend.app.cli.verify_production_migration_target import run_production_target_verification


def validate_backup_manifest(
    manifest_path: str,
    expected_db: str,
    max_age_hours: float = 24.0,
) -> Dict[str, Any]:
    """Validate that pre-migration backup manifest exists, is verified, and is fresh."""
    if not manifest_path or not manifest_path.strip():
        raise ValueError(
            "PREFLIGHT SAFETY VIOLATION: --backup-manifest is required for production migrations. "
            "Pass path to verified backup_manifest.json created prior to migration."
        )

    norm_path = os.path.abspath(manifest_path.strip())
    if not os.path.isfile(norm_path):
        raise ValueError(
            f"PREFLIGHT SAFETY VIOLATION: Backup manifest file not found: '{norm_path}'. "
            "Ensure a verified baseline backup was created before initiating migrations."
        )

    try:
        with open(norm_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        raise ValueError(f"PREFLIGHT SAFETY VIOLATION: Malformed backup manifest JSON: {exc}") from exc

    status = manifest.get("status")
    if status != "BACKUP_AND_RESTORE_VERIFIED":
        raise ValueError(
            f"PREFLIGHT SAFETY VIOLATION: Backup manifest status is '{status}'. "
            "Must be 'BACKUP_AND_RESTORE_VERIFIED' with confirmed disposable container restore."
        )

    db_meta = manifest.get("database_identity", {})
    manifest_db = db_meta.get("database_name", "").strip().lower()
    if manifest_db != expected_db.lower():
        raise ValueError(
            f"PREFLIGHT SAFETY VIOLATION: Backup manifest database '{manifest_db}' does not match "
            f"expected migration target database '{expected_db}'."
        )

    # Check timestamp freshness
    raw_ts = manifest.get("backup_timestamp_utc")
    if not raw_ts:
        raise ValueError("PREFLIGHT SAFETY VIOLATION: Backup manifest missing backup_timestamp_utc.")

    try:
        backup_dt = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        age_seconds = (now_dt - backup_dt).total_seconds()
        if age_seconds < -60:  # Allow 1 min clock skew
            raise ValueError(f"Backup manifest timestamp '{raw_ts}' is in the future.")
        if age_seconds > (max_age_hours * 3600):
            hours_old = round(age_seconds / 3600, 1)
            raise ValueError(
                f"PREFLIGHT SAFETY VIOLATION: Backup manifest is {hours_old} hours old (exceeds {max_age_hours}h limit). "
                "A fresh pre-migration backup must be taken immediately before deployment."
            )
    except Exception as exc:
        if "PREFLIGHT SAFETY VIOLATION" in str(exc):
            raise
        raise ValueError(f"Invalid timestamp in backup manifest: {exc}") from exc

    return manifest


def run_production_migration_preflight(
    backup_manifest_path: str,
    target_revision: str = "head",
    dry_run: bool = False,
) -> int:
    """Execute target guard and backup check before running Alembic migration."""
    print("=" * 70)
    print("RVFitness Production Migration Preflight Gate")
    print("=" * 70)

    # Gate 1: Production target verification
    print("[PREFLIGHT GATE 1/2] Verifying production database target...")
    target_info = run_production_target_verification()
    target_db = target_info["database"]
    print(f"  PASS: Production target verified ({target_db} on {target_info['host']})")

    # Gate 2: Pre-migration backup confirmation
    print("[PREFLIGHT GATE 2/2] Verifying pre-migration baseline backup manifest...")
    manifest = validate_backup_manifest(backup_manifest_path, expected_db=target_db)
    print(f"  PASS: Pre-migration backup confirmed ({manifest.get('backup_directory')})")
    print(f"        Manifest status: {manifest.get('status')}")

    if dry_run:
        print("[DRY-RUN] Both preflight gates passed. Skipping Alembic execution.")
        print("=" * 70)
        return 0

    print("-" * 70)
    print(f"Proceeding with Alembic upgrade to '{target_revision}'...")
    print("-" * 70)

    cmd = [sys.executable, "-m", "alembic", "upgrade", target_revision]
    res = subprocess.run(cmd, cwd=workspace_dir)
    if res.returncode != 0:
        print(f"[FAIL] Alembic upgrade returned non-zero code {res.returncode}", file=sys.stderr)
        return res.returncode

    print("=" * 70)
    print("[SUCCESS] Production migration completed successfully.")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description="RVFitness Production Migration Guard and Runner")
    parser.add_argument(
        "--backup-manifest",
        required=True,
        help="Path to verified pre-migration backup_manifest.json",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Target Alembic migration revision (default: head)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate preflight gates only without executing Alembic",
    )
    args = parser.parse_args()

    try:
        code = run_production_migration_preflight(
            backup_manifest_path=args.backup_manifest,
            target_revision=args.revision,
            dry_run=args.dry_run,
        )
        sys.exit(code)
    except Exception as exc:
        print(f"\n[ERROR] Production migration aborted: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
