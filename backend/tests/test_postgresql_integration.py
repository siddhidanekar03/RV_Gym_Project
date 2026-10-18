"""
PostgreSQL Integration and Concurrency Verification Suite for RVFitness.
Exercises Alembic migrations from clean schema, multi-session concurrent check-ins,
QR nonce replay rejection, and PostgreSQL-specific advisory lock contention.
"""
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, or_
from sqlalchemy.orm import sessionmaker, Session
from alembic.config import Config
from alembic import command

from backend.app.core.security import hash_password
from backend.app.core.database import Base
from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan
from backend.app.models.attendance import AttendanceRecord, AttendanceAttempt, ConsumedQRToken
from backend.app.services.attendance_service import (
    generate_member_qr_token,
    process_qr_checkin,
    process_manual_checkin,
    get_branch_local_date,
    resolve_member_identity,
)
from backend.app.cli.prune_nonces import run_prune_nonces, RVF_QR_CLEANUP_ADVISORY_LOCK_ID

from typing import Optional
from urllib.parse import urlparse

from backend.app.core.postgres_test_guard import (
    sanitize_db_url,
    validate_disposable_test_target,
    verify_live_database_identity,
)

# Require explicit opt-in and URL configuration to guarantee test isolation.
# Never silently fall back to an implicit database with embedded credentials.
POSTGRES_TEST_URL = os.environ.get("POSTGRESQL_TEST_URL")
OPT_IN_DESTRUCTIVE = os.environ.get("ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "").strip().lower() == "true"


def is_postgres_available(url: Optional[str]) -> bool:
    """Check whether PostgreSQL test database is reachable with short timeout."""
    if not url or not OPT_IN_DESTRUCTIVE:
        return False
    try:
        preflight = validate_disposable_test_target(url)
        eng = create_engine(url, connect_args={"connect_timeout": 2})
        with eng.connect() as conn:
            verify_live_database_identity(conn, expected_db=preflight["database"])
        eng.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = is_postgres_available(POSTGRES_TEST_URL)

if not OPT_IN_DESTRUCTIVE:
    skip_reason = (
        "ALLOW_DESTRUCTIVE_POSTGRES_TESTS is unset or not 'true'. "
        "Explicit opt-in is required to permit destructive schema operations (DROP SCHEMA, migrations)."
    )
elif not POSTGRES_TEST_URL:
    skip_reason = (
        "POSTGRESQL_TEST_URL environment variable is unset. "
        "Explicit configuration of an isolated disposable test database is mandatory for PostgreSQL integration tests."
    )
else:
    skip_reason = f"PostgreSQL test database not available or rejected by safety guard at {sanitize_db_url(POSTGRES_TEST_URL)}."

pytestmark = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=skip_reason)


@pytest.fixture(scope="module")
def pg_engine():
    """Create isolated PostgreSQL engine and apply clean Alembic migrations to head."""
    # 1. Static preflight guard
    preflight = validate_disposable_test_target(POSTGRES_TEST_URL)
    expected_db = preflight["database"]

    engine = create_engine(
        POSTGRES_TEST_URL,
        pool_size=10,
        max_overflow=5,
        isolation_level="READ COMMITTED",
    )

    # 2. Verify live database identity before any destructive SQL
    with engine.connect() as conn:
        verify_live_database_identity(conn, expected_db=expected_db)
        ver = conn.execute(sa.text("SELECT version();")).scalar()
        print(f"\n[PostgreSQL Integration] Verified disposable target: {preflight['sanitized_url']}")
        print(f"[PostgreSQL Integration] Connected to: {ver}")

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ini_path = os.path.join(backend_dir, "alembic.ini")
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        POSTGRES_TEST_URL.replace("%", "%%"),
    )

    # 3. Clean schema: drop and recreate public schema on verified disposable target
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        verify_live_database_identity(conn, expected_db=expected_db)
        conn.execute(
            sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        )

    # Run Alembic migrations from base to head on PostgreSQL
    command.upgrade(alembic_cfg, "head")

    yield engine

    # Clean teardown: verify identity again before dropping schema
    preflight = validate_disposable_test_target(POSTGRES_TEST_URL)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        verify_live_database_identity(conn, expected_db=preflight["database"])
        conn.execute(
            sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        )
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """Provide clean database session with per-test data cleanup on PostgreSQL."""
    session_factory = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    session = session_factory()

    yield session

    session.close()
    preflight = validate_disposable_test_target(POSTGRES_TEST_URL)
    with pg_engine.connect() as conn:
        with conn.begin():
            verify_live_database_identity(conn, expected_db=preflight["database"])
            conn.execute(sa.text("DELETE FROM workout_session_exercises;"))
            conn.execute(sa.text("DELETE FROM workout_sessions;"))
            conn.execute(sa.text("DELETE FROM workout_plan_exercises;"))
            conn.execute(sa.text("DELETE FROM workout_plan_assignments;"))
            conn.execute(sa.text("DELETE FROM workout_plans;"))
            conn.execute(sa.text("DELETE FROM fitness_progress_records;"))
            conn.execute(sa.text("DELETE FROM point_ledger_entries;"))
            conn.execute(sa.text("DELETE FROM audit_logs;"))
            conn.execute(sa.text("DELETE FROM consumed_qr_tokens;"))
            conn.execute(sa.text("DELETE FROM attendance_attempts;"))
            conn.execute(sa.text("DELETE FROM attendance_records;"))


