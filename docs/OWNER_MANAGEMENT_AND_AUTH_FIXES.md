# RVFitness: Authentication Bug Remediation and Gym Owner Website Management Implementation

## Executive Summary

This report documents the investigation, root cause diagnosis, architectural remediation, and test verification conducted for the RVFitness platform in the local staging environment (`http://127.0.0.1:18000`).

Two critical authentication defects were resolved without weakening security:
1. Member Registration Validation failure (`Request validation failed`).
2. Authentication and session persistence failure (`Authentication required. Missing session credentials.`) affecting protected views and monthly attendance reports.

In addition, a complete, secure Gym Owner Website Management Panel was designed, implemented, and verified across backend API services, PostgreSQL schemas, and the React frontend interface.

---

## 1. Root Cause Analysis

### Phase 1: Member Registration Validation Failure

#### Reported Symptom
During member registration on the frontend modal, submissions failed with the error message: `Request validation failed`.

#### Root Causes
1. **Password Length Validation Discrepancy**:
   - The backend Pydantic schema `RegisterRequest` in [backend/app/schemas/auth.py](file:///d:/RV_Gym_Project/backend/app/schemas/auth.py) strictly enforces `password: str = Field(..., min_length=8)`.
   - The frontend registration form in [frontend/src/components/AuthModal.jsx](file:///d:/RV_Gym_Project/frontend/src/components/AuthModal.jsx) previously only validated client-side passwords with `password.length < 6`, while displaying a placeholder suggestive of 6 characters. Users submitting 6 or 7 character passwords triggered a 422 Unprocessable Content response from FastAPI.
2. **Generic Validation Error Response Handler**:
   - In [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py), the `RequestValidationError` exception handler collapsed all detailed Pydantic error objects into a single generic top-level string: `"Request validation failed"`.
   - Per-field failure details (`loc`, `msg`) were omitted from the structured response payload, making it impossible for the frontend to highlight which specific input failed.
3. **Frontend API Error Extraction**:
   - In [frontend/src/api.js](file:///d:/RV_Gym_Project/frontend/src/api.js), HTTP 422 errors were caught generically, discarding any structured field mapping and presenting only the string `err.message`.

#### Remediation Applied
- Enhanced `validation_exception_handler` in [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) to extract and return `field_errors: Dict[str, str]`, `message: str`, and sanitized `details: List[str]`.
- Updated [frontend/src/api.js](file:///d:/RV_Gym_Project/frontend/src/api.js) to parse `data.field_errors` and attach them to rejected Error objects (`err.fieldErrors`).
- Updated [frontend/src/components/AuthModal.jsx](file:///d:/RV_Gym_Project/frontend/src/components/AuthModal.jsx) to enforce 8+ character passwords client-side, perform email format validation, and render inline field-level error messages directly beneath affected inputs.
- Preserved strict server-side validation and bcrypt password hashing.

---

### Phase 2: Authentication and Session Persistence Failure

#### Reported Symptom
Users authenticated successfully via the login modal, but subsequent navigation to the Admin Dashboard or Monthly Attendance Reports failed with: `Authentication required. Missing session credentials.` Refreshing the browser also dropped the user session.

#### Root Causes
1. **Cookie Secure Flag Misconfiguration in Local Staging**:
   - In [docker-compose.staging.yml](file:///d:/RV_Gym_Project/docker-compose.staging.yml), the environment variable `COOKIE_SECURE: "true"` was configured.
   - The local staging environment is served over plain HTTP at `http://127.0.0.1:18000`. Modern browsers (Chrome, Edge, Firefox) reject and silently drop `Set-Cookie` headers containing the `Secure` attribute when received over unencrypted HTTP connections. As a result, the `rvf_session` HttpOnly cookie was never saved by the browser.
2. **Missing Scheme Detection in Backend Cookie Handlers**:
   - In [backend/app/core/auth.py](file:///d:/RV_Gym_Project/backend/app/core/auth.py) and [backend/app/api/v1/endpoints/auth.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/auth.py), `set_auth_cookies` and `clear_auth_cookies` only checked the static configuration `settings.COOKIE_SECURE` without inspecting incoming request scheme or client host (such as `127.0.0.1` or `localhost`).
3. **Premature Route Resolution in React Application Shell**:
   - In [frontend/src/App.jsx](file:///d:/RV_Gym_Project/frontend/src/App.jsx), the view state was rendered prior to `fetchCurrentUser()` completing its initial probe.
   - Child components mounted and immediately dispatched authenticated API requests before the session credentials were confirmed.
   - In [frontend/src/components/StaffAttendanceDesk.jsx](file:///d:/RV_Gym_Project/frontend/src/components/StaffAttendanceDesk.jsx), CSV and PDF export links rendered as raw `<a href="..." download>` anchor tags. Browser link navigation does not include custom headers and failed when downloading reports.

#### Remediation Applied
- Configured `COOKIE_SECURE: "false"` for local staging in [docker-compose.staging.yml](file:///d:/RV_Gym_Project/docker-compose.staging.yml) while preserving `COOKIE_SECURE: "true"` in production configuration [docker-compose.production.yml](file:///d:/RV_Gym_Project/docker-compose.production.yml).
- Updated `set_auth_cookies` and `clear_auth_cookies` in [backend/app/core/auth.py](file:///d:/RV_Gym_Project/backend/app/core/auth.py) and [backend/app/api/v1/endpoints/auth.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/auth.py) to dynamically detect plain HTTP requests on loopback addresses and disable the `Secure` flag on local connections.
- Implemented an `authResolved` gating check in [frontend/src/App.jsx](file:///d:/RV_Gym_Project/frontend/src/App.jsx) to ensure authentication state is completely resolved before mounting protected views.
- Implemented `downloadBranchReportExport` in [frontend/src/api.js](file:///d:/RV_Gym_Project/frontend/src/api.js) and [frontend/src/components/StaffAttendanceDesk.jsx](file:///d:/RV_Gym_Project/frontend/src/components/StaffAttendanceDesk.jsx) using authenticated blob requests (`credentials: 'include'`).

---

## 2. Gym Owner Website Management Panel Architecture

### Role and Designation Hierarchy
- **Platform Administrator** (`role = 'org_admin'`, `staff_role = 'Platform Administrator'`): Full administrative control over all organizations, global billing, and system operations.
- **Gym Owner** (`role = 'org_admin'`, `staff_role = 'Gym Owner'`): Complete management authority over website content, equipment photo showcase, coaches, staff assignments, membership plans, and multi-branch operations.
- **Branch Manager** (`role = 'branch_manager'`): Restricted to managing operations, attendance desk, and inquiries for their assigned branch.
- **Trainer / Coach** (`role = 'trainer'`): Restricted to personal coaching assignments and assigned client workout programs.
- **Member** (`role = 'member'`): Restricted to personal attendance, QR code generation, and membership profile.

### Database Models Added
Defined in [backend/app/models/website_content.py](file:///d:/RV_Gym_Project/backend/app/models/website_content.py) and registered in [backend/app/models/__init__.py](file:///d:/RV_Gym_Project/backend/app/models/__init__.py):

1. **`WebsiteContent` (`website_contents`)**:
   - `id`: Primary key string (e.g. `content_homepage_hero`, `content_contact`).
   - `section`: Section identifier (`hero`, `facilities`, `contact`, `hours`, `promotions_banner`).
   - `data`: JSONB column storing dynamic website content.
   - `updated_by`: Foreign key to `users.id`.
   - `updated_at`: Timestamp with timezone.

2. **`EquipmentItem` (`equipment_items`)**:
   - `id`: UUID primary key.
   - `name`: Equipment title.
   - `category`: Functional category (Strength, Cardio, Free Weights, Functional).
   - `spec`: Technical specifications and user load ratings.
   - `brand_model`: Equipment manufacturer and model number.
   - `branch_id`: Foreign key to `branches.id`.
   - `primary_image_url`: Primary display photo URL.
   - `images`: JSON array of all uploaded photo URLs.
   - `is_published`: Boolean visibility toggle for public website.
   - `display_order`: Integer sorting index.

3. **`GalleryItem` (`gallery_items`)**:
   - `id`: UUID primary key.
   - `zone`: Gym facility area (Weight Room, Cardio Theater, Turf Lane).
   - `description`: Narrative description of the training space.
   - `image_url`: Persistent photo asset path.
   - `status`: Facility status tag (`In Active Use`, `Renovated`).
   - `branch_id`: Branch association.
   - `is_published`: Boolean visibility toggle.
   - `display_order`: Integer sorting index.

### Alembic Migration
- Migration file: [backend/alembic/versions/008_gym_owner_website_equipment_gallery.py](file:///d:/RV_Gym_Project/backend/alembic/versions/008_gym_owner_website_equipment_gallery.py)
- Revision ID: `008_owner_web_equip_gallery` (27 characters, adhering to PostgreSQL `alembic_version.version_num` 32-character column limit).
- Down revision: `007_phase11_production_readiness`.
- Successfully applied to staging database container `rvfitness_staging_db`.

---

## 3. Owner Capabilities and New Endpoints

All endpoints are defined in [backend/app/api/v1/endpoints/owner.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/owner.py) under the prefix `/api/v1/owner`:

| Method | Endpoint | Authorization | Description |
|---|---|---|---|
| GET | `/api/v1/owner/overview` | `org_admin`, `admin` | Aggregated gym metrics (equipment, coaches, members, plans, branches). |
| GET | `/api/v1/owner/website-content` | `org_admin`, `admin` | Fetch all configured website content sections. |
| PUT | `/api/v1/owner/website-content/{section}` | `org_admin`, `admin` (CSRF required) | Update website content section (hero, facilities, contact, etc.). |
| GET | `/api/v1/owner/equipment` | `org_admin`, `admin` | Fetch all equipment items with branch filters. |
| POST | `/api/v1/owner/equipment` | `org_admin`, `admin` (CSRF required) | Create new equipment item. |
| PUT | `/api/v1/owner/equipment/{id}` | `org_admin`, `admin` (CSRF required) | Update equipment item details, order, and publishing status. |
| DELETE | `/api/v1/owner/equipment/{id}` | `org_admin`, `admin` (CSRF required) | Delete equipment item and safely purge unreferenced physical image files. |
| POST | `/api/v1/owner/equipment/{id}/upload-photo` | `org_admin`, `admin` (CSRF required) | Upload validated photograph (JPEG, PNG, WebP <= 5MB) for equipment. |
| GET | `/api/v1/owner/gallery` | `org_admin`, `admin` | Fetch all facility gallery items. |
| POST | `/api/v1/owner/gallery` | `org_admin`, `admin` (CSRF required) | Add facility gallery showcase item. |
| PUT | `/api/v1/owner/gallery/{id}` | `org_admin`, `admin` (CSRF required) | Update gallery item details and visibility. |
| DELETE | `/api/v1/owner/gallery/{id}` | `org_admin`, `admin` (CSRF required) | Remove gallery item and purge unreferenced image file. |
| POST | `/api/v1/owner/gallery/upload-photo` | `org_admin`, `admin` (CSRF required) | Upload gallery photo asset with magic-bytes verification. |
| GET | `/api/v1/owner/coaches` | `org_admin`, `admin` | List coach and trainer accounts across branches. |
| POST | `/api/v1/owner/coaches` | `org_admin`, `admin` (CSRF required) | Create new coach/trainer account with bcrypt hashed password. |
| PUT | `/api/v1/owner/coaches/{id}` | `org_admin`, `admin` (CSRF required) | Update coach profile, bio, certifications, and active status. |
| GET | `/api/v1/owner/plans` | `org_admin`, `admin` | List all membership plans and pricing configurations. |
| POST | `/api/v1/owner/plans` | `org_admin`, `admin` (CSRF required) | Create new membership plan with multi-branch pricing tiers. |
| PUT | `/api/v1/owner/plans/{id}` | `org_admin`, `admin` (CSRF required) | Update membership plan parameters. |
| DELETE | `/api/v1/owner/plans/{id}` | `org_admin`, `admin` (CSRF required) | Delete unreferenced plan or safely archive if subscriptions exist. |
| POST | `/api/v1/owner/upload-media` | `org_admin`, `admin` (CSRF required) | General media asset upload to persistent volume. |

### Public Endpoints Updated for Dynamic Content
In [backend/app/api/v1/endpoints/gym_info.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/gym_info.py):
- `GET /api/v1/gym/info`: Reads live database records from `website_contents`, falling back gracefully to static defaults if unconfigured.
- `GET /api/v1/gym/equipment`: Reads published items from `equipment_items`, falling back to catalog defaults if empty.
- `GET /api/v1/gym/gallery`: Reads published showcase items from `gallery_items`, falling back to default facility zones.
- `GET /api/v1/gym/trainers`: Reads active coaches from `users` and `trainer_profiles`.

---

## 4. Frontend Implementation

### Gym Owner Panel Component
Created [frontend/src/components/GymOwnerPanel.jsx](file:///d:/RV_Gym_Project/frontend/src/components/GymOwnerPanel.jsx):
- **Design System**: Fully integrated with RVFitness's metallic gold (`#d4af37`), deep charcoal (`#121214`), dark slate (`#1e1e24`), and crisp white typography.
- **Navigation Tabs**:
  1. **Overview**: Metric summary cards (Equipment, Gallery, Coaches, Active Members, Plans, Branches) and quick actions.
  2. **Website Editor**: Live form to update Homepage Hero, Facility Information, Operating Hours, Contact Details, and Promotional Banners.
  3. **Equipment & Gallery**: Add, edit, publish/unpublish, reorder, and upload multiple photos for gym equipment and facility areas. Includes cover image selection and destructive deletion confirmation dialogs.
  4. **Coaches & Staff**: Roster management, adding new trainers, updating qualifications, biographies, branch assignments, and deactivating accounts.
  5. **Membership Plans**: Creating plans, setting durations, configuring pricing across branches, publishing, and archiving.
  6. **Branches & Facilities**: Multi-branch operational overview for Narsobawadi and Jaysingpur campuses.
  7. **Members & Attendance**: Direct link to the real-time Attendance Desk and monthly attendance analytics.
  8. **Announcements**: Broadcast management for member notices.
  9. **Settings**: Platform security parameters and audit logging status.

### Frontend Integration
- [frontend/src/components/AdminDashboard.jsx](file:///d:/RV_Gym_Project/frontend/src/components/AdminDashboard.jsx): Embedded the Gym Owner Panel as a top-level tab alongside Attendance Desk, Memberships, Member Lookup, and Inquiries.
- [frontend/src/components/Hero.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Hero.jsx): Dynamically fetches and renders the live hero title, subtitle, and CTA.
- [frontend/src/components/Equipment.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Equipment.jsx): Dynamically loads equipment items from `/api/v1/gym/equipment`.
- [frontend/src/components/Gallery.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Gallery.jsx): Dynamically displays facility gallery photos from `/api/v1/gym/gallery`.
- [frontend/src/App.css](file:///d:/RV_Gym_Project/frontend/src/App.css): Comprehensive styles for tabs, form controls, media cards, upload drag-and-drop targets, badges, and modal dialogs.
- Bundle compiled cleanly using `npm run build` with Vite.

---

## 5. Security and Authorization Rules

1. **Backend Role Enforcement**:
   - Every mutation endpoint requires `current_user: User = Depends(require_roles("org_admin", "admin"))`.
   - Normal members (`role = 'member'`) and trainers (`role = 'trainer'`) receive HTTP 403 Forbidden on all owner endpoints.
2. **CSRF Protection**:
   - All state-changing endpoints (`POST`, `PUT`, `DELETE`) require `Depends(require_csrf)`.
   - The double-submit cookie pattern verifies the `rvf_csrf_token` cookie against the `X-CSRF-Token` request header.
3. **Safe File Uploads and Path Traversal Prevention**:
   - File extensions are restricted to `.jpg`, `.png`, `.webp`.
   - Magic bytes verification (`\xff\xd8\xff` for JPEG, `\x89PNG\r\n\x1a\n` for PNG, `RIFF...WEBP` for WebP) inspects file headers to prevent executable code disguising as an image.
   - Filenames are randomized with `uuid.uuid4().hex` to prevent arbitrary filesystem path traversal.
   - Max file size strictly capped at 5 MB.
   - Files are stored in the persistent Docker volume `/app/uploads` (`rvfitness_media_data`).
4. **Physical Media File Cleanup**:
   - When an equipment photo or gallery photo is deleted, the backend checks whether the image path is referenced by any other record before purging the physical file from disk.
5. **Financial and Subscription Integrity**:
   - When deleting a membership plan, the backend queries `enrollments` and `invoices`. If historical records reference the plan, deletion is prevented with HTTP 409 Conflict, requiring the owner to archive the plan instead.
6. **Self-Promotion Prevention**:
   - Coaches cannot promote themselves or create administrator accounts.

---

## 6. Test Commands and Verification Results

### Backend Test Suite
Executed within the workspace using pytest against isolated test database sessions:

```powershell
python -m pytest backend/tests/test_owner_management_and_auth_fixes.py -v
```

**Results (15 of 15 passed in 16.06s)**:
- `test_registration_short_password_validation`: PASSED
- `test_registration_invalid_email_validation`: PASSED
- `test_registration_terms_not_accepted`: PASSED
- `test_registration_successful_and_duplicate`: PASSED
- `test_login_session_cookie_and_csrf_persistence`: PASSED
- `test_attendance_reports_with_authenticated_session`: PASSED
- `test_unauthenticated_request_rejected`: PASSED
- `test_revoked_session_rejected`: PASSED
- `test_logout_invalidates_session`: PASSED
- `test_owner_website_content_management`: PASSED
- `test_owner_equipment_management`: PASSED
- `test_owner_coaches_management`: PASSED
- `test_owner_plan_management_and_dependency_guard`: PASSED
- `test_member_and_trainer_forbidden_from_owner_endpoints`: PASSED
- `test_csrf_protection_on_owner_mutations`: PASSED

### Regression Verification Suite
```powershell
python -m pytest backend/tests/test_auth.py backend/tests/test_endpoints.py backend/tests/test_attendance.py -v
```
**Results**: 14 of 14 passed in 7.98s.

```powershell
python -m pytest backend/tests/test_billing.py backend/tests/test_branch_isolation.py -v
```
**Results**: 7 of 7 passed in 3.32s.

```powershell
python -m pytest backend/tests/test_media_persistence.py -v
```
**Results**: 15 of 15 passed in 3.11s.

```powershell
python -m pytest backend/tests/test_migrations.py backend/tests/test_migration_safety_target.py -v
```
**Results**: 16 of 16 passed in 3.18s.

### Live Staging End-to-End Verification
Executed against the running staging container cluster at `http://127.0.0.1:18000`:
- Step 1: CSRF token retrieved successfully.
- Step 2: Member registration validation: short password (<8 chars) rejected with 422 and structured `field_errors`; unaccepted terms rejected with 400.
- Step 3: Gym Owner login (`owner@rvfitness.in`) authenticated; `rvf_session` cookie issued and persisted.
- Step 4: Session persistence verified via `/api/v1/auth/me`.
- Step 5: Monthly Attendance Reports loaded with full daily breakdown and operator metrics.
- Step 6: Gym Owner Overview metrics retrieved.
- Step 7: Equipment item created via owner API and immediately verified on public `/api/v1/gym/equipment`.
- Step 8: Website hero section updated via owner API and immediately verified on public `/api/v1/gym/info`.
- Step 9: Logout cleared cookies and invalidated server-side session.

---

## 7. Files Changed Summary

| File | Change Description |
|---|---|
| [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) | Added field-level error dictionary to `validation_exception_handler`. Mounted API router at `/api/v1` alias. |
| [backend/app/core/auth.py](file:///d:/RV_Gym_Project/backend/app/core/auth.py) | Added HTTP scheme detection to disable `Secure` cookie flag on local staging loopback connections. |
| [backend/app/api/v1/endpoints/auth.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/auth.py) | Added scheme-aware cookie settings and fixed registration validation error details. |
| [backend/app/models/website_content.py](file:///d:/RV_Gym_Project/backend/app/models/website_content.py) | Added `WebsiteContent`, `EquipmentItem`, and `GalleryItem` database models. |
| [backend/app/models/__init__.py](file:///d:/RV_Gym_Project/backend/app/models/__init__.py) | Exported new website content and equipment models for Alembic discovery. |
| [backend/alembic/versions/008_gym_owner_website_equipment_gallery.py](file:///d:/RV_Gym_Project/backend/alembic/versions/008_gym_owner_website_equipment_gallery.py) | Alembic migration creating tables and foreign key constraints. |
| [backend/app/schemas/owner.py](file:///d:/RV_Gym_Project/backend/app/schemas/owner.py) | Created Pydantic schemas for equipment, gallery, coaches, plans, and website content. |
| [backend/app/api/v1/endpoints/owner.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/owner.py) | Implemented full Gym Owner Management API router with 20 endpoints. |
| [backend/app/api/v1/endpoints/gym_info.py](file:///d:/RV_Gym_Project/backend/app/api/v1/endpoints/gym_info.py) | Updated public `/info`, `/equipment`, `/gallery`, and `/trainers` endpoints to serve live data. |
| [backend/app/api/v1/api.py](file:///d:/RV_Gym_Project/backend/app/api/v1/api.py) | Registered owner router in API router. |
| [docker-compose.staging.yml](file:///d:/RV_Gym_Project/docker-compose.staging.yml) | Set `COOKIE_SECURE: "false"` for local staging plain HTTP compatibility. |
| [frontend/src/api.js](file:///d:/RV_Gym_Project/frontend/src/api.js) | Enhanced error parsing for field errors; added owner API client functions and authenticated export download. |
| [frontend/src/App.jsx](file:///d:/RV_Gym_Project/frontend/src/App.jsx) | Added `authResolved` gate; subscribed to auth expiration events; resolved undefined prop references. |
| [frontend/src/components/AuthModal.jsx](file:///d:/RV_Gym_Project/frontend/src/components/AuthModal.jsx) | Aligned client password validation to 8+ characters; added inline field error rendering. |
| [frontend/src/components/GymOwnerPanel.jsx](file:///d:/RV_Gym_Project/frontend/src/components/GymOwnerPanel.jsx) | Created comprehensive Gym Owner Website and Operational Management UI. |
| [frontend/src/components/AdminDashboard.jsx](file:///d:/RV_Gym_Project/frontend/src/components/AdminDashboard.jsx) | Integrated Gym Owner Panel into administrative tabs. |
| [frontend/src/components/Hero.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Hero.jsx) | Connected to live website content API. |
| [frontend/src/components/Equipment.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Equipment.jsx) | Connected to live equipment inventory API. |
| [frontend/src/components/Gallery.jsx](file:///d:/RV_Gym_Project/frontend/src/components/Gallery.jsx) | Connected to live facility gallery API. |
| [frontend/src/components/StaffAttendanceDesk.jsx](file:///d:/RV_Gym_Project/frontend/src/components/StaffAttendanceDesk.jsx) | Converted raw export links to authenticated blob downloads. |
| [frontend/src/App.css](file:///d:/RV_Gym_Project/frontend/src/App.css) | Complete CSS styles for owner management panel, modals, and field validation errors. |
| [backend/tests/test_owner_management_and_auth_fixes.py](file:///d:/RV_Gym_Project/backend/tests/test_owner_management_and_auth_fixes.py) | 15 comprehensive automated tests for auth fixes and owner management. |

---

## 8. Manual Verification Steps for Gym Owner

To verify the Gym Owner capabilities manually in a web browser:

1. Open `http://127.0.0.1:18000` in Google Chrome or Microsoft Edge.
2. Click **Member Login / Staff Portal** in the navigation header.
3. Sign in with the Gym Owner credentials:
   - **Email**: `owner@rvfitness.in`
   - **Password**: `StagingOwnerPass123!`
4. Verify that the user profile badge shows `Gym Owner (Rohit V.)` with role `org_admin`.
5. Click **Admin Dashboard** in the navigation bar.
6. Select the **Gym Owner Panel** tab:
   - **Website Editor**: Edit the Homepage Hero headline to `RVFITNESS ELITE ATHLETICS` and save. Refresh the homepage and verify the new title appears immediately without rebuilding the code.
   - **Equipment & Gallery**: Click **Add Equipment**, provide name `Arsenal Strength Incline Lever Row`, category `Strength`, upload a photo, and click Save. Verify the equipment appears in the public Equipment section.
   - **Coaches & Staff**: Add a new coach, set specialization to `Powerlifting & Hypertrophy`, and assign to `Narsobawadi Main Campus`.
   - **Membership Plans**: Create or edit a plan, toggle publishing status, and verify public plans reflect the change.
   - **Attendance Reports**: Navigate to Monthly Attendance Reports for Narsobawadi branch, change month/year, recalculate, and click **Export CSV** to verify the authenticated file download works.
7. Click **Sign Out** and verify the session terminates cleanly, redirecting to the unauthenticated view.
