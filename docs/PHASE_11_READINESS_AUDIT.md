# RVFitness: Phase 11 Readiness Audit and Next-Phase Planning Report

**Document Version:** 1.0.0  
**Audit Date:** 2026-10-16  
**Auditor:** Automated Architecture and Security Reviewer  
**Workspace Root:** `D:\RV_Gym_Project`  
**Active Branch:** `prithviraj-feature` (Commit: `6529abd`)  
**Overall Readiness Verdict:** CONDITIONALLY READY FOR CONTROLLED STAGING (Phase 11 Required for Operational Reliability)

---

## 1. Executive Summary

This readiness audit evaluated the actual state of the RVFitness repository following the implementation and verification of destructive PostgreSQL test safety guards. The review assessed operational resilience, security posture, multi-tenant isolation, data integrity, background maintenance, and compliance readiness prior to committing to isolated staging deployment.

### Key Audit Conclusions
1. **Core Application and Schema Health:** The backend test suite passes completely (201 offline unit/integration tests with 0 failures and 0 warnings, plus 19 dedicated PostgreSQL guard unit tests). The linear Alembic migration chain comprises 7 revisions terminating cleanly at head revision `007_workout_plans_and_progress`. Upgrades to head and downgrades to base are verified by automated tests.
2. **Frontend Distribution:** The React 19 / Vite frontend compiles successfully in 9.41s into static production distribution artifacts (`dist/`). Oxlint flags 10 React hook dependency warnings across 5 components with zero errors.
3. **Repository Hygiene:** The SQLite development database [rvfitness_dev.db](file:///d:/RV_Gym_Project/rvfitness_dev.db) is staged for deletion from the Git index (`git rm --cached`) while the physical 487,424-byte database file remains safely intact on disk. Both [.gitignore](file:///d:/RV_Gym_Project/.gitignore) and [backend/.gitignore](file:///d:/RV_Gym_Project/backend/.gitignore) properly ignore `.db` and all SQLite sidecars (`*.db-wal`, `*.db-shm`, `*.db-journal`).
4. **Primary Staging Gaps Identified:** 
   - Media upload directory divergence between [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging) line 43 (`/app/backend/app/uploads/announcements`) and [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py) line 96 (`/app/backend/uploads`), combined with the absence of a declared persistent docker volume mount.
   - In-memory rate limiting is isolated per process; multi-worker Uvicorn processes cannot share rate limit state without an external coordinator or Redis adapter.
   - Absorbance of expired tokens: Table `consumed_qr_tokens` and table `user_sessions` lack automated background cleanup cron or maintenance tasks, risking unbounded database bloat.
   - Database disaster recovery: Backup and restore procedures exist only as manual documentation in [DEPLOYMENT.md](file:///d:/RV_Gym_Project/DEPLOYMENT.md); automated backup, checksumming, and restore verification tests do not exist.
   - Statutory tax compliance: Invoice calculation in [backend/app/services/billing_service.py](file:///d:/RV_Gym_Project/backend/app/services/billing_service.py) hardcodes zero tax with placeholder GST text, lacking SAC 999723 classification, GSTIN tracking, and CGST/SGST/IGST tax breakdowns required for Indian commercial operations.

---

## 2. Verified Repository and Test Status

### A. Git Working Tree State
- **Branch:** `prithviraj-feature` tracking `origin/prithviraj-feature` at commit `6529abd`.
- **Staged Changes:**
  - `D  rvfitness_dev.db`: Removed from Git index. Physical file on disk verified at 487,424 bytes.
- **Modified Unstaged Files (16 files):**
  - [backend/.gitignore](file:///d:/RV_Gym_Project/backend/.gitignore): SQLite sidecar ignore rules.
  - [backend/app/api/v1/endpoints/announcements.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/announcements.py): Media upload validation and CSRF enforcement.
  - [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py): Production security validator, dedicated `QR_SIGNING_KEY` checks, and uploads path resolver.
  - [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py): Defensive security headers, correlation IDs, exception handlers, and SPA static fallback.
  - [backend/app/services/announcement_service.py](file:///d:/RV_Gym_Project/backend/app/services/announcement_service.py): Announcement query and status filters.
  - [backend/app/services/leaderboard_service.py](file:///d:/RV_Gym_Project/backend/app/services/leaderboard_service.py): Privacy opt-in filtering, tie-breaker ordering, points reversals.
  - [backend/requirements.txt](file:///d:/RV_Gym_Project/backend/requirements.txt): Core runtime dependencies.
  - [backend/tests/test_attendance.py](file:///d:/RV_Gym_Project/backend/tests/test_attendance.py): Attendance regression tests.
  - [backend/tests/test_attendance_adversarial.py](file:///d:/RV_Gym_Project/backend/tests/test_attendance_adversarial.py): QR replay, HMAC forgery, and time-drift test suite.
  - [backend/tests/test_auth.py](file:///d:/RV_Gym_Project/backend/tests/test_auth.py): Cookie security, session lifecycle, and authentication tests.
  - [backend/tests/test_authorization.py](file:///d:/RV_Gym_Project/backend/tests/test_authorization.py): Role-based access control and branch scope isolation tests.
  - [backend/tests/test_phase5_security_and_e2e.py](file:///d:/RV_Gym_Project/backend/tests/test_phase5_security_and_e2e.py): End-to-end operational flow verification.
  - [backend/tests/test_postgresql_integration.py](file:///d:/RV_Gym_Project/backend/tests/test_postgresql_integration.py): Hardened integration test suite with preflight target checks and live database identity verification.
  - [backend/tests/test_production_readiness_phase9.py](file:///d:/RV_Gym_Project/backend/tests/test_production_readiness_phase9.py): Security headers, proxy trust, and startup invariant checks.
  - [docker-compose.test.yml](file:///d:/RV_Gym_Project/docker-compose.test.yml): Test fixture credential hygiene documentation.
  - [scripts/verify_postgres_integration.py](file:///d:/RV_Gym_Project/scripts/verify_postgres_integration.py): Fail-closed verification script with credential masking.
- **Untracked Files:**
  - [.gitignore](file:///d:/RV_Gym_Project/.gitignore): Root repository ignore configuration.
  - [backend/app/core/postgres_test_guard.py](file:///d:/RV_Gym_Project/backend/app/core/postgres_test_guard.py): Fail-closed test target guard module.
  - [backend/tests/test_postgres_guard.py](file:///d:/RV_Gym_Project/backend/tests/test_postgres_guard.py): 19 offline guard unit tests.
  - [backend/uploads/announcements/.gitkeep](file:///d:/RV_Gym_Project/backend/uploads/announcements/.gitkeep): Local media directory placeholder.
  - [docs/security/POSTGRES_TEST_SAFETY_AUDIT.md](file:///d:/RV_Gym_Project/docs/security/POSTGRES_TEST_SAFETY_AUDIT.md): Test-safety audit report.

### B. Test Suite Execution Metrics
1. **PostgreSQL Test Safety Guard Suite:**
   - Command: `python -m pytest -q .\backend\tests\test_postgres_guard.py`
   - Result: 19 passed in 0.06s.
   - Target connections: 0 (Pure offline static validation).
2. **Non-PostgreSQL Comprehensive Suite:**
   - Command: `python -m pytest -q .\backend\tests --ignore=.\backend\tests\test_postgresql_integration.py`
   - Result: 201 passed in 196.20s (0 failures, 0 warnings, 0 errors).
   - Test categories covered: Unit, security, adversarial HMAC, session management, branch isolation, migrations lifecycle, health probes, and error handlers.
3. **Disposable PostgreSQL Integration Suite:**
   - Target: `rvfitness-integration-db` container on port 15432, database `rvfitness_test`, role `rvfitness_integration`.
   - Result: 4 passed in 2.72s. Live identity verified before destructive schema teardown and table deletions.
   - Negative rejection: Target on unapproved port (54320) rejected fail-closed before network socket initialization.
4. **Frontend Linter and Build:**
   - Command: `npm run lint; npm run build` (in `frontend/`)
   - Linter: Oxlint inspected 26 files with 104 rules; 0 errors, 10 warnings (cascading render and missing effect dependencies in admin/reporting components).
   - Compiler: Vite v8.3.4 compiled 1,973 modules in 9.41s, generating:
     - `dist/index.html` (0.97 kB)
     - `dist/assets/index-CB5X8mT9.css` (84.31 kB)
     - `dist/assets/index-BIDbRGxf.js` (441.16 kB)

### C. Docker and Container Infrastructure Status
- **Staging Image:** `rvfitness:staging` (ID: `491797a4baf0`, Virtual Size: 422MB).
- **Existing Containers:**
  - `rvfitness-integration-db` (postgres:16-alpine): Exited (0), volume `rvfitness_integration_data` preserved.
  - `rvfitness_staging_smoke` (rvfitness:staging): Exited (255), preserved.
  - `rvfitness-smoke-db` (postgres:16-alpine): Exited (255), volume `rvfitness_smoke_data` preserved.
  - `coverageiq-postgres` (pgvector:pg16, port 5432): External container running and preserved untouched.
- **Physical Backups on Disk:**
  - [backups/rvfitness-staging.tar](file:///d:/RV_Gym_Project/backups/rvfitness-staging.tar): 100,232,192 bytes.
  - [backups/rvfitness_smoke_backup.sql](file:///d:/RV_Gym_Project/backups/rvfitness_smoke_backup.sql): 75,762 bytes.

---

## 3. Readiness Matrix with Evidence

| Functional Subsystem | Classification | Evidence and File Paths | Current Test Coverage | Identified Gaps / Failure Modes |
| :--- | :--- | :--- | :--- | :--- |
| **In-Memory Rate Limiting** | **PARTIALLY VERIFIED** | [backend/app/core/rate_limit.py](file:///d:/RV_Gym_Project/backend/app/core/rate_limit.py)<br>[backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) | [test_auth.py](file:///d:/RV_Gym_Project/backend/tests/test_auth.py#L131)<br>[test_attendance.py](file:///d:/RV_Gym_Project/backend/tests/test_attendance.py) | In-memory limiter uses process-local `threading.Lock` and `defaultdict(deque)`. Does not coordinate across multiple Uvicorn workers or multiple container replicas. Single-worker mode enforced in staging as temporary workaround. |
| **Persistent Media Storage** | **PARTIALLY VERIFIED** | [backend/app/api/v1/endpoints/announcements.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/announcements.py)<br>[backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py)<br>[Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging) | [test_phase5_security_and_e2e.py](file:///d:/RV_Gym_Project/backend/tests/test_phase5_security_and_e2e.py) | Upload validation enforces 5MB limit, MIME verification, and UUID filenames. Path mismatch exists between `Dockerfile.staging` (`/app/backend/app/uploads`) and `config.py` (`/app/backend/uploads`). No named volume mount configured in compose. Cloud storage adapter not implemented. |
| **Database Backup & Restore** | **PARTIALLY VERIFIED** | [DEPLOYMENT.md](file:///d:/RV_Gym_Project/DEPLOYMENT.md)<br>[backups/rvfitness_smoke_backup.sql](file:///d:/RV_Gym_Project/backups/rvfitness_smoke_backup.sql) | Manual test during Phase 10 | Procedures exist only as documentation in runbook. No automated backup script, checksumming, or automated restore verification test exists in the repository. |
| **Secrets & Key Rotation** | **PARTIALLY VERIFIED** | [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py#L173-L215) | [test_production_readiness_phase9.py](file:///d:/RV_Gym_Project/backend/tests/test_production_readiness_phase9.py) | Preflight startup invariants enforce >= 32 chars, entropy validation, placeholder rejection, and independent `QR_SIGNING_KEY`. No key rotation mechanism (no secondary keys, no key IDs, no token verification grace period) exists. |
| **Reverse Proxy & Security Headers** | **VERIFIED** | [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py#L76-L95)<br>[backend/app/core/auth.py](file:///d:/RV_Gym_Project/backend/app/core/auth.py#L22-L40) | [test_production_readiness_phase9.py](file:///d:/RV_Gym_Project/backend/tests/test_production_readiness_phase9.py) | Defensive headers enforced (`nosniff`, `DENY` framing, CSP, HSTS in staging/prod). `get_client_ip()` validates peer IP against `settings.TRUSTED_PROXIES` before parsing `X-Forwarded-For`. |
| **Database Migrations & Rollback** | **VERIFIED** | [backend/alembic/versions](file:///d:/RV_Gym_Project/backend/alembic/versions)<br>[backend/tests/test_migrations.py](file:///d:/RV_Gym_Project/backend/tests/test_migrations.py) | [test_migrations.py](file:///d:/RV_Gym_Project/backend/tests/test_migrations.py) | 7 sequential Alembic migrations with single head `007_workout_plans_and_progress`. Full upgrade to head and downgrade to base verified by automated tests. Historical data upgrade and downgrade verified. |
| **Logging, Health Probes & Errors** | **PARTIALLY VERIFIED** | [backend/app/core/logging.py](file:///d:/RV_Gym_Project/backend/app/core/logging.py)<br>[backend/app/api/v1/endpoints/health.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/health.py)<br>[backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) | [test_production_readiness_phase9.py](file:///d:/RV_Gym_Project/backend/tests/test_production_readiness_phase9.py) | Structured logging with correlation IDs, sensitive data redaction (passwords, tokens, biometric weight/fat). `/health` (DB latency) and `/ready` probes verified. Prometheus `/metrics` and APM instrumentation not implemented. |
| **Auth, Branch Isolation & Privacy** | **VERIFIED** | [backend/app/core/auth.py](file:///d:/RV_Gym_Project/backend/app/core/auth.py#L257)<br>[backend/app/models/user.py](file:///d:/RV_Gym_Project/backend/app/models/user.py) | [test_authorization.py](file:///d:/RV_Gym_Project/backend/tests/test_authorization.py)<br>[test_auth.py](file:///d:/RV_Gym_Project/backend/tests/test_auth.py) | `verify_branch_access()` restricts branch managers and staff strictly to assigned branch; members restricted to home branch; org admins have cross-branch scope. Biometric privacy and log redaction verified. |
| **Finance Ledger & Invoicing** | **PARTIALLY VERIFIED** | [backend/app/models/billing.py](file:///d:/RV_Gym_Project/backend/app/models/billing.py)<br>[backend/app/services/billing_service.py](file:///d:/RV_Gym_Project/backend/app/services/billing_service.py) | [test_phase5_security_and_e2e.py](file:///d:/RV_Gym_Project/backend/tests/test_phase5_security_and_e2e.py) | Immutable payment ledger with reversal rows (`is_reversal=True`). Atomic invoice sequence generator with row locking. Idempotency key deduplication with payload mismatch rejection. ReportLab PDF generation. Online payment gateway integration (Razorpay/Stripe) is NOT IMPLEMENTED. |
| **Freezes, QR Replay & Maintenance** | **PARTIALLY VERIFIED** | [backend/app/services/membership_service.py](file:///d:/RV_Gym_Project/backend/app/services/membership_service.py)<br>[backend/app/services/attendance_service.py](file:///d:/RV_Gym_Project/backend/app/services/attendance_service.py) | [test_attendance_adversarial.py](file:///d:/RV_Gym_Project/backend/tests/test_attendance_adversarial.py) | Membership freezes (1-90 days, overlap rejection, valid_until extension, audit logging). Dynamic HMAC QR token verification with atomic JTI consumption in `consumed_qr_tokens` table. Automated background cleanup job for expired nonces and stale sessions is NOT IMPLEMENTED. |
| **Workout Tracking & Leaderboard** | **VERIFIED** | [backend/app/services/leaderboard_service.py](file:///d:/RV_Gym_Project/backend/app/services/leaderboard_service.py)<br>[backend/app/api/v1/endpoints/workouts.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/workouts.py) | [test_phase5_security_and_e2e.py](file:///d:/RV_Gym_Project/backend/tests/test_phase5_security_and_e2e.py) | Full workout tracking and session logging. Points ledger with daily caps and reversals. Leaderboard excludes members where `is_leaderboard_visible=False`. Privacy aliases generated as `Athlete_<id>`. Fitness progress records private by default. |
| **GST & Indian Legal Compliance** | **NOT IMPLEMENTED** | [backend/app/services/billing_service.py](file:///d:/RV_Gym_Project/backend/app/services/billing_service.py#L458) | None | Tax is hardcoded to `0.00` with static "Tax (GST Exempt / Composite)" label on PDF. No branch GSTIN tracking, no SAC code classification (SAC 999723 for gym services), no CGST (9%) / SGST (9%) / IGST (18%) computation, and no statutory tax invoice compliance. |

---

## 4. Risks Ranked by Severity

### Critical Severity Risks
1. **Unbounded Database Bloat from Uncleaned Nonces and Sessions:**
   - *Impact:* High write velocity on `consumed_qr_tokens` and `user_sessions` will continuously grow tables without a scheduled purging worker. Over months, index scan times and storage costs will degrade check-in latency at physical gym turnstiles.
   - *Remediation:* Implement an automated maintenance routine (`purge_expired_tokens_and_sessions`) executable via cron or lightweight Celery/FastAPI lifespan scheduler.

2. **Upload Path Divergence and Container Ephemerality:**
   - *Impact:* In `Dockerfile.staging`, `mkdir -p /app/backend/app/uploads/announcements` creates a directory differing from `settings.get_uploads_dir()` which resolves to `/app/backend/uploads`. Furthermore, without a named docker volume mount, media uploaded in staging or production will vanish upon container restart or redeployment.
   - *Remediation:* Reconcile upload path resolutions in `config.py` and `Dockerfile.staging`, declare an explicit volume mount in compose, and add image cleanup utilities.

### High Severity Risks
3. **Multi-Worker Rate Limiting Bypass:**
   - *Impact:* Because `SlidingWindowRateLimiter` is in-memory only, scaling Uvicorn to 4 workers allows an adversary to execute up to 4x the rate limit on login and QR check-in endpoints.
   - *Remediation:* Create a pluggable rate limiting backend that utilizes Redis when `REDIS_URL` is configured, while preserving the existing in-memory implementation as a zero-dependency fallback for development and unit testing.

4. **Lack of Automated Backup and Restore Verification:**
   - *Impact:* Relying exclusively on manual documentation in `DEPLOYMENT.md` exposes operations to human error during pre-deployment migrations. If a restore fails due to format or permission issues, recovery time objective (RTO) is compromised.
   - *Remediation:* Provide an automated script (`scripts/backup_database.py` and `scripts/restore_database.py`) with sha256 checksumming and an automated test validating restore into a disposable database.

### Medium Severity Risks
5. **Absence of Indian GST Tax Invoicing:**
   - *Impact:* Hardcoded zero tax on invoice PDFs violates Indian GST compliance for gym and fitness center admissions (SAC 999723). When real payments are eventually introduced, retroactive tax restructuring would require database schema changes and customer re-billing.
   - *Remediation:* Add GSTIN fields to Organization and Branch models, calculate 18% GST (9% CGST + 9% SGST for intra-state, 18% IGST for inter-state), itemize tax lines, and format statutory tax invoices.

6. **React Compiler / Oxlint Warnings in Admin Frontend:**
   - *Impact:* 10 warnings in frontend admin components (`Memberships.jsx`, `AdminDashboard.jsx`, `AdminWorkouts.jsx`, `AdminAnnouncements.jsx`, `StaffAttendanceDesk.jsx`) could cause unnecessary re-renders or stale state under high-frequency updates.
   - *Remediation:* Refactor `useEffect` dependencies and extract async loader functions outside of lifecycle hooks.

---

## 5. Recommended Next Phase and Rationale

### Recommendation: Phase 11: Staging Operational Hardening and Reliability Engineering

**Strategic Rationale:**
The application layer, database schemas, role authorization, and destructive test protections are solid and thoroughly tested. However, deploying to an isolated staging environment requires operational reliability: media must not vanish on container restarts, rate limiting must work predictably, expired security nonces must be pruned automatically, and database backups must be verified with automated tooling before any staging migration is executed.

Attempting to implement online payment gateways (Razorpay/Stripe) or public production deployment prior to resolving container storage persistence, backup automation, and rate limiting would compound risk and violate data-preservation principles.

---

## 6. Explicit Scope and Out-of-Scope Work for Phase 11

### In-Scope Work
1. **Container Media Persistence & Path Alignment:**
   - Align `settings.get_uploads_dir()` in [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py) and [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging) to `/app/backend/uploads`.
   - Configure persistent named Docker volume in staging orchestration for media storage.
   - Add orphan media cleanup utility for abandoned draft announcements.
2. **Pluggable Multi-Worker Rate Limiting:**
   - Refactor [backend/app/core/rate_limit.py](file:///d:/RV_Gym_Project/backend/app/core/rate_limit.py) to use an interface with two interchangeable backends:
     - `InMemoryRateLimiter`: Zero-dependency sliding window for local dev and offline tests.
     - `RedisRateLimiter`: Atomic Lua-scripted sliding window for multi-worker staging and production when `REDIS_URL` is set.
   - Add offline unit tests verifying both backends.
3. **Automated Database Backup, Checksum & Restore Tooling:**
   - Create [scripts/backup_database.py](file:///d:/RV_Gym_Project/scripts/backup_database.py) supporting PostgreSQL and SQLite targets, producing timestamped compressed dumps with SHA-256 checksums.
   - Create [scripts/restore_database.py](file:///d:/RV_Gym_Project/scripts/restore_database.py) with preflight safety checks (rejecting production/staging unless explicitly confirmed) and validation of row counts.
   - Create an automated test in `backend/tests/test_backup_restore.py` verifying full backup and restore cycle against a disposable database.
4. **Scheduled Maintenance & Security Nonce Purging:**
   - Create maintenance service [backend/app/services/maintenance_service.py](file:///d:/RV_Gym_Project/backend/app/services/maintenance_service.py) with functions:
     - `purge_expired_qr_tokens(db)`: Purges rows in `consumed_qr_tokens` where `expires_at < now()`.
     - `purge_expired_sessions(db)`: Purges rows in `user_sessions` where `expires_at < now()`.
   - Expose maintenance CLI tool (`python -m backend.app.cli maintenance purge`) and an authorized admin maintenance endpoint.
   - Add unit tests for maintenance routines.
5. **Indian GST Calculation and Statutory Invoicing Foundation:**
   - Add organization/branch GSTIN and state code support.
   - Implement GST calculator service: 18% GST (CGST 9% + SGST 9% for Maharashtra intra-state, IGST 18% for inter-state) with SAC 999723 code.
   - Update [backend/app/services/billing_service.py](file:///d:/RV_Gym_Project/backend/app/services/billing_service.py) ReportLab PDF invoice generator to output compliant tax invoices showing subtotal, CGST, SGST, total, and GSTIN.
   - Add unit tests covering tax calculations and PDF generation.
6. **Frontend Hook Cleanups:**
   - Resolve the 10 Oxlint warnings in `Memberships.jsx`, `AdminDashboard.jsx`, `AdminWorkouts.jsx`, `AdminAnnouncements.jsx`, and `StaffAttendanceDesk.jsx`.

### Out-of-Scope Work (Deferred to Phase 12+)
- Live payment gateway integration (Razorpay / Stripe) and webhook processing.
- Public cloud infrastructure provisioning (AWS ALB, ECS, RDS).
- Production domain DNS, SSL certificate provisioning, and public launch.
- Biometric hardware turnstile physical SDK integration.

---

## 7. Acceptance Criteria and Test Plan

### Acceptance Criteria
1. **Media Persistence:** Media uploaded via `/api/v1/announcements/upload-image` writes to the designated persistent directory, resolves via `/uploads/announcements/<filename>`, and survives container restarts.
2. **Rate Limiting:** Sliding-window rate limiter functions identically across single-worker (in-memory) and multi-worker (Redis) configurations. 429 Too Many Requests response is returned with proper `Retry-After` headers.
3. **Backup Tooling:** `scripts/backup_database.py` generates an uncorrupted compressed database archive with a verified SHA-256 sidecar file. `scripts/restore_database.py` safely restores the archive to a disposable test database without data loss.
4. **Maintenance Purge:** Calling `purge_expired_qr_tokens` and `purge_expired_sessions` deletes expired rows while preserving all active tokens and sessions.
5. **GST Invoicing:** Invoices computed for membership plans accurately calculate 18% GST with SAC 999723, and generated PDFs show itemized CGST and SGST amounts.
6. **Zero Regression:** All existing 201 backend tests and 19 guard tests continue to pass with 0 failures and 0 warnings.
7. **Frontend Clean:** Oxlint completes with 0 errors and 0 warnings.

### Verification Test Plan
- Unit tests: `test_rate_limit_redis.py`, `test_maintenance.py`, `test_gst_billing.py`.
- Backup verification test: `test_backup_restore.py` verifying automated backup, checksum validation, and restore into a disposable PostgreSQL target.
- Frontend test: `npm run lint` and `npm run build` with zero warnings.

---

## 8. Rollback and Data-Preservation Considerations

1. **Working Tree Safety:** Staged removal of `rvfitness_dev.db` will be preserved; local file on disk (487,424 bytes) will not be modified or deleted.
2. **Container Preservation:** All existing Docker resources (`rvfitness-integration-db`, `rvfitness_staging_smoke`, `rvfitness_smoke_data`, `coverageiq-postgres`) remain completely intact. No volume pruning or container removals will occur.
3. **Alembic Backward Compatibility:** Any schema additions (such as GST configuration fields on branches) must be accompanied by explicit upgrade and downgrade methods tested against SQLite and PostgreSQL.
4. **Fail-Safe Fallbacks:** If Redis is unavailable or unconfigured, the application must automatically fall back to the in-memory rate limiter without throwing unhandled startup errors.

---

## 9. Remaining Blockers to Staging and Public Launch

### Staging Blockers (Resolved in Phase 11)
- [ ] Upload directory path alignment and volume mount in staging container.
- [ ] Multi-worker rate limiter support for staging replicas.
- [ ] Automated pre-deployment backup and restore verification tool.
- [ ] Expired nonce and session maintenance cleanup routines.
- [ ] GST invoice calculation and tax breakdown compliance.

### Public Launch Blockers (Phase 12+)
- [ ] Razorpay / UPI payment gateway integration and webhook verification.
- [ ] Production SSL/TLS certificate deployment and domain binding.
- [ ] Production key rotation runbook and secret manager integration.
- [ ] Prometheus metrics endpoint and monitoring dashboard setup.