def seed_pg_fixtures(session: Session):
    """Seed minimal org, branch, staff, and member fixtures."""
    org = session.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness", code="RVF", contact_email="admin@rvf.in")
        session.add(org)
        session.flush()

    branch = session.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch:
        branch = Branch(id="narsobawadi", organization_id=org.id, name="Narsobawadi Main Campus", code="NRS")
        session.add(branch)
        session.flush()

    staff = session.query(User).filter(User.email == "pg_staff@rvf.in").first()
    if not staff:
        staff = User(
            id="pg-staff-1",
            email="pg_staff@rvf.in",
            name="PG Staff",
            role="front_desk",
            branch_id="narsobawadi",
            hashed_password=hash_password("staffSecret123"),
            is_active=True,
        )
        session.add(staff)

    member = session.query(User).filter(User.email == "pg_member@rvf.in").first()
    if not member:
        member = User(
            id="pg-mem-1",
            email="pg_member@rvf.in",
            name="PG Member",
            role="member",
            membership_id="RVF-PG-001",
            membership_status="active",
            valid_until=date.today() + timedelta(days=90),
            branch_id="narsobawadi",
            hashed_password=hash_password("memberSecret123"),
            is_active=True,
        )
        session.add(member)

    session.commit()
    return {"staff": staff, "member": member, "branch": branch}


def test_postgres_schema_and_constraints(pg_engine):
    """Verify that PostgreSQL schema correctly creates compound daily unique constraints."""
    inspector = inspect(pg_engine)
    tables = set(inspector.get_table_names())
    assert "attendance_records" in tables
    assert "attendance_attempts" in tables
    assert "consumed_qr_tokens" in tables
    assert "announcements" in tables
    assert "point_ledger_entries" in tables
    assert "workout_plans" in tables
    assert "workout_plan_assignments" in tables
    assert "workout_plan_exercises" in tables
    assert "workout_sessions" in tables
    assert "workout_session_exercises" in tables
    assert "fitness_progress_records" in tables

    unique_constraints = inspector.get_unique_constraints("attendance_records")
    constraint_names = [uc["name"] for uc in unique_constraints if uc.get("name")]

    assert (
        "uq_member_branch_attendance_daily" in constraint_names
        or any("member_identity" in uc["column_names"] and "check_in_date" in uc["column_names"] for uc in unique_constraints)
    ), f"uq_member_branch_attendance_daily missing in PG constraints: {unique_constraints}"


def test_postgres_concurrent_registered_checkins(pg_engine, pg_session):
    """
    Simultaneously submit 10 concurrent check-in requests for the same member on PostgreSQL.
    Verify that independent database connections and transactions enforce that exactly
    1 request succeeds and 9 produce controlled rejections and auditable attempts.
    """
    fixtures = seed_pg_fixtures(pg_session)
    member_id = fixtures["member"].id
    staff_id = fixtures["staff"].id
    branch_id = "narsobawadi"
    today = get_branch_local_date(branch_id)
    session_factory = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)

    successes = []
    failures = []

    def perform_checkin(worker_idx: int):
        db = session_factory()
        try:
            st = db.query(User).filter(User.id == staff_id).first()
            rec = process_manual_checkin(
                db=db,
                branch_id=branch_id,
                staff=st,
                reason_code="no_internet",
                member_id=member_id,
                notes=f"Concurrent worker {worker_idx}",
            )
            db.commit()
            return True, rec.id
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(perform_checkin, i) for i in range(10)]
        for f in as_completed(futures):
            ok, res = f.result()
            if ok:
                successes.append(res)
            else:
                failures.append(res)

    assert len(successes) == 1, f"Expected 1 success on PostgreSQL, got {len(successes)}"
    assert len(failures) == 9, f"Expected 9 rejections on PostgreSQL, got {len(failures)}"

    # Authoritative database check
    verify_db = session_factory()
    try:
        records_count = verify_db.query(AttendanceRecord).filter(
            AttendanceRecord.user_id == member_id,
            AttendanceRecord.branch_id == branch_id,
            AttendanceRecord.check_in_date == today,
        ).count()
        assert records_count == 1

        attempts_count = verify_db.query(AttendanceAttempt).filter(
            AttendanceAttempt.user_id == member_id,
            AttendanceAttempt.branch_id == branch_id,
            AttendanceAttempt.failure_reason == "already_checked_in",
        ).count()
        assert attempts_count == 9
    finally:
        verify_db.close()


