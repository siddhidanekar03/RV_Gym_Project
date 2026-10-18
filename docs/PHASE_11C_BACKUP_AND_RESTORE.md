# RVFitness Phase 11C: Safe Backup and Recovery Verification Runbook

## 1. Executive Summary

Phase 11C establishes, validates, and documents an enterprise-grade, non-destructive PostgreSQL backup and restore verification workflow for the RVFitness platform. All backup artifacts are structured under the primary backup destination on the `E:` drive:

`E:\RVFitnessBackup\RVFitness\YYYY-MM-DD_HH-mm-ss\`

This runbook documents:
1. Complete database identity verification before initiating exports.
2. Non-destructive logical dump creation via `pg_dump` in both plain SQL text format (`.sql`) and PostgreSQL custom compressed archive format (`.dump`).
3. Cryptographic SHA-256 checksum generation (`SHA256SUMS`).
4. Structured JSON metadata generation (`backup_manifest.json`) with zero credentials or secrets.
5. Automated, isolated restore testing into a dedicated disposable container (`rvfitness_restore_verify_<timestamp>`), validating Alembic revision `007_workout_plans_and_progress`, all 30 application tables, row counts, and application smoke test queries.
6. Clean teardown of disposable resources without touching existing databases, containers, or named volumes.
7. Preservation of existing pre-verified backups on `E:\RVFitnessBackup\` (`rvfitness-staging.tar` and `rvfitness_smoke_backup.sql`).

---

## 2. Database Environment Identification and Segregation

To prevent cross-environment contamination and data corruption, the RVFitness architecture distinguishes five distinct database tiers:

| Tier | Database Name | Engine / Container | Volume / Storage | Purpose & Data Nature |
| :--- | :--- | :--- | :--- | :--- |
| **Development** | `rvfitness_dev.db` (historic) / local | SQLite / Local PostgreSQL | Local file / disk | Ephemeral local developer testing. |
| **Test** | `rvfitness_test` | `rvfitness_postgres_test` (port 5432) | Ephemeral container | Automated unit and integration test fixture. |
| **Integration** | `rvfitness_integration` | `rvfitness-integration-db` (port 15432) | `rvfitness_integration_data` | Destructive concurrency, race condition, and advisory lock tests. |
| **Smoke-Test Snapshot** | `rvfitness_smoke` | `rvfitness-smoke-db` (no host port) | `rvfitness_smoke_data` | Pre-deployment baseline snapshot. Fully migrated through revision 007 with verified smoke test state. |
| **Staging** | `rvfitness_staging` | `rvfitness_staging_db` (internal only) | `rvfitness_staging_db_data` | Staging deployment target defined in `docker-compose.staging.yml`. |

> [!IMPORTANT]
> Never assume similarly named databases contain the same data. Backups must strictly verify the live database name, user, and Alembic revision before dump creation.

---

## 3. Verified Backup Execution Evidence (Phase 11C)

- **Execution Timestamp**: `2026-10-16T10:59:07 UTC` (Local: `2026-10-16 16:29:06 IST`)
- **Target Destination**: `E:\RVFitnessBackup\RVFitness\2026-10-16_16-29-06\`
- **Source Container**: `rvfitness-smoke-db`
- **Source Database**: `rvfitness_smoke` (verified via `SELECT current_database()`)
- **Source Engine**: PostgreSQL 16.15 on x86_64-pc-linux-musl
- **Alembic Revision**: `007_workout_plans_and_progress`
- **Table Count**: 30 application tables

### 3.1 Created Artifacts and Cryptographic Checksums

| Filename | Format | Size (Bytes) | SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| `rvfitness_rvfitness_smoke.sql` | Plain SQL text | 92,807 | `93FFEDB9B6B7B980BDE73CACAC2DE8DAAFA64938A7779D581401310F4D47DF1B` |
| `rvfitness_rvfitness_smoke.dump` | PostgreSQL Custom Archive (`-F c`) | 105,936 | `C76C1EA4E605E3004E10C31FFC184E6C8958B17C5BF7EA692418F13CE388A3D0` |
| `SHA256SUMS` | Checksum manifest | 195 | Contains hashes for SQL and Custom dumps |
| `backup_manifest.json` | Metadata JSON | 1,413 | Full audit trail and database identity metadata |
| `backup.log` | Operation log | 469 | Sanitized execution log |
| `restore_verification_report.json` | Verification JSON | 317 | Automated restore pass/fail verification metrics |
| `restore_verification.log` | Restore log | 719 | Step-by-step container restore log |

### 3.2 Pre-Existing Backups Preserved Untouched

The pre-existing verified artifacts in `E:\RVFitnessBackup\` were verified completely untouched before and after the operation:
- `rvfitness-staging.tar` (100,232,192 bytes, SHA-256: `28B93AABB5B78446B39C5CAB503648A6E1546EEDE4D86D8217A7AEAD627C6868`)
- `rvfitness_smoke_backup.sql` (75,762 bytes, SHA-256: `B7C4A04BF647C953586CC75E2ABC45288EFBACE8FB169B091F1AFB0E6F4E167A`)

---

## 4. Isolated Restore Verification Results

The backup tool executed an end-to-end restore into an isolated, ephemeral container:
- **Disposable Container**: `rvfitness_restore_verify_1792148347_19248`
- **Ephemeral Database**: `rvfitness_restore_1792148347_19248`
- **Port Isolation**: Zero published host ports (avoiding any conflict with host port 5432).
- **Execution Time**: 4.49 seconds.
- **Verification Criteria**:
  1. Restore completed without errors.
  2. Database identity verified as `rvfitness_restore_1792148347_19248`.
  3. Alembic revision matched source exactly: `007_workout_plans_and_progress`.
  4. Table count matched source exactly: 30 tables.
  5. Application smoke queries succeeded on `users`, `branches`, `membership_plans`, and `workout_plans`.
- **Teardown**: Container `rvfitness_restore_verify_1792148347_19248` was stopped and deleted immediately after verification.

---

## 5. Operational Runbook

### 5.1 Creating a New Backup to E: Drive
Run the committed backup script from the project root:
```bash
python scripts/backup_and_restore.py --backup-root "E:\RVFitnessBackup" --container rvfitness-smoke-db --user rvfitness_smoke --db rvfitness_smoke
```

### 5.2 Verifying Checksums
Verify file integrity on the backup host:
```powershell
# PowerShell verification:
Get-FileHash E:\RVFitnessBackup\RVFitness\<timestamp>\*.* -Algorithm SHA256

