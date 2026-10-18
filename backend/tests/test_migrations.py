import os
import tempfile
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

expected_tables = {
    "membership_plans",
    "users",
    "enrollments",
    "attendance_records",
    "personal_records",
    "contact_inquiries",
    "audit_logs",
    "user_sessions",
    "organizations",
    "branches",
    "member_branch_access",
    "plan_prices",
    "membership_changes",
    "trainer_profiles",
    "trainer_member_assignments",
    "invoice_sequences",
    "invoices",
    "invoice_lines",
    "payments",
    "attendance_attempts",
    "consumed_qr_tokens",
    "announcements",
    "point_ledger_entries",
    "workout_plans",
    "workout_plan_assignments",
    "workout_plan_exercises",
    "workout_sessions",
    "workout_session_exercises",
    "fitness_progress_records",
}


def test_alembic_migrations_lifecycle():
    """Verify Alembic applies full migration up to head and downgrades cleanly to base."""
    # Create isolated temp file for migration run
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ini_path = os.path.join(backend_dir, "alembic.ini")

        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
        # Force alembic to use this test database
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        # 2. Inspect created tables
        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())

        assert expected_tables.issubset(actual_tables), (
            f"Expected tables {expected_tables} not fully present in migrated DB: {actual_tables}"
        )

        # 3. Check attendance table unique constraints
        unique_constraints = inspector.get_unique_constraints("attendance_records")
        constraint_names = [uc["name"] for uc in unique_constraints if uc.get("name")]
        assert (
            "uq_user_branch_attendance_daily" in constraint_names
            or any("user_id" in uc["column_names"] and "check_in_date" in uc["column_names"] for uc in unique_constraints)
        )
        assert (
            "uq_member_branch_attendance_daily" in constraint_names
            or any("member_identity" in uc["column_names"] and "check_in_date" in uc["column_names"] for uc in unique_constraints)
        )

        columns = [c["name"] for c in inspector.get_columns("attendance_records")]
        assert "member_identity" in columns

        engine.dispose()

        # 4. Downgrade to base
        command.downgrade(alembic_cfg, "base")

        engine2 = create_engine(f"sqlite:///{db_path}")
        inspector2 = inspect(engine2)
        tables_after_downgrade = set(inspector2.get_table_names())
        assert not expected_tables.intersection(tables_after_downgrade)
        engine2.dispose()

    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass


def test_migration_004_upgrade_on_existing_database_and_rollback():
    """
    Verify migration 004 successfully upgrades an existing database containing
    pre-Phase-4 attendance records, populates member_identity, enforces the
    new unique constraint, and rolls back cleanly to 003.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ini_path = os.path.join(backend_dir, "alembic.ini")

        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

        # 1. Upgrade up to revision 003 (existing database state)
        command.upgrade(alembic_cfg, "003_enterprise_org_billing")

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            import sqlalchemy as sa
            conn.execute(sa.text(
                "INSERT INTO organizations (id, name, code, contact_email, created_at, updated_at) "
                "VALUES ('org-1', 'RV Fitness', 'RVF', 'admin@rvf.in', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO branches (id, organization_id, name, code, created_at, updated_at) "
                "VALUES ('narsobawadi', 'org-1', 'Narsobawadi Main Campus', 'NRS', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO users (id, email, hashed_password, name, role, branch_id, is_active, streak_days, created_at, updated_at) "
                "VALUES ('user-existing-1', 'existing@rvf.in', 'hash', 'Existing Member', 'member', 'narsobawadi', 1, 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO attendance_records (id, user_id, branch_id, check_in_date, check_in_time, method, notes, created_at, updated_at) "
                "VALUES ('att-rec-1', 'user-existing-1', 'narsobawadi', '2026-10-10', CURRENT_TIMESTAMP, 'portal', 'Pre-existing check-in', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))

        # 2. Upgrade to head (applies 004 on representative existing data)
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(engine)
        cols_004 = [c["name"] for c in inspector.get_columns("attendance_records")]
        assert "member_identity" in cols_004
        assert "consumed_qr_tokens" in inspector.get_table_names()
        assert "attendance_attempts" in inspector.get_table_names()

        # Verify historical record was backfilled with canonical member_identity
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT id, user_id, member_identity, notes FROM attendance_records WHERE id = 'att-rec-1'")
            ).fetchone()
            assert row is not None
            assert row[1] == "user-existing-1"
            assert row[2] == "user:user-existing-1"
            assert row[3] == "Pre-existing check-in"

            # Verify that attempting to insert a duplicate with the same member_identity, branch, date fails
            with pytest.raises(Exception):
                conn.execute(
                    sa.text(
                        "INSERT INTO attendance_records (id, user_id, member_identity, branch_id, check_in_date, check_in_time, method, source, created_at, updated_at) "
                        "VALUES ('att-rec-dup', 'user-existing-1', 'user:user-existing-1', 'narsobawadi', '2026-10-10', CURRENT_TIMESTAMP, 'manual', 'manual', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )

        # 3. Rollback to 003 and verify historical attendance is preserved
        command.downgrade(alembic_cfg, "003_enterprise_org_billing")

        inspector_post_rollback = inspect(engine)
        cols_post_rollback = [c["name"] for c in inspector_post_rollback.get_columns("attendance_records")]
        assert "member_identity" not in cols_post_rollback
        assert "consumed_qr_tokens" not in inspector_post_rollback.get_table_names()
        assert "attendance_attempts" not in inspector_post_rollback.get_table_names()

        # Historical attendance record must survive the rollback
        with engine.connect() as conn:
            hist_row = conn.execute(
                sa.text("SELECT id, user_id, check_in_date, notes FROM attendance_records WHERE id = 'att-rec-1'")
            ).fetchone()
            assert hist_row is not None
            assert hist_row[0] == "att-rec-1"
            assert hist_row[1] == "user-existing-1"
            assert str(hist_row[2]) == "2026-10-10"

        # 4. Verify re-upgrading back to head
        command.upgrade(alembic_cfg, "head")
        engine.dispose()

    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass
