# RVFitness Production Deployment Runbook and Architecture Guide

This guide specifies the operational, infrastructure, security, and lifecycle requirements for deploying the RVFitness Enterprise Gym Management Platform to staging and production environments.

---

## 1. System Architecture Overview

The RVFitness platform is structured as a modular monolith:

1. **Frontend**: Single-Page Application (SPA) built with React 19, TypeScript, and Vite. Statically built and served via CDN / reverse proxy (Nginx, Cloudflare Pages, AWS CloudFront + S3, or Vercel).
2. **Backend**: Asynchronous ASGI application powered by FastAPI, Python 3.11+, and Uvicorn workers. Manages business logic, authentication, RBAC, billing, QR entry validation, attendance reporting, announcements, and workout plans.
3. **Database**: PostgreSQL 16 relational database with SQLAlchemy 2.0 ORM and Alembic migrations. Handles ACID transactions, row-level concurrency locking (`with_for_update`), and PostgreSQL advisory locks for distributed task deduplication.
4. **Media Storage**: Local container volume or cloud object storage (AWS S3 / Google Cloud Storage) for uploaded announcement media.
5. **Reverse Proxy & Ingress**: Nginx, Traefik, or AWS Application Load Balancer (ALB) providing TLS 1.3 termination, rate limiting, and trusted header forwarding.

```
[ User Browser / Device ]
           |
       (HTTPS / 443)
           v
[ Ingress / Reverse Proxy (Nginx / ALB) ]
     |                             |
     v                             v
[ Static Frontend Assets ]    [ FastAPI Backend Cluster ]
(HTML, JS, CSS, Media)        (Uvicorn Workers / Port 8000)
                                   |
                             (TCP / 5432 - TLS)
                                   v
                      [ PostgreSQL 16 Database ]
```

---

## 2. Infrastructure Prerequisites

### 2.1 Backend Compute Requirements
- **Runtime**: Linux (Ubuntu 22.04 LTS, Debian 12, or Alpine Linux container).
- **Python**: Version 3.11 or higher.
- **Process Manager**: Systemd or Docker / Kubernetes with auto-restart policies.
- **Hardware Sizing (Baseline)**:
  - Minimum: 2 vCPU, 4 GB RAM (supports 500 active concurrent users).
  - Recommended Production: 4 vCPU, 8 GB RAM per app container (2 to 4 Uvicorn workers per container).

### 2.2 PostgreSQL Database Provisioning
- **Engine**: PostgreSQL 16.x.
- **Connection Security**: Enforce SSL/TLS (`sslmode=require`).
- **Network Isolation**: Deploy PostgreSQL inside a private Virtual Private Cloud (VPC) subnet. Deny public internet access. Only backend compute instances inside authorized security groups may open TCP port 5432.
- **Storage**: Automated daily snapshots with 30-day point-in-time recovery (PITR) retention.

### 2.3 Least-Privilege Database Accounts
The application runtime must **never** connect as a PostgreSQL superuser (`postgres`) or database owner. Create two distinct roles:

1. **`rvf_migrator`** (Used exclusively during release deployment by Alembic):
   - Ownership of schemas and tables to apply DDL migrations.
2. **`rvf_app`** (Used by the active FastAPI application workers):
   - Restricted to DML operations: `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables; `USAGE`, `SELECT`, `UPDATE` on sequences.
   - Denied `CREATE`, `DROP`, `ALTER`, and schema truncation permissions.

#### SQL Setup Script for Least Privilege:
```sql
-- 1. Create migration and runtime roles
CREATE ROLE rvf_migrator WITH LOGIN PASSWORD 'USE_STRONG_MIGRATOR_SECRET_HERE';
CREATE ROLE rvf_app WITH LOGIN PASSWORD 'USE_STRONG_RUNTIME_SECRET_HERE';

-- 2. Grant schema ownership to migrator
GRANT ALL PRIVILEGES ON DATABASE rvfitness TO rvf_migrator;
GRANT ALL ON SCHEMA public TO rvf_migrator;

-- 3. Grant runtime DML permissions to app role
GRANT CONNECT ON DATABASE rvfitness TO rvf_app;
GRANT USAGE ON SCHEMA public TO rvf_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rvf_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO rvf_app;

-- 4. Default future privileges for new tables created by Alembic
ALTER DEFAULT PRIVILEGES FOR ROLE rvf_migrator IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rvf_app;

