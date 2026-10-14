"""002_user_sessions_and_branch_scope

Revision ID: 002_user_sessions_and_branch_scope
Revises: 001_initial_rvfitness_schema
Create Date: 2026-10-14 22:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_user_sessions_and_branch_scope"
down_revision: Union[str, Sequence[str], None] = "001_initial_rvfitness_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update users table with branch scope and trainer assignment (batch mode for SQLite)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("branch_id", sa.String(length=50), server_default="narsobawadi", nullable=False)
        )
        batch_op.add_column(
            sa.Column("assigned_trainer_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_index("ix_users_branch_id", ["branch_id"], unique=False)
        batch_op.create_index("ix_users_assigned_trainer_id", ["assigned_trainer_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_users_assigned_trainer_id",
            "users",
            ["assigned_trainer_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 2. Create user_sessions table
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_session_token_hash", "user_sessions", ["session_token_hash"], unique=True)
    op.create_index("ix_user_sessions_is_revoked", "user_sessions", ["is_revoked"], unique=False)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_table("user_sessions")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("fk_users_assigned_trainer_id", type_="foreignkey")
        batch_op.drop_index("ix_users_assigned_trainer_id")
        batch_op.drop_index("ix_users_branch_id")
        batch_op.drop_column("assigned_trainer_id")
        batch_op.drop_column("branch_id")
