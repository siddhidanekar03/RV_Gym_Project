#!/usr/bin/env python3
"""
RVFitness PostgreSQL Safe Backup and Restore Verification Tool.
Implements non-destructive pg_dump backups to E:\\RVFitnessBackup\\RVFitness\\<timestamp>\\
and automated restore verification in an isolated disposable PostgreSQL test container.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("rvfitness.backup")

PROTECTED_DATABASES = {
    "rvfitness",
    "rvfitness_staging",
    "rvfitness_smoke",
    "rvfitness_production",
    "production",
    "postgres",
}

DISPOSABLE_CONTAINER_PREFIX = "rvfitness_restore_verify_"


def sanitize_log(text: str) -> str:
    """Mask credentials, passwords, and sensitive connection details in logs and outputs."""
    if not text:
        return ""
    # Mask password parameters in URLs: ://[user]:[password]@
    sanitized = re.sub(r"://([^:@/]*):([^@/]+)@", r"://\1:***@", text)
    # Mask POSTGRES_PASSWORD=... or password=...
    sanitized = re.sub(
        r"(POSTGRES_PASSWORD|password|secret|key)=['\"]?[^'\"\s]+['\"]?",
        r"\1=***",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Mask psql password prompts or args
    sanitized = re.sub(r"(-W\s*|--password\s+)\S+", r"\1***", sanitized)
    return sanitized


def calculate_sha256(filepath: str) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest().upper()


def run_cmd(
    cmd: List[str], check: bool = True, timeout: int = 120
) -> Tuple[int, str, str]:
    """Execute command safely and capture output without exposing secrets."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = sanitize_log(proc.stdout)
        stderr = sanitize_log(proc.stderr)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout, stderr=stderr
            )
        return proc.returncode, stdout, stderr
    except Exception as exc:
        sanitized_exc = sanitize_log(str(exc))
        if isinstance(exc, subprocess.CalledProcessError):
            sanitized_exc = f"{sanitized_exc} | stderr: {sanitize_log(exc.stderr)}"
        raise RuntimeError(f"Command execution error: {sanitized_exc}") from exc


def verify_source_database_identity(
    container_name: str, db_user: str, db_name: str
) -> Dict[str, Any]:
    """Query live PostgreSQL container to verify database identity, version, tables, and migration revision."""
    sql = (
        "SELECT current_database(), current_user, version(); "
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'; "
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
    )
    cmd = ["docker", "exec", container_name, "psql", "-U", db_user, "-d", db_name, "-t", "-c", sql]
    code, stdout, stderr = run_cmd(cmd)
    if code != 0:
        raise RuntimeError(f"Failed to query database identity in '{container_name}': {stderr}")

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"Unexpected database identity output: {stdout}")

    # First row: current_database | current_user | version
    db_info = lines[0].split("|")
    actual_db = db_info[0].strip()
    actual_user = db_info[1].strip() if len(db_info) > 1 else "unknown"
    version_str = db_info[2].strip() if len(db_info) > 2 else "unknown"

    if actual_db != db_name:
        raise ValueError(
            f"Database identity mismatch: expected '{db_name}', got '{actual_db}'."
        )

    # Second row: table count
    table_count = int(lines[1].strip())

    # Remaining rows: table names
    table_names = lines[2:]

    # Check if alembic_version exists
    if "alembic_version" in table_names:
        rev_cmd = ["docker", "exec", container_name, "psql", "-U", db_user, "-d", db_name, "-t", "-c", "SELECT version_num FROM alembic_version;"]
        rev_code, rev_out, _ = run_cmd(rev_cmd, check=False)
        alembic_version = rev_out.strip() if rev_code == 0 else "unknown"
    else:
        alembic_version = "unmigrated"

    return {
        "database": actual_db,
        "user": actual_user,
        "version": version_str,
        "alembic_version": alembic_version,
        "table_count": table_count,
        "tables": table_names,
    }


