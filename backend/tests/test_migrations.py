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

        # 3. Check attendance table unique constraint
        unique_constraints = inspector.get_unique_constraints("attendance_records")
        constraint_names = [uc["name"] for uc in unique_constraints if uc.get("name")]
        assert "uq_user_attendance_daily" in constraint_names or any(
            set(uc["column_names"]) == {"user_id", "check_in_date"} for uc in unique_constraints
        )

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
