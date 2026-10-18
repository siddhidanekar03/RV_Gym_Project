#!/usr/bin/env python3
"""
RVFitness PostgreSQL Integration Verification Runner.
Executes Alembic migrations, PostgreSQL schema inspection, concurrent check-in races,
QR replay prevention, and pg_try_advisory_lock verification.
"""
import os
import sys
import subprocess
# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from backend.app.core.postgres_test_guard import (
    sanitize_db_url,
    validate_disposable_test_target,
    verify_live_database_identity,
)

pg_url = os.environ.get("POSTGRESQL_TEST_URL")
opt_in = os.environ.get("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "").strip().lower() == "true"


def main():
    print("=" * 70)
    print("RVFitness PostgreSQL Integration Verification Runner")
    print("=" * 70)

    if not opt_in:
        print("[ABORTED] ALLOW_DESTRUCTIVE_POSTGRES_TESTS is unset or not 'true'.")
        print("Explicit opt-in is required to permit destructive schema operations.")
        print("Example: set ALLOW_DESTRUCTIVE_POSTGRES_TESTS=true")
        return 1

    if not pg_url or not pg_url.strip():
        print("[ABORTED] POSTGRESQL_TEST_URL environment variable is unset or empty.")
        print("Explicit configuration of an isolated disposable test database is required.")
        print("No implicit database fallback is permitted.")
        return 1

    sanitized = sanitize_db_url(pg_url)
    print(f"Target Database URL: {sanitized}")

    # Validate disposable target
    try:
        preflight = validate_disposable_test_target(pg_url)
    except Exception as exc:
        print(f"[SAFETY VIOLATION] Target rejected by safety guard: {exc}")
        return 1

    # Check connection and verify live database identity
    try:
        import sqlalchemy as sa
        engine = sa.create_engine(pg_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            identity = verify_live_database_identity(conn, expected_db=preflight["database"])
            pg_version = conn.execute(sa.text("SELECT version();")).scalar()
            print(f"[SUCCESS] Connected to verified disposable PostgreSQL Engine:")
            print(f"          Database: {identity['database']}")
            print(f"          User:     {identity['user']}")
            print(f"          Server:   {identity.get('server_ip') or preflight['host']}")
            print(f"          Version:  {pg_version}")
        engine.dispose()
    except Exception as e:
        print("\n[UNVERIFIED IN LOCAL ENVIRONMENT] PostgreSQL test database is not reachable or rejected.")
        print(f"Connection failure details: {e}\n")
        print("To run this PostgreSQL integration suite locally or in CI/CD:")
        print("1. Start isolated PostgreSQL container:")
        print("   docker compose -f docker-compose.test.yml up -d")
        print("2. Set environment variables:")
        print("   ALLOW_DESTRUCTIVE_POSTGRES_TESTS=true")
        print("   POSTGRESQL_TEST_URL=<sanitized-url>")
        print("3. Run this verification command:")
        print("   python scripts/verify_postgres_integration.py\n")
        return 1

    # Run pytest on the PostgreSQL integration test suite
    print("\nRunning PostgreSQL Integration Test Suite...")
    env = os.environ.copy()
    env["POSTGRESQL_TEST_URL"] = pg_url
    env["ALLOW_DESTRUCTIVE_POSTGRES_TESTS"] = "true"
    cmd = [sys.executable, "-m", "pytest", "backend/tests/test_postgresql_integration.py", "-v"]
    result = subprocess.run(cmd, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