ALTER DEFAULT PRIVILEGES FOR ROLE rvf_migrator IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO rvf_app;
```

---

## 3. Production Configuration (`.env`)

The backend requires the following environment variables. The application executes a strict fail-fast validation at startup and will terminate immediately if production security invariants are violated.

| Variable | Type | Required | Description | Example / Notes |
| :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | string | Yes | Operational tier (`production` / `staging`). | `production` |
| `DATABASE_URL` | string | Yes | PostgreSQL connection string with TLS. SQLite is forbidden. | `postgresql+psycopg2://rvf_app:SECRET@db.internal:5432/rvfitness?sslmode=require` |
| `SECRET_KEY` | string | Yes | Cryptographic secret for sessions and signatures (min 32 chars). | 64-character hex string generated via `secrets.token_hex(32)`. |
| `QR_SIGNING_KEY` | string | No | Dedicated key for attendance QR codes (defaults to `SECRET_KEY`). | Independent 64-character hex key for key rotation. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| int | Yes | Session validity period in minutes. | `1440` (24 hours) |
| `CORS_ORIGINS` | JSON array | Yes | Allowed browser origins. Wildcards (`*`) are rejected. | `["https://app.rvfitness.in","https://admin.rvfitness.in"]` |
| `FORWARDED_ALLOW_IPS` | string | Yes | Comma-separated list of trusted upstream proxy IPs. | `127.0.0.1,10.0.0.1` |
| `TRUSTED_PROXIES` | JSON array | Yes | Trusted reverse-proxy addresses for client IP derivation. | `["127.0.0.1","10.0.0.1"]` |
| `COOKIE_SECURE` | bool | Yes | Enforces HTTPS-only cookies (auto-enabled in production). | `true` |
| `COOKIE_SAMESITE` | string | Yes | SameSite cookie attribute. | `lax` |
| `SESSION_COOKIE_NAME` | string | Yes | Session cookie name. | `rvf_session` |
| `CSRF_COOKIE_NAME` | string | Yes | CSRF token cookie name. Must be exactly `rvf_csrf_token`. | `rvf_csrf_token` |
| `UPLOADS_DIR` | string | No | Directory for persistent uploads storage (defaults to `/app/backend/app/uploads`). | `/var/www/rvfitness/uploads` |
| `EXPECTED_STAGING_DB_NAME` | string | No | Staging database name expected by pre-migration safety tool. | `rvfitness_staging` |
| `EXPECTED_STAGING_USER` | string | No | Staging database user expected by pre-migration safety tool. | `rvf_migrator` |
| `APPROVED_STAGING_HOSTS` | string | No | Comma-separated list of approved staging database hostnames or IPs. | `staging-db.internal,10.0.1.5` |
| `DB_POOL_SIZE` | int | Yes | Baseline SQLAlchemy connection pool size. | `15` |
| `DB_MAX_OVERFLOW` | int | Yes | Connection pool overflow capacity. | `25` |
| `DB_POOL_TIMEOUT` | int | Yes | Connection pool timeout in seconds. | `30` |
| `DB_POOL_RECYCLE` | int | Yes | Connection pool recycle interval in seconds. | `1800` |
| `LOG_LEVEL` | string | Yes | Diagnostic log verbosity (`INFO` / `WARNING` / `ERROR`). | `INFO` |

