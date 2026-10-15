#!/usr/bin/env python3
"""
RVFitness PostgreSQL Integration Verification Runner.
Executes Alembic migrations, PostgreSQL schema inspection, concurrent check-in races,
QR replay prevention, and pg_try_advisory_lock verification.
"""
import os
import sys
import subprocess

DEFAULT_PG_URL = "postgresql+psycopg2://postgres:postgresPassword123@localhost:5432/rvfitness_test"
pg_url = os.environ.get("POSTGRESQL_TEST_URL", os.environ.get("TEST_DATABASE_URL", DEFAULT_PG_URL))

def main():
    print("=" * 70)
    print("RVFitness Phase 4.3: PostgreSQL Integration Verification")
    print("=" * 70)
    print(f"Target Database URL: {pg_url}")

    # Check connection
    try:
        import sqlalchemy as sa
        engine = sa.create_engine(pg_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            pg_version = conn.execute(sa.text("SELECT version();")).scalar()
            print(f"[SUCCESS] Connected to PostgreSQL Engine:")
            print(f"          {pg_version}")
        engine.dispose()
    except Exception as e:
        print("\n[UNVERIFIED IN LOCAL ENVIRONMENT] PostgreSQL server is not reachable.")
        print(f"Connection failure details: {e}\n")
        print("To run this PostgreSQL integration suite locally or in CI/CD:")
        print("1. Start isolated PostgreSQL container:")
        print("   docker compose -f docker-compose.test.yml up -d")
        print("2. Run this verification command:")
        print("   pytest backend/tests/test_postgresql_integration.py -v")
        print("3. Teardown test container:")
        print("   docker compose -f docker-compose.test.yml down -v\n")
        return 1

    # Run pytest on the PostgreSQL integration test suite
    print("\nRunning PostgreSQL Integration Test Suite...")
    env = os.environ.copy()
    env["POSTGRESQL_TEST_URL"] = pg_url
    cmd = [sys.executable, "-m", "pytest", "backend/tests/test_postgresql_integration.py", "-v"]
    result = subprocess.run(cmd, env=env)
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