# Linux / WSL verification:
cd /mnt/e/RVFitnessBackup/RVFitness/<timestamp> && sha256sum -c SHA256SUMS
```

### 5.3 Manual Restore Verification into Disposable Container
To manually test any dump artifact without modifying existing databases:
```bash
# 1. Spawn a disposable container
docker run -d --name rvfitness_manual_test_restore \
  -e POSTGRES_DB=rvfitness_test_disposable \
  -e POSTGRES_USER=test_runner \
  -e POSTGRES_PASSWORD=disposableFixturePass123 \
  postgres:16-alpine

# 2. Copy dump into container
docker cp "E:\RVFitnessBackup\RVFitness\<timestamp>\rvfitness_rvfitness_smoke.sql" rvfitness_manual_test_restore:/tmp/restore.sql

# 3. Restore schema and data
docker exec rvfitness_manual_test_restore psql -U test_runner -d rvfitness_test_disposable -f /tmp/restore.sql

# 4. Inspect tables and Alembic revision
docker exec rvfitness_manual_test_restore psql -U test_runner -d rvfitness_test_disposable -c \
  "SELECT version_num FROM alembic_version; SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

# 5. Clean up container
docker stop rvfitness_manual_test_restore && docker rm rvfitness_manual_test_restore
```

### 5.4 Troubleshooting and Recovery Steps
1. **If Backup Fails**:
   - Check `backup.log` in the target directory.
   - Verify PostgreSQL container is running: `docker ps`.
   - Check available space on E: drive: `Get-PSDrive E`.
   - Re-run backup tool after resolving container availability.
2. **If Restore Verification Fails**:
   - Check `restore_verification.log` for SQL execution errors.
   - Confirm checksum matches `SHA256SUMS`.
   - Ensure the restoring PostgreSQL engine version matches the dump version (PostgreSQL 16.x).
   - Never restore over production or staging databases until isolated tests pass cleanly.

---

## 6. Retention and Limitations

- **Local Retention Policy**: Maintain rolling backups on `E:\RVFitnessBackup\RVFitness\` for 14 days. Retain milestone release backups indefinitely.
- **Off-Site Limitation**: The `E:` drive is an on-premise local storage drive. It safeguards against logical data corruption, migration failures, and accidental deletions, but does NOT protect against host hardware failure, ransomware, or catastrophic site loss. Production deployments must configure automated replication to cloud object storage (AWS S3, Google Cloud Storage, or Azure Blob) with immutable object locks.
- **Automated Scheduling Status**: Automated host-level scheduling (cron or Windows Task Scheduler) is not yet active. Backups must be initiated manually as part of pre-deployment releases until Phase 12 infrastructure automation is implemented.