def test_postgres_concurrent_qr_token_replay(pg_engine, pg_session):
    """
    Simultaneously submit 10 concurrent QR scan requests with the exact same token on PostgreSQL.
    Atomic nonce insertion with primary key constraint must allow exactly 1 and reject 9.
    """
    fixtures = seed_pg_fixtures(pg_session)
    member = fixtures["member"]
    branch_id = "narsobawadi"
    qr_token, _, _ = generate_member_qr_token(member)
    session_factory = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)

    successes = []
    failures = []

    def perform_qr_scan(worker_idx: int):
        db = session_factory()
        try:
            rec = process_qr_checkin(db=db, qr_token=qr_token, branch_id=branch_id)
            db.commit()
            return True, rec.id
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(perform_qr_scan, i) for i in range(10)]
        for f in as_completed(futures):
            ok, res = f.result()
            if ok:
                successes.append(res)
            else:
                failures.append(res)

    assert len(successes) == 1, f"Expected 1 QR scan success, got {len(successes)}"
    assert len(failures) == 9, f"Expected 9 QR replay rejections, got {len(failures)}"


def test_postgres_advisory_lock_contention_and_cleanup(pg_engine, pg_session):
    """
    Verify PostgreSQL advisory locking in prune_nonces CLI:
    When connection A holds the advisory lock (RVF_QR_CLEANUP_ADVISORY_LOCK_ID),
    connection B executing prune_nonces detects lock contention and safely skips.
    Once connection A releases the lock, connection B acquires it and prunes expired nonces.
    """
    fixtures = seed_pg_fixtures(pg_session)
    member = fixtures["member"]

    # Seed 3 expired nonces
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(hours=2)
    n1 = ConsumedQRToken(jti=f"pg-jti-exp-1-{uuid.uuid4().hex[:8]}", user_id=member.id, expires_at=expired_time)
    n2 = ConsumedQRToken(jti=f"pg-jti-exp-2-{uuid.uuid4().hex[:8]}", user_id=member.id, expires_at=expired_time)
    n_act = ConsumedQRToken(jti=f"pg-jti-act-1-{uuid.uuid4().hex[:8]}", user_id=member.id, expires_at=now + timedelta(hours=1))
    pg_session.add_all([n1, n2, n_act])
    pg_session.commit()

    session_factory = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)

    # 1. Connection A acquires advisory lock
    conn_a = pg_engine.connect()
    trans_a = conn_a.begin()
    lock_acquired = conn_a.execute(
        sa.text(f"SELECT pg_try_advisory_lock({RVF_QR_CLEANUP_ADVISORY_LOCK_ID});")
    ).scalar()
    assert lock_acquired is True, "Connection A failed to acquire advisory lock"

    # 2. Connection B attempts prune_nonces -> must detect lock contention and skip
    db_b = session_factory()
    success, pruned = run_prune_nonces(db=db_b, dry_run=False)
    assert success is False, "Expected run_prune_nonces to fail when lock is held"
    assert pruned == 0
    db_b.close()

    # 3. Connection A releases advisory lock
    conn_a.execute(sa.text(f"SELECT pg_advisory_unlock({RVF_QR_CLEANUP_ADVISORY_LOCK_ID});"))
    trans_a.rollback()
    conn_a.close()

    # 4. Connection B re-runs prune_nonces -> succeeds and cleans expired nonces
    db_c = session_factory()
    success2, pruned2 = run_prune_nonces(db=db_c, dry_run=False)
    assert success2 is True
    assert pruned2 >= 2
    db_c.close()
