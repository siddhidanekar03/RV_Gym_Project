"""010_coach_photo_editor

Revision ID: 010_coach_photo_editor
Revises: 009_enrollment_workflow
Create Date: 2026-10-17 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "010_coach_photo_editor"
down_revision: Union[str, Sequence[str], None] = "009_enrollment_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add photo_url column to trainer_profiles table
    op.add_column("trainer_profiles", sa.Column("photo_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("trainer_profiles", "photo_url")
