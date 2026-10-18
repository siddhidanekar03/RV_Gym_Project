"""011_member_health_and_metrics

Revision ID: 011_member_health_metrics
Revises: 010_coach_photo_editor
Create Date: 2026-10-18 01:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "011_member_health_metrics"
down_revision: Union[str, Sequence[str], None] = "010_coach_photo_editor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create member_profiles table
    op.create_table(
        "member_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=30), nullable=True),
        sa.Column("profile_photo_url", sa.String(length=500), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("emergency_contact_name", sa.String(length=150), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(length=50), nullable=True),
        sa.Column("past_injuries", sa.Text(), nullable=True),
        sa.Column("current_injuries", sa.Text(), nullable=True),
        sa.Column("health_conditions", sa.Text(), nullable=True),
        sa.Column("exercise_restrictions", sa.Text(), nullable=True),
        sa.Column("allergies", sa.Text(), nullable=True),
        sa.Column("surgery_history", sa.Text(), nullable=True),
        sa.Column("current_medications", sa.Text(), nullable=True),
        sa.Column("has_medication_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fitness_goals", sa.Text(), nullable=True),
        sa.Column("health_notes", sa.Text(), nullable=True),
        sa.Column("primary_goal", sa.String(length=50), server_default="general_fitness", nullable=False),
        sa.Column("target_weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("last_health_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_member_profiles_user_id"),
    )
    op.create_index("ix_member_profiles_user_id", "member_profiles", ["user_id"])

    # 2. Create member_measurements table
    op.create_table(
        "member_measurements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("recorded_date", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("height_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("body_fat_pct", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("chest_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("waist_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("hips_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("arms_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("thighs_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("calves_cm", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("recorded_by_id", sa.String(length=36), nullable=True),
        sa.Column("recorded_by_role", sa.String(length=30), server_default="member", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_measurements_user_id", "member_measurements", ["user_id"])
    op.create_index("ix_member_measurements_date", "member_measurements", ["recorded_date"])
    op.create_index(
        "ix_member_measurements_user_date",
        "member_measurements",
        ["user_id", "recorded_date"],
    )

    # 3. Add duration_minutes and rpe to workout_sessions
    op.add_column("workout_sessions", sa.Column("duration_minutes", sa.Integer(), nullable=True))
    op.add_column("workout_sessions", sa.Column("rpe", sa.Integer(), nullable=True))


def downgrade() -> None:
    # 3. Drop columns from workout_sessions
    op.drop_column("workout_sessions", "rpe")
    op.drop_column("workout_sessions", "duration_minutes")

    # 2. Drop member_measurements
    op.drop_index("ix_member_measurements_user_date", table_name="member_measurements")
    op.drop_index("ix_member_measurements_date", table_name="member_measurements")
    op.drop_index("ix_member_measurements_user_id", table_name="member_measurements")
    op.drop_table("member_measurements")

    # 1. Drop member_profiles
    op.drop_index("ix_member_profiles_user_id", table_name="member_profiles")
    op.drop_table("member_profiles")