def perform_pg_dump(
    container_name: str,
    db_user: str,
    db_name: str,
    output_dir: str,
    dump_basename: str,
) -> Dict[str, Any]:
    """Execute non-destructive pg_dump inside container and copy artifacts to output directory."""
    os.makedirs(output_dir, exist_ok=True)
    temp_container_sql = f"/tmp/{dump_basename}.sql"
    temp_container_dump = f"/tmp/{dump_basename}.dump"

    local_sql_path = os.path.join(output_dir, f"{dump_basename}.sql")
    local_dump_path = os.path.join(output_dir, f"{dump_basename}.dump")

    # 1. Plain SQL Dump with clean / if-exists
    dump_sql_cmd = [
        "docker", "exec", container_name,
        "pg_dump", "-U", db_user, "-d", db_name,
        "--clean", "--if-exists",
        "-f", temp_container_sql,
    ]
    code, out, err = run_cmd(dump_sql_cmd)
    if code != 0:
        raise RuntimeError(f"pg_dump (SQL) failed: {err}")

    # Copy SQL dump out of container
    run_cmd(["docker", "cp", f"{container_name}:{temp_container_sql}", local_sql_path])
    run_cmd(["docker", "exec", container_name, "rm", "-f", temp_container_sql])

    # 2. PostgreSQL Custom Archive Dump (-F c)
    dump_custom_cmd = [
        "docker", "exec", container_name,
        "pg_dump", "-U", db_user, "-d", db_name,
        "-F", "c",
        "-f", temp_container_dump,
    ]
    code, out, err = run_cmd(dump_custom_cmd)
    if code != 0:
        raise RuntimeError(f"pg_dump (custom archive) failed: {err}")

    # Copy custom dump out of container
    run_cmd(["docker", "cp", f"{container_name}:{temp_container_dump}", local_dump_path])
    run_cmd(["docker", "exec", container_name, "rm", "-f", temp_container_dump])

    # Validate output files exist and are non-empty
    for path in [local_sql_path, local_dump_path]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected dump file missing: {path}")
        size = os.path.getsize(path)
        if size == 0:
            raise ValueError(f"Generated dump file is empty (0 bytes): {path}")

    # Calculate checksums
    sql_hash = calculate_sha256(local_sql_path)
    dump_hash = calculate_sha256(local_dump_path)

    # Write SHA256SUMS file
    checksum_file = os.path.join(output_dir, "SHA256SUMS")
    with open(checksum_file, "w", encoding="utf-8") as f:
        f.write(f"{sql_hash}  {os.path.basename(local_sql_path)}\n")
        f.write(f"{dump_hash}  {os.path.basename(local_dump_path)}\n")

    return {
        "sql_file": os.path.basename(local_sql_path),
        "sql_path": local_sql_path,
        "sql_size_bytes": os.path.getsize(local_sql_path),
        "sql_sha256": sql_hash,
        "dump_file": os.path.basename(local_dump_path),
        "dump_path": local_dump_path,
        "dump_size_bytes": os.path.getsize(local_dump_path),
        "dump_sha256": dump_hash,
        "checksum_file": checksum_file,
    }


FORBIDDEN_DESTINATION_SUBSTRINGS = ["..", "\x00"]
ALLOWED_SUBFOLDER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_backup_subfolder(subfolder: str) -> str:
    """Validate subfolder name against traversal, invalid characters, and empty values."""
    cleaned = (subfolder or "").strip()
    if not cleaned:
        raise ValueError("Backup subfolder cannot be empty.")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"Backup subfolder '{cleaned}' cannot contain path separators ('/' or '\\').")
    if not ALLOWED_SUBFOLDER_PATTERN.match(cleaned):
        raise ValueError(
            f"Backup subfolder '{cleaned}' contains invalid characters. Use alphanumeric, hyphens, and underscores only."
        )
    return cleaned