### 3.1 Frontend and Backend CSRF Synchronization
The frontend API client ([frontend/src/services/api.ts](file:///d:/RV_Gym_Project/frontend/src/services/api.ts)) and cookie helper ([frontend/src/utils/cookies.ts](file:///d:/RV_Gym_Project/frontend/src/utils/cookies.ts)) read the CSRF token from the `rvf_csrf_token` cookie and submit it via the `X-CSRF-Token` request header on state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`).
To prevent silent divergence where the frontend and backend look for different cookie names, [backend/app/core/config.py](file:///d:/RV_Gym_Project/backend/app/core/config.py) validates in `validate_production_security()` that `settings.CSRF_COOKIE_NAME == "rvf_csrf_token"`. Startup fails closed if the cookie name is altered or mismatched.

---

## 4. Ingress, TLS, and Reverse Proxy Configuration

Nginx or AWS ALB must terminate TLS 1.3, serve static frontend bundles, and proxy `/api/*` and root probes `/health`, `/ready` to Uvicorn.

### Nginx Production Configuration Snippet:
```nginx
# Upstream Uvicorn backend cluster
upstream rvfitness_backend {
    server 127.0.0.1:8000 max_fails=3 fail_timeout=10s;
    keepalive 32;
}

server {
    listen 80;
    server_name app.rvfitness.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name app.rvfitness.in;

    ssl_certificate /etc/letsencrypt/live/app.rvfitness.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.rvfitness.in/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Root frontend static files
    root /var/www/rvfitness/frontend/dist;
    index index.html;

    # Serve static assets with caching
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA routing fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Health and Readiness Probes for Orchestrators
    location ~ ^/(health|ready)$ {
        proxy_pass http://rvfitness_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API Endpoints & Dynamic Requests
    location /api/ {
        proxy_pass http://rvfitness_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }

    # User uploads directory (serve static files without script execution)
    location /uploads/ {
        alias /var/www/rvfitness/uploads/;
        add_header X-Content-Type-Options nosniff always;
        add_header Content-Security-Policy "default-src 'none'; img-src 'self'" always;
        expires 30d;
    }
}
```

---

## 4.1 Staging Packaging and Container Execution

A dedicated reproducible multi-stage Dockerfile ([Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging)) packages the full application for isolated staging deployment:
- **Build Stage (`node:20-alpine`)**: Installs frontend dependencies via `npm ci` and compiles static assets via `npm run build` into `/build/dist`.
- **Runtime Stage (`python:3.11-slim`)**: Installs minimal system libraries (`curl`, `libpq5`), installs backend dependencies from [backend/requirements.txt](file:///d:/RV_Gym_Project/backend/requirements.txt), copies backend source code, embeds compiled frontend assets into `/app/frontend/dist`, sets `PYTHONPATH=/app` and `ENVIRONMENT=staging`, and configures single-worker Uvicorn.
- **Frontend SPA Serving**: [backend/app/main.py](file:///d:/RV_Gym_Project/backend/app/main.py) automatically mounts static assets at `/assets` and provides an SPA HTML fallback route for `/{full_path:path}` while protecting `/api/*`, `/uploads/*`, `/health`, and `/ready` from SPA interception. No development servers (e.g. Vite dev server) are run in staging or exposed publicly.

### Building the Staging Container Image
```bash
docker build -f Dockerfile.staging -t rvfitness:staging .
```

### Running the Staging Container
```bash
docker run -d \
  --name rvfitness_staging \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /var/www/rvfitness/uploads:/app/backend/app/uploads \
  --env-file .env.staging \
  rvfitness:staging
```

### Worker Process Mode and Rate Limiting
- **Single-Worker Enforcement**: Staging MUST run in single-worker mode (`--workers 1` as configured in [Dockerfile.staging](file:///d:/RV_Gym_Project/Dockerfile.staging)).
- **Rationale**: The sliding window rate limiter ([backend/app/core/rate_limit.py](file:///d:/RV_Gym_Project/backend/app/core/rate_limit.py)) is currently process-local and in-memory. If multiple worker processes are launched, rate limiting counters are partitioned across workers, allowing clients to exceed configured thresholds.
- **Production Path**: Multi-worker and horizontally autoscaled deployments require a shared rate limiter (e.g., Redis-backed token bucket) or upstream edge enforcement (e.g., Cloudflare Rate Limiting or AWS WAF).

### Media Storage Persistence
- **Persistent Volume Requirement**: The application container must mount a persistent host volume or network volume to `/app/backend/app/uploads`. Announcement images uploaded via `POST /api/announcements/upload-image` are written to `/app/backend/app/uploads/announcements/` and served statically via `/uploads/announcements/*`.
- **Single-Instance Restriction**: Local volume mounts only support single-container deployments. Horizontally scaled or multi-instance deployments require centralized object storage (e.g., AWS S3, Google Cloud Storage, or MinIO) with signed URLs. Do not claim multi-instance support without implementing shared object storage.

---

## 5. Deployment Procedures and Release Order

To prevent schema mismatch and downtime, releases must follow this strict sequence:

### Step 1: Pre-Deployment Build and Test Validation
```bash
# 1. Run full backend test suite on CI runner
python -m pytest backend/tests -v

# 2. Verify frontend lint and build
cd frontend
npm run lint
npm run build
cd ..
```

### Step 2: Database Backup
Always trigger a pre-deployment PostgreSQL snapshot or logical backup before applying migrations:
```bash
pg_dump -U rvf_migrator -h <db_host> -d rvfitness -F c -f "/backup/pre_deploy_$(date +%Y%m%d_%H%M%S).dump"
```

#### Step 3: Pre-Migration Target Verification and Database Migrations
Before executing Alembic migrations, run the committed pre-migration verification tool to guard against accidental execution on incorrect databases, unauthorized user roles, or unapproved network targets:

```bash
# Configure staging target and credentials in the deployment shell:
export ENVIRONMENT="staging"
export DATABASE_URL="postgresql+psycopg2://rvf_migrator:SECRET@staging-db.internal:5432/rvfitness_staging?sslmode=require"
export EXPECTED_STAGING_DB_NAME="rvfitness_staging"
export EXPECTED_STAGING_USER="rvf_migrator"
export APPROVED_STAGING_HOSTS="staging-db.internal,10.0.1.5"

# 1. Execute pre-migration safety verification tool
python scripts/verify_staging_migration_target.py

# Expected success output:
# [TARGET VERIFIED] Target database verified successfully:
#   Host: staging-db.internal:5432
#   Database: rvfitness_staging
#   User: rvf_migrator
#   Environment: staging
# Safe to proceed with: python -m alembic upgrade head

# 2. Execute Alembic migrations using the exact same environment and connection:
python -m alembic upgrade head
```

The verification tool enforces strict fail-closed criteria:
- Fails closed if `ENVIRONMENT` is not exactly `staging`.
- Fails closed if database dialect is SQLite (`sqlite://`).
- Fails closed if URL configuration is ambiguous (e.g., conflicting `POSTGRESQL_TEST_URL` and `DATABASE_URL`).
- Fails closed if the target hostname is not in `APPROVED_STAGING_HOSTS`.
- Fails closed if the database name does not match `EXPECTED_STAGING_DB_NAME`.
- Fails closed if live PostgreSQL query `SELECT current_database()` does not match `EXPECTED_STAGING_DB_NAME`.
- Fails closed if live PostgreSQL query `SELECT current_user` does not match `EXPECTED_STAGING_USER`.

### Step 4: Deploy Backend Code and Restart Workers
Launch or restart backend application instances with rolling updates:
```bash
# Direct execution from workspace root:
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Or with Systemd:
sudo systemctl restart rvfitness-backend.service

# Or with Docker Compose:
docker compose up -d --no-deps --build backend
```

### Step 5: Verify Backend Health and Readiness
```bash
curl -f -s https://app.rvfitness.in/health | jq .
curl -f -s https://app.rvfitness.in/ready | jq .
```
Both endpoints must return HTTP 200 with `"status": "healthy"` and `"status": "ready"`.

### Step 6: Deploy Frontend Static Build
Deploy the `frontend/dist` directory to the static hosting target or web server document root:
```bash
rsync -avz --delete frontend/dist/ /var/www/rvfitness/frontend/dist/
```

---

## 6. Rollback Procedures
If an unrecoverable failure occurs post-deployment:

### 6.1 Frontend Rollback
Revert the static asset directory to the previous build artifact:
```bash
rsync -avz --delete /var/www/rvfitness/frontend/dist_previous/ /var/www/rvfitness/frontend/dist/
```

### 6.2 Backend Rollback
Revert backend application code to the prior Git commit or previous Docker image tag and restart Uvicorn workers.

### 6.3 Database Migration Downgrade (If Supported)
If the database migration needs to be rolled back and does not contain irreversible data destruction:
```bash
export DATABASE_URL="postgresql+psycopg2://rvf_migrator:SECRET@db.internal:5432/rvfitness?sslmode=require"

# Step back 1 revision from workspace root:
python -m alembic downgrade -1

# Or explicitly:
python -m alembic -c backend/alembic.ini downgrade -1
```

### 6.4 Full Database Restoration from Pre-Deployment Dump
If data corruption occurred:
```bash
# 1. Terminate active backend workers to release connections
sudo systemctl stop rvfitness-backend

# 2. Restore database from pre-deployment snapshot
pg_restore -U rvf_migrator -h <db_host> -d rvfitness --clean --if-exists /backup/pre_deploy_<timestamp>.dump

# 3. Restart backend workers
sudo systemctl start rvfitness-backend
```

---

## 7. Scheduled Background Maintenance

The platform utilizes scheduled maintenance tasks that must be configured via host cron or Kubernetes CronJobs.

### 7.1 Expired QR Nonce Pruning (Every 10 minutes)
The CLI tool [backend/app/cli/prune_nonces.py](file:///d:/RV_Gym_Project/backend/app/cli/prune_nonces.py) acquires PostgreSQL advisory lock `84729103` to prevent multi-worker concurrency contention:
```bash
# Add to crontab:
*/10 * * * * cd /var/www/rvfitness && /var/www/rvfitness/venv/bin/python -m backend.app.cli.prune_nonces >> /var/log/rvfitness_cron.log 2>&1
```

---

## 8. Pre-Deployment and Smoke-Test Checklists

### Pre-Deployment Checklist
- [ ] Database snapshot / backup successfully created and verified.
- [ ] Alembic migration history verified through revision 007 (`python -m alembic history`).
- [ ] Production / staging environment variables populated in `.env` (no default passwords or sample keys).
- [ ] `SECRET_KEY` is a 64-character high-entropy hex string.
- [ ] `DATABASE_URL` targets PostgreSQL with `sslmode=require`.
- [ ] `CORS_ORIGINS` contains only verified domain names (no wildcards).
- [ ] Ingress reverse proxy forwards `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Request-ID`.
- [ ] All 165+ backend tests pass in clean test environment.
- [ ] Frontend build succeeds with zero errors.

### Post-Deployment Smoke-Test Checklist
- [ ] `/health` returns HTTP 200 with active database connectivity and low query latency (< 50ms).
- [ ] `/ready` returns HTTP 200 with `"status": "ready"`.
- [ ] Admin login succeeds; `rvf_session` cookie is received with `HttpOnly`, `Secure`, and `SameSite=Lax`.
- [ ] CSRF protection validates state-changing requests (`POST /api/workouts/plans` requires `x-csrf-token`).
- [ ] Member registration and login rate limiting is operational (5 requests / minute).
- [ ] Member QR code generation generates valid 120-second token.
- [ ] Staff Attendance Desk validates QR scan and rejects replay attempts.
- [ ] Billing invoice PDF downloads properly via `GET /api/billing/invoices/{id}/pdf`.
- [ ] Workout plan creation, member assignment, and session completion award points idempotently.
- [ ] Private fitness records remain concealed from public leaderboard responses.

---

## 9. Architectural Considerations and Staging Blockers

### 9.1 In-Memory Rate Limiting
- **Current State**: Sliding window rate limits are tracked in worker memory ([backend/app/core/rate_limit.py](file:///d:/RV_Gym_Project/backend/app/core/rate_limit.py)).
- **Implication**: When running multiple Uvicorn worker processes or horizontally scaled container instances, rate-limit buckets are partitioned per process rather than globally aggregated.
- **Remediation for Scale**:
  - For single-node staging: Ensure ingress reverse proxy (Nginx) uses `ip_hash` sticky routing if multiple backend processes are targeted.
  - For distributed production: Deploy a Redis-backed token bucket or delegate edge rate limiting to Cloudflare / AWS WAF.

### 9.2 Announcement Media Storage
- **Current State**: Uploaded announcement banner images are written to the local filesystem at `backend/app/uploads/announcements/`.
- **Implication**: If containers are ephemeral or destroyed during rolling updates, uploaded media files will be lost unless backed by persistent storage.
- **Remediation for Staging**:
  - Bind mount a persistent volume (e.g., host volume `/var/www/rvfitness/uploads` or Kubernetes PVC) to `/app/backend/app/uploads`.
  - For production: Implement an S3-compatible object store client (AWS S3, MinIO, or Google Cloud Storage) with signed URL delivery.

### 9.3 Indian GST & Tax Compliance Review
- **Current State**: The billing service computes basic line items and composite subtotals ([backend/app/services/billing_service.py](file:///d:/RV_Gym_Project/backend/app/services/billing_service.py)).
- **Implication**: Legal enterprise operations in India require GST compliance (HSN/SAC 999723 for fitness services, state-specific CGST/SGST vs IGST determination based on customer and gym branch place of supply, and formal tax invoice serial numbering).
- **Remediation**: Obtain formal accounting and legal review of invoice generation formats before enabling commercial payment gateway processing in production. Staging must use dummy transaction records only.

### 9.4 Payment Gateway and Staging Safeguards
- **Real Payment Gateway Status**: Real payment gateway activation is strictly disabled in staging.
- **Draft Invoices**: All staging billing records and invoices are strictly marked as test drafts and must never be used for actual tax or fiscal accounting.
- **Pre-Migration Safety**: Direct database migrations against live databases without executing `python scripts/verify_staging_migration_target.py` are strictly prohibited.
