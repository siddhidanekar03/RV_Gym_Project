"""004_production_attendance_qr_and_reporting

Revision ID: 004_production_attendance
Revises: 003_enterprise_org_billing
Create Date: 2026-10-14 22:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004_production_attendance"
down_revision: Union[str, Sequence[str], None] = "003_enterprise_org_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update attendance_records table with audit metadata, source tracking, and branch-level uniqueness
    with op.batch_alter_table("attendance_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("member_identity", sa.String(length=100), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("source", sa.String(length=30), server_default="portal", nullable=False)
        )
        batch_op.add_column(
            sa.Column("staff_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("manual_reason", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("is_backfill", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("backfill_operator_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("backfill_entry_operator", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(
            sa.Column("backfill_reason", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("member_name", sa.String(length=150), nullable=True)
        )
        batch_op.add_column(
            sa.Column("member_phone", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("membership_id", sa.String(length=50), nullable=True)
        )

        # Alter user_id to be nullable for desk walk-in members without web portal accounts
        batch_op.alter_column("user_id", existing_type=sa.String(length=36), nullable=True)

        # Drop old single-user-daily constraint if present, add branch-scoped constraint
        try:
            batch_op.drop_constraint("uq_user_attendance_daily", type_="unique")
        except Exception:
            pass
        batch_op.create_unique_constraint(
            "uq_user_branch_attendance_daily",
            ["user_id", "branch_id", "check_in_date"],
        )
        batch_op.create_unique_constraint(
            "uq_member_branch_attendance_daily",
            ["member_identity", "branch_id", "check_in_date"],
        )

        batch_op.create_index("ix_attendance_records_member_identity", ["member_identity"], unique=False)
        batch_op.create_index("ix_attendance_records_source", ["source"], unique=False)
        batch_op.create_index("ix_attendance_records_staff_id", ["staff_id"], unique=False)
        batch_op.create_index("ix_attendance_records_member_phone", ["member_phone"], unique=False)
        batch_op.create_index("ix_attendance_records_membership_id", ["membership_id"], unique=False)

    # Backfill member_identity on existing attendance records
    try:
        op.execute("UPDATE attendance_records SET member_identity = 'user:' || user_id WHERE user_id IS NOT NULL AND (member_identity IS NULL OR member_identity = '')")
        op.execute("UPDATE attendance_records SET member_identity = 'member:' || membership_id WHERE (member_identity IS NULL OR member_identity = '') AND membership_id IS NOT NULL")
        op.execute("UPDATE attendance_records SET member_identity = 'phone:' || member_phone WHERE (member_identity IS NULL OR member_identity = '') AND member_phone IS NOT NULL")
        op.execute("UPDATE attendance_records SET member_identity = 'legacy:' || id WHERE member_identity IS NULL OR member_identity = ''")
    except Exception:
        pass

    # 2. Create attendance_attempts table for audit trail and manager overrides
    op.create_table(
        "attendance_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_identity", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("membership_id", sa.String(length=50), nullable=True),
        sa.Column("member_phone", sa.String(length=50), nullable=True),
        sa.Column("member_name", sa.String(length=150), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("failure_reason", sa.String(length=100), nullable=False),
        sa.Column("failure_detail", sa.String(length=255), nullable=True),
        sa.Column("staff_id", sa.String(length=36), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_overridden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("overridden_by_id", sa.String(length=36), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_attendance_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["overridden_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["override_attendance_id"], ["attendance_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["staff_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attendance_attempts_member_identity", "attendance_attempts", ["member_identity"], unique=False)
    op.create_index("ix_attendance_attempts_user_id", "attendance_attempts", ["user_id"], unique=False)
    op.create_index("ix_attendance_attempts_branch_id", "attendance_attempts", ["branch_id"], unique=False)
    op.create_index("ix_attendance_attempts_failure_reason", "attendance_attempts", ["failure_reason"], unique=False)
    op.create_index("ix_attendance_attempts_attempted_at", "attendance_attempts", ["attempted_at"], unique=False)
    op.create_index("ix_attendance_attempts_is_overridden", "attendance_attempts", ["is_overridden"], unique=False)

    # 3. Create consumed_qr_tokens table for replay attack prevention
    op.create_table(
        "consumed_qr_tokens",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index("ix_consumed_qr_tokens_user_id", "consumed_qr_tokens", ["user_id"], unique=False)
    op.create_index("ix_consumed_qr_tokens_expires_at", "consumed_qr_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_table("consumed_qr_tokens")
    op.drop_table("attendance_attempts")

    with op.batch_alter_table("attendance_records", schema=None) as batch_op:
        batch_op.drop_constraint("uq_member_branch_attendance_daily", type_="unique")
        batch_op.drop_constraint("uq_user_branch_attendance_daily", type_="unique")
        batch_op.create_unique_constraint("uq_user_attendance_daily", ["user_id", "check_in_date"])
        batch_op.drop_index("ix_attendance_records_member_identity")
        batch_op.drop_index("ix_attendance_records_membership_id")
        batch_op.drop_index("ix_attendance_records_member_phone")
        batch_op.drop_index("ix_attendance_records_staff_id")
        batch_op.drop_index("ix_attendance_records_source")
        batch_op.drop_column("membership_id")
        batch_op.drop_column("member_phone")
        batch_op.drop_column("member_name")
        batch_op.drop_column("backfill_reason")
        batch_op.drop_column("backfill_entry_operator")
        batch_op.drop_column("backfill_operator_id")
        batch_op.drop_column("is_backfill")
        batch_op.drop_column("manual_reason")
        batch_op.drop_column("staff_id")
        batch_op.drop_column("source")
        batch_op.drop_column("member_identity")