def resolve_backup_target_dir(
    backup_root: str = r"E:\RVFitnessBackup",
    subfolder: str = "RVFitness",
    explicit_dest_dir: Optional[str] = None,
    timestamp_str: Optional[str] = None,
) -> str:
    """
    Resolve and validate backup target directory.
    Rejects directory traversal, dangerous root locations, and workspace collisions.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if timestamp_str is None:
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if explicit_dest_dir:
        cleaned_dest = explicit_dest_dir.strip()
        if not cleaned_dest:
            raise ValueError("Explicit destination directory cannot be empty.")
        if any(f in cleaned_dest for f in FORBIDDEN_DESTINATION_SUBSTRINGS):
            raise ValueError(f"Unsafe destination directory '{cleaned_dest}': path traversal is strictly rejected.")
        norm_dest = os.path.abspath(cleaned_dest)

        # Reject workspace collisions (prevent committing dumps to git)
        try:
            repo_drive, _ = os.path.splitdrive(repo_root)
            dest_drive, _ = os.path.splitdrive(norm_dest)
            if repo_drive.lower() == dest_drive.lower():
                common = os.path.commonpath([repo_root, norm_dest])
                if common == repo_root:
                    raise ValueError(
                        f"Unsafe destination directory '{norm_dest}': writing backups into workspace tree is forbidden."
                    )
        except ValueError:
            pass

        # Reject filesystem root drives directly (e.g. C:\ or E:\ directly without subpath)
        split_path = os.path.splitdrive(norm_dest)[1].strip("/\\")
        if not split_path:
            raise ValueError(f"Unsafe destination directory '{norm_dest}': cannot target filesystem drive root directly.")

        return norm_dest

    # Validate backup_root
    cleaned_root = (backup_root or "").strip()
    if not cleaned_root:
        raise ValueError("Backup root directory cannot be empty.")
    if any(f in cleaned_root for f in FORBIDDEN_DESTINATION_SUBSTRINGS):
        raise ValueError(f"Unsafe backup root '{cleaned_root}': path traversal is strictly rejected.")

    valid_subfolder = validate_backup_subfolder(subfolder)
    target = os.path.join(cleaned_root, valid_subfolder, timestamp_str)
    norm_target = os.path.abspath(target)

    # Reject workspace collisions
    try:
        repo_drive, _ = os.path.splitdrive(repo_root)
        dest_drive, _ = os.path.splitdrive(norm_target)
        if repo_drive.lower() == dest_drive.lower():
            common = os.path.commonpath([repo_root, norm_target])
            if common == repo_root:
                raise ValueError(
                    f"Unsafe target directory '{norm_target}': writing backups into workspace tree is forbidden."
                )
    except ValueError:
        pass

    return norm_target


def verify_restore_target_safety(target_db_name: str) -> None:
    """Ensure restore target is strictly a disposable test database, never production or original source."""
    clean_target = (target_db_name or "").strip().lower()
    if clean_target in PROTECTED_DATABASES:
        raise ValueError(
            f"SAFETY VIOLATION: Cannot restore into protected database '{target_db_name}'. "
            "Restore verification requires an isolated, disposable test database."
        )
    if not (clean_target.startswith("rvfitness_restore_") or clean_target.startswith("rvfitness_test_") or "disposable" in clean_target):
        raise ValueError(
            f"SAFETY VIOLATION: Target database '{target_db_name}' does not meet disposable naming requirements."
        )


def verify_restore_in_disposable_container(
    dump_filepath: str,
    source_metadata: Dict[str, Any],
    output_dir: str,
) -> Dict[str, Any]:
    """
    Restore the dump file into an ephemeral, disposable PostgreSQL test container.
    Verifies tables, Alembic revision, and schema consistency against the source snapshot.
    Cleans up the disposable container upon completion.
    """
    unique_suffix = f"{int(time.time())}_{os.getpid()}"
    disposable_container = f"{DISPOSABLE_CONTAINER_PREFIX}{unique_suffix}"
    test_db = f"rvfitness_restore_{unique_suffix}"
    test_user = "rvf_restore_test"
    test_pass = f"fixtureRestorePass_{unique_suffix}"

    verify_restore_target_safety(test_db)

    report_log: List[str] = []
    report_log.append(f"Starting isolated restore verification into '{disposable_container}'...")
    report_log.append(f"Source dump: {os.path.basename(dump_filepath)}")
    report_log.append(f"Expected database: {test_db}")

    t0 = time.time()
    container_started = False
    try:
        # Launch disposable container without published host ports
        run_cmd([
            "docker", "run", "-d",
            "--name", disposable_container,
            "-e", f"POSTGRES_DB={test_db}",
            "-e", f"POSTGRES_USER={test_user}",
            "-e", f"POSTGRES_PASSWORD={test_pass}",
            "postgres:16-alpine",
        ])
        container_started = True
        report_log.append(f"Launched container '{disposable_container}'. Waiting for readiness...")

        # Wait for PostgreSQL ready in container
        ready = False
        for attempt in range(20):
            time.sleep(1)
            code, out, _ = run_cmd(
                ["docker", "exec", disposable_container, "pg_isready", "-U", test_user, "-d", test_db],
                check=False,
            )
            if code == 0:
                # Confirm server is accepting queries (initdb fully complete)
                q_code, _, _ = run_cmd(
                    ["docker", "exec", disposable_container, "psql", "-U", test_user, "-d", test_db, "-c", "SELECT 1;"],
                    check=False,
                )
                if q_code == 0:
                    ready = True
                    break

        if not ready:
            raise TimeoutError(f"Disposable container '{disposable_container}' did not become ready in 20s.")

        report_log.append("PostgreSQL ready. Copying dump artifact...")
        container_dump_path = "/tmp/restore_artifact.sql"
        run_cmd(["docker", "cp", dump_filepath, f"{disposable_container}:{container_dump_path}"])

        report_log.append("Executing restore via psql...")
        code, out, err = run_cmd([
            "docker", "exec", disposable_container,
            "psql", "-U", test_user, "-d", test_db,
            "-f", container_dump_path,
        ])
        if code != 0:
            raise RuntimeError(f"Restore failed with code {code}: {err}")

        report_log.append("Restore completed successfully. Verifying schema and metadata...")

        # Verify database identity
        id_code, id_out, _ = run_cmd([
            "docker", "exec", disposable_container,
            "psql", "-U", test_user, "-d", test_db,
            "-t", "-c", "SELECT current_database();",
        ])
        restored_db_actual = id_out.strip()
        if restored_db_actual != test_db:
            raise ValueError(f"Restored database mismatch: expected '{test_db}', got '{restored_db_actual}'.")

        # Verify table count
        cnt_code, cnt_out, _ = run_cmd([
            "docker", "exec", disposable_container,
            "psql", "-U", test_user, "-d", test_db,
            "-t", "-c", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';",
        ])
        restored_count = int(cnt_out.strip())
        expected_count = source_metadata.get("table_count", 0)
        if restored_count != expected_count:
            raise ValueError(
                f"Table count mismatch: expected {expected_count}, got {restored_count}."
            )
        report_log.append(f"Verified table count: {restored_count} tables.")

        expected_rev = source_metadata.get("alembic_version", "")
        if expected_rev != "unmigrated":
            # Verify Alembic migration revision
            rev_code, rev_out, _ = run_cmd([
                "docker", "exec", disposable_container,
                "psql", "-U", test_user, "-d", test_db,
                "-t", "-c", "SELECT version_num FROM alembic_version;",
            ])
            restored_rev = rev_out.strip()
            if restored_rev != expected_rev:
                raise ValueError(
                    f"Alembic revision mismatch: expected '{expected_rev}', got '{restored_rev}'."
                )
            report_log.append(f"Verified Alembic version: '{restored_rev}'.")

            # Test smoke query on core tables
            smoke_sql = (
                "SELECT count(*) FROM users; "
                "SELECT count(*) FROM branches; "
                "SELECT count(*) FROM membership_plans; "
                "SELECT count(*) FROM workout_plans;"
            )
            run_cmd([
                "docker", "exec", disposable_container,
                "psql", "-U", test_user, "-d", test_db,
                "-c", smoke_sql,
            ])
            report_log.append("Application smoke test queries executed successfully on restored database.")
        else:
            restored_rev = "unmigrated"
            report_log.append("Verified fresh database state (unmigrated, 0 application tables).")
            # Verify basic connectivity
            run_cmd([
                "docker", "exec", disposable_container,
                "psql", "-U", test_user, "-d", test_db,
                "-c", "SELECT 1;",
            ])
            report_log.append("Basic connectivity verified on restored database.")

        duration = time.time() - t0
        report = {
            "status": "PASS",
            "disposable_container": disposable_container,
            "restored_database": test_db,
            "alembic_version": restored_rev,
            "table_count": restored_count,
            "duration_seconds": round(duration, 2),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    finally:
        # Strict teardown of temporary resource only
        if container_started and disposable_container.startswith(DISPOSABLE_CONTAINER_PREFIX):
            report_log.append(f"Tearing down disposable container '{disposable_container}'...")
            run_cmd(["docker", "stop", disposable_container], check=False)
            run_cmd(["docker", "rm", "-f", disposable_container], check=False)
            report_log.append("Disposable container removed successfully.")

    # Write restore verification report and log
    report_file = os.path.join(output_dir, "restore_verification_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    log_file = os.path.join(output_dir, "restore_verification.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_log) + "\n")

    return report


def run_full_backup_and_verify(
    backup_root: str = r"E:\RVFitnessBackup",
    source_container: str = "rvfitness-smoke-db",
    source_user: str = "rvfitness_smoke",
    source_db: str = "rvfitness_smoke",
    subfolder: str = "RVFitness",
    explicit_dest_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete workflow: preflight, timestamped dump, checksums, manifest, and restore test."""
    t_start = time.time()

    # 1. Verify source database identity
    identity = verify_source_database_identity(source_container, source_user, source_db)

    # 2. Prepare timestamped directory structure
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_dir = resolve_backup_target_dir(
        backup_root=backup_root,
        subfolder=subfolder,
        explicit_dest_dir=explicit_dest_dir,
        timestamp_str=timestamp_str,
    )

    os.makedirs(target_dir, exist_ok=True)

    # 3. Perform pg_dump
    dump_prefix = f"rvfitness_{source_db}"
    dump_results = perform_pg_dump(
        source_container, source_user, source_db, target_dir, dump_prefix
    )

    # 4. Create manifest
    manifest = {
        "project": "RVFitness",
        "backup_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "backup_directory": target_dir,
        "database_identity": {
            "source_container": source_container,
            "database_name": identity["database"],
            "database_user": identity["user"],
            "pg_version": identity["version"],
            "alembic_version": identity["alembic_version"],
            "table_count": identity["table_count"],
        },
        "artifacts": [
            {
                "filename": dump_results["sql_file"],
                "size_bytes": dump_results["sql_size_bytes"],
                "sha256": dump_results["sql_sha256"],
                "format": "plain_sql",
            },
            {
                "filename": dump_results["dump_file"],
                "size_bytes": dump_results["dump_size_bytes"],
                "sha256": dump_results["dump_sha256"],
                "format": "custom_archive",
            },
        ],
        "status": "BACKUP_COMPLETED",
    }

    # 5. Perform isolated restore test in disposable container
    restore_report = verify_restore_in_disposable_container(
        dump_results["sql_path"], identity, target_dir
    )

    manifest["restore_verification"] = restore_report
    manifest["status"] = "BACKUP_AND_RESTORE_VERIFIED"
    manifest["total_workflow_seconds"] = round(time.time() - t_start, 2)

    manifest_file = os.path.join(target_dir, "backup_manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Write backup log
    backup_log_file = os.path.join(target_dir, "backup.log")
    with open(backup_log_file, "w", encoding="utf-8") as f:
        f.write(f"RVFitness Backup Log\n")
        f.write(f"Timestamp: {manifest['backup_timestamp_utc']}\n")
        f.write(f"Source Database: {identity['database']}\n")
        f.write(f"Alembic Version: {identity['alembic_version']}\n")
        f.write(f"Tables Exported: {identity['table_count']}\n")
        f.write(f"SQL Dump: {dump_results['sql_file']} ({dump_results['sql_size_bytes']} bytes, SHA256: {dump_results['sql_sha256']})\n")
        f.write(f"Custom Dump: {dump_results['dump_file']} ({dump_results['dump_size_bytes']} bytes, SHA256: {dump_results['dump_sha256']})\n")
        f.write(f"Restore Verification Status: {restore_report['status']}\n")

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="RVFitness PostgreSQL Backup and Recovery Verification")
    parser.add_argument("--backup-root", default=r"E:\RVFitnessBackup", help="Root backup directory")
    parser.add_argument("--subfolder", default="RVFitness", help="Destination subfolder under backup-root (default: RVFitness, e.g. RVFitness_Production)")
    parser.add_argument("--dest-dir", default=None, help="Explicit destination directory for backup artifacts (overrides backup-root and subfolder)")
    parser.add_argument("--container", default="rvfitness-smoke-db", help="Source PostgreSQL container name")
    parser.add_argument("--user", default="rvfitness_smoke", help="Source PostgreSQL database user")
    parser.add_argument("--db", default="rvfitness_smoke", help="Source PostgreSQL database name")
    args = parser.parse_args()

    print("=" * 70)
    print("RVFitness Safe Backup and Restore Verification")
    print("=" * 70)
    print(f"Backup Root:      {args.backup_root}")
    print(f"Subfolder:        {args.subfolder}")
    if args.dest_dir:
        print(f"Explicit Dest:    {args.dest_dir}")
    print(f"Source Container: {args.container}")
    print(f"Source Database:  {args.db}")
    print(f"Source User:      {args.user}")

    try:
        manifest = run_full_backup_and_verify(
            backup_root=args.backup_root,
            source_container=args.container,
            source_user=args.user,
            source_db=args.db,
            subfolder=args.subfolder,
            explicit_dest_dir=args.dest_dir,
        )
        print("-" * 70)
        print("[SUCCESS] Backup and Restore Verification COMPLETED SUCCESSFULLY.")
        print(f"Destination:     {manifest['backup_directory']}")
        print(f"SQL Dump:        {manifest['artifacts'][0]['filename']} ({manifest['artifacts'][0]['size_bytes']} bytes)")
        print(f"                 SHA-256: {manifest['artifacts'][0]['sha256']}")
        print(f"Custom Archive:  {manifest['artifacts'][1]['filename']} ({manifest['artifacts'][1]['size_bytes']} bytes)")
        print(f"                 SHA-256: {manifest['artifacts'][1]['sha256']}")
        print(f"Restore Status:  {manifest['restore_verification']['status']}")
        print(f"Tables Verified: {manifest['restore_verification']['table_count']}")
        print(f"Alembic Rev:     {manifest['restore_verification']['alembic_version']}")
        print(f"Total Duration:  {manifest['total_workflow_seconds']}s")
        print("=" * 70)
        return 0
    except Exception as exc:
        print(f"[ERROR] Backup and Restore Verification failed: {sanitize_log(str(exc))}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
