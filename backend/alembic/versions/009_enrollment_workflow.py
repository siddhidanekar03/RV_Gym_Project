"""009_enrollment_workflow

Revision ID: 009_enrollment_workflow
Revises: 008_owner_web_equip_gallery
Create Date: 2026-10-16 21:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "009_enrollment_workflow"
down_revision: Union[str, Sequence[str], None] = "008_owner_web_equip_gallery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add user_id column to enrollments
    op.add_column("enrollments", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_enrollments_user_id_users",
        "enrollments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_enrollments_user_id", "enrollments", ["user_id"], unique=False)

    # 2. Add rejection_reason column to enrollments
    op.add_column("enrollments", sa.Column("rejection_reason", sa.Text(), nullable=True))

    # 3. Backfill user_id from matching user emails or invoices
    op.execute(
        """
        UPDATE enrollments
        SET user_id = users.id
        FROM users
        WHERE LOWER(TRIM(enrollments.email)) = LOWER(TRIM(users.email))
          AND enrollments.user_id IS NULL;
        """
    )
    op.execute(
        """
        UPDATE enrollments
        SET user_id = invoices.user_id
        FROM invoices
        WHERE invoices.enrollment_id = enrollments.id
          AND invoices.user_id IS NOT NULL
          AND enrollments.user_id IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_column("enrollments", "rejection_reason")
    op.drop_index("ix_enrollments_user_id", table_name="enrollments")
    op.drop_constraint("fk_enrollments_user_id_users", "enrollments", type_="foreignkey")
    op.drop_column("enrollments", "user_id")
