# RVFitness: Phase 11A Persistent Media Storage and Deployment Reliability Report

**Document Version:** 1.0.0  
**Phase:** 11A  
**Status:** PASS  
**Date:** 2026-10-16  
**Auditor:** Automated Architecture and Reliability Reviewer  
**Workspace Root:** `D:\RV_Gym_Project`  
**Active Branch:** `prithviraj-feature` (Commit: `6529abd`)  

---

## 1. Executive Summary

Phase 11A addresses the persistent media storage divergence and deployment reliability risks identified in [docs/PHASE_11_READINESS_AUDIT.md](file:///d:/RV_Gym_Project/docs/PHASE_11_READINESS_AUDIT.md).

Prior to this phase:
- [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging) created `/app/backend/app/uploads/announcements`, introducing an unnecessary nested path divergence.
- [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py) defaulted to `/app/backend/uploads` inside the container source tree.
- No named persistent Docker volume was declared for uploaded media in staging or production specifications, meaning container restarts or recreation would wipe user-uploaded announcement media.
- No staging Docker Compose specification existed to cleanly separate staging resources from disposable integration test fixtures.

All issues have been resolved. The media storage contract is now unified, path traversal protections are enforced in both schemas and route fallbacks, an isolated staging Compose configuration with named persistent volumes has been established, and a comprehensive 15-test verification suite has passed with zero failures.

---

## 2. Files Changed and Implementation Details

1. [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py):
   - Refactored `get_uploads_dir()` to return the canonical container path `/app/uploads` when `ENVIRONMENT in {"staging", "production"}` and `/app` exists.
   - Preserved development/test default `<workspace>/backend/uploads` for zero-friction local workflows.
   - Enhanced `validate_production_security()` to verify that in staging and production, media storage is strictly outside the application source tree (`backend/`), exists or can be created, and is writable via probe verification.

2. [backend/app/schemas/announcement.py](file:///d:/RV_Gym_Project/backend/app/schemas/announcement.py):
   - Added `validate_safe_image_url()` validator across `AnnouncementBase` and `AnnouncementUpdate`.
   - Rejects dangerous URI protocols (`javascript:`, `data:`, `vbscript:`, `file:`).
   - Rejects path traversal sequences (`..`, `\`, `%2e`, null bytes `\0`).
   - Enforces that relative paths must strictly start with `/uploads/`.

3. [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py):
   - Hardened `serve_spa_frontend` SPA fallback route: requests for sensitive file extensions (`.env`, `.py`, `.db`, `.key`, `.ini`, `.conf`) or hidden dotfiles return HTTP 404 rather than serving the frontend `index.html` fallback.

4. [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging):
   - Aligned directory creation to `/app/uploads/announcements` with `0775` permissions.
   - Declared persistent volume mount point: `VOLUME ["/app/uploads"]`.
   - Set explicit environment variable: `ENV UPLOADS_DIR=/app/uploads`.

5. [docker-compose.staging.yml](file:///d:/RV_Gym_Project/docker-compose.staging.yml):
   - Created standalone staging orchestration specification completely isolated from [docker-compose.test.yml](file:///d:/RV_Gym_Project/docker-compose.test.yml).
   - Configured named persistent volume `rvfitness_media_data:/app/uploads` for media storage.
   - Configured dedicated database volume `rvfitness_staging_db_data:/var/lib/postgresql/data`.

6. [backend/.env.example](file:///d:/RV_Gym_Project/backend/.env.example):
   - Documented `UPLOADS_DIR` configuration with development and staging defaults.

7. [DEPLOYMENT.md](file:///d:/RV_Gym_Project/DEPLOYMENT.md):
   - Corrected documentation table row for `UPLOADS_DIR` to cite canonical `/app/uploads` backed by persistent volume `rvfitness_media_data`.

8. [backend/tests/test_media_persistence.py](file:///d:/RV_Gym_Project/backend/tests/test_media_persistence.py):
   - Implemented 15 comprehensive unit and functional tests validating storage resolution, upload/retrieval, lifecycle persistence across simulated container recreation, traversal rejection, RBAC/CSRF boundaries, and staging fail-fast invariants.

---

## 3. Media Storage Contract

### Architecture and Isolation Boundaries
- **Container Path:** `/app/uploads` (dedicated, outside `/app/backend` source and `/app/frontend` build).
- **Subdirectories:** `/app/uploads/announcements` for announcement media assets.
- **Permissions:** Directory initialized with `0775` permissions.
- **Persistent Volume:** Docker named volume `rvfitness_media_data` mapped to `/app/uploads`.
- **Public URL Mapping:** Mounted via FastAPI StaticFiles at `/uploads`, accessible via `/uploads/announcements/<uuid>.<ext>`.
- **Development Default:** `<workspace>/backend/uploads` (retains local `.gitkeep` placeholder).

---

## 4. Security Considerations

1. **Path Traversal Prevention:**
   - Upload filenames are generated exclusively on the server using `uuid.uuid4().hex + ext`. The client-supplied filename is never used on disk.
   - Schema validation in [backend/app/schemas/announcement.py](file:///d:/RV_Gym_Project/backend/app/schemas/announcement.py) rejects any `..`, `\`, `%2e`, or null bytes in image URLs.
   - StaticFiles mount strictly limits file reads to the configured `UPLOADS_DIR`. Attempts to traverse outside return HTTP 404 or 400.
   - SPA fallback route in [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) blocks access to dotfiles and sensitive extensions (`.env`, `.py`, `.db`, `.key`).

2. **Upload Boundary Enforcement:**
   - Role-Based Access Control: Endpoint `/api/announcements/upload-image` requires roles `org_admin`, `admin`, `branch_manager`, or `manager`. Members and unauthenticated callers receive HTTP 401 or 403.
   - CSRF Protection: Valid `rvf_csrf_token` cookie and `X-CSRF-Token` header are mandatory.
   - Content Verification: Inspects first 512 bytes for binary magic signatures matching JPEG (`\xff\xd8\xff`), PNG (`\x89PNG\r\n\x1a\n`), or WebP (`RIFF...WEBP`). Mismatched or non-image types receive HTTP 400.
   - File Size Limit: Content length is strictly capped at 5 MB (`MAX_IMAGE_SIZE_BYTES = 5242880`). Larger payloads receive HTTP 413.

3. **Staging Fail-Fast Security:**
   - In staging and production, `validate_production_security()` verifies that `UPLOADS_DIR` exists, is writable, and is not placed inside the application source tree. In a container environment, missing or ephemeral storage halts application startup immediately.

---

## 5. Verification and Test Results

### A. Media Persistence Suite
- **Command:** `python -m pytest -q .\backend\tests\test_media_persistence.py`
- **Result:** 15 passed in 4.09s.
- **Coverage Summary:**
  1. `test_media_directory_resolution_defaults`: Passed.
  2. `test_media_directory_resolution_explicit_custom`: Passed.
  3. `test_media_directory_resolution_whitespace_stripping`: Passed.
  4. `test_media_persistence_across_app_lifecycle_recreation`: Passed.
  5. `test_path_traversal_rejection_in_schema`: Passed.
  6. `test_path_traversal_rejection_via_static_routes`: Passed.
  7. `test_upload_unauthenticated_rejection`: Passed.
  8. `test_upload_unauthorized_role_rejection`: Passed.
  9. `test_upload_missing_csrf_rejection`: Passed.
  10. `test_upload_disallowed_mime_type_rejection`: Passed.
  11. `test_upload_magic_bytes_mismatch_rejection`: Passed.
  12. `test_upload_oversized_file_rejection`: Passed.
  13. `test_staging_storage_inside_source_tree_rejection`: Passed.
  14. `test_staging_storage_unwritable_rejection`: Passed.
  15. `test_staging_storage_valid_persistent_directory_succeeds`: Passed.

### B. Production Readiness Phase 9 Suite
- **Command:** `python -m pytest -q .\backend\tests\test_production_readiness_phase9.py`
- **Result:** 26 passed in 1.89s.

### C. PostgreSQL Guard Unit Tests
- **Command:** `python -m pytest -q .\backend\tests\test_postgres_guard.py`
- **Result:** 19 passed in 0.06s.

### D. Comprehensive Non-PostgreSQL Backend Test Suite
- **Command:** `python -m pytest -q .\backend\tests --ignore=.\backend\tests\test_postgresql_integration.py`
- **Result:** 215 passed in 250.74s (0:04:10), 0 failures, 0 warnings, 0 errors.

### E. Staging Docker Image Packaging
- **Command:** `docker build -f Dockerfile.staging -t rvfitness:staging .`
- **Result:** Succeeded in 6.0s. Image `rvfitness:staging` verified with:
  - Persistent volume: `{"/app/uploads":{}}`
  - Runtime environment: `UPLOADS_DIR=/app/uploads` and `ENVIRONMENT=staging`
  - Directory permissions: `/app/uploads/announcements` initialized with 0775.

---

## 6. Rollback Steps

If Phase 11A changes need to be rolled back:
1. Revert [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging) line 43 back to `mkdir -p /app/backend/app/uploads/announcements` and remove the `VOLUME` directive.
2. Remove [docker-compose.staging.yml](file:///d:/RV_Gym_Project/docker-compose.staging.yml).
3. Revert [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py) and [backend/app/schemas/announcement.py](file:///d:/RV_Gym_Project/backend/app/schemas/announcement.py).
4. Revert [backend/tests/test_media_persistence.py](file:///d:/RV_Gym_Project/backend/tests/test_media_persistence.py).

---

## 7. Remaining Staging Blockers (Phase 11B+)

1. **Distributed Rate Limiting (Phase 11B):** In-memory sliding window limiter needs a Redis backend adapter for multi-worker container scaling.
2. **Automated Backup & Restore Tooling (Phase 11C):** Need automated backup script with SHA-256 verification and automated restore verification tests.
3. **Scheduled Nonce & Session Maintenance (Phase 11D):** Need automated purging of expired rows in `consumed_qr_tokens` and `user_sessions`.
4. **GST Tax Invoicing Foundation (Phase 11E):** Need 18% GST calculation and statutory tax invoice PDF generation.
