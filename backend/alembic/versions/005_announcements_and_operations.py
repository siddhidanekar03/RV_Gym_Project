"""005_announcements_and_operations

Revision ID: 005_announcements_operations
Revises: 004_production_attendance
Create Date: 2026-10-15 08:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005_announcements_operations"
down_revision: Union[str, Sequence[str], None] = "004_production_attendance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create announcements table
    op.create_table(
        "announcements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=True),
        sa.Column("is_org_wide", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), server_default="general", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("audience", sa.String(length=30), server_default="public", nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="chk_announcement_expiry_after_publish",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Indexes for efficient audience, branch, and status queries
    op.create_index("ix_announcements_organization_id", "announcements", ["organization_id"])
    op.create_index("ix_announcements_branch_id", "announcements", ["branch_id"])
    op.create_index("ix_announcements_is_org_wide", "announcements", ["is_org_wide"])
    op.create_index("ix_announcements_category", "announcements", ["category"])
    op.create_index("ix_announcements_priority", "announcements", ["priority"])
    op.create_index("ix_announcements_status", "announcements", ["status"])
    op.create_index("ix_announcements_audience", "announcements", ["audience"])
    op.create_index("ix_announcements_author_id", "announcements", ["author_id"])
    op.create_index("ix_announcements_published_at", "announcements", ["published_at"])
    op.create_index("ix_announcements_expires_at", "announcements", ["expires_at"])
    op.create_index(
        "ix_announcements_org_status_published",
        "announcements",
        ["organization_id", "status", "published_at"],
    )
    op.create_index(
        "ix_announcements_branch_status",
        "announcements",
        ["branch_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_announcements_branch_status", table_name="announcements")
    op.drop_index("ix_announcements_org_status_published", table_name="announcements")
    op.drop_index("ix_announcements_expires_at", table_name="announcements")
    op.drop_index("ix_announcements_published_at", table_name="announcements")
    op.drop_index("ix_announcements_author_id", table_name="announcements")
    op.drop_index("ix_announcements_audience", table_name="announcements")
    op.drop_index("ix_announcements_status", table_name="announcements")
    op.drop_index("ix_announcements_priority", table_name="announcements")
    op.drop_index("ix_announcements_category", table_name="announcements")
    op.drop_index("ix_announcements_is_org_wide", table_name="announcements")
    op.drop_index("ix_announcements_branch_id", table_name="announcements")
    op.drop_index("ix_announcements_organization_id", table_name="announcements")
    op.drop_table("announcements")
