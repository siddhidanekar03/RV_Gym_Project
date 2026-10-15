"""006_privacy_leaderboard_and_engagement

Revision ID: 006_privacy_leaderboard
Revises: 005_announcements_operations
Create Date: 2026-10-15 09:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_privacy_leaderboard"
down_revision: Union[str, Sequence[str], None] = "005_announcements_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add privacy and alias columns to users table
    op.add_column("users", sa.Column("leaderboard_alias", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_leaderboard_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_users_leaderboard_alias", "users", ["leaderboard_alias"], unique=True)

    # 2. Create point_ledger_entries table
    op.create_table(
        "point_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_point_ledger_source"),
    )

    # 3. Create indexes for high-throughput queries and period filtering
    op.create_index("ix_point_ledger_user_id", "point_ledger_entries", ["user_id"])
    op.create_index("ix_point_ledger_branch_id", "point_ledger_entries", ["branch_id"])
    op.create_index("ix_point_ledger_organization_id", "point_ledger_entries", ["organization_id"])
    op.create_index("ix_point_ledger_source_type", "point_ledger_entries", ["source_type"])
    op.create_index("ix_point_ledger_source_id", "point_ledger_entries", ["source_id"])
    op.create_index("ix_point_ledger_event_date", "point_ledger_entries", ["event_date"])
    op.create_index("ix_point_ledger_year_month", "point_ledger_entries", ["year", "month"])
    op.create_index("ix_point_ledger_user_year_month", "point_ledger_entries", ["user_id", "year", "month"])
    op.create_index("ix_point_ledger_branch_year_month", "point_ledger_entries", ["branch_id", "year", "month"])


def downgrade() -> None:
    op.drop_index("ix_point_ledger_branch_year_month", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_user_year_month", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_year_month", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_event_date", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_source_id", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_source_type", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_organization_id", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_branch_id", table_name="point_ledger_entries")
    op.drop_index("ix_point_ledger_user_id", table_name="point_ledger_entries")
    op.drop_table("point_ledger_entries")

    op.drop_index("ix_users_leaderboard_alias", table_name="users")
    op.drop_column("users", "is_leaderboard_visible")
    op.drop_column("users", "leaderboard_alias")
