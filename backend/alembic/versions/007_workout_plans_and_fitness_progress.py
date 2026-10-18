"""007_workout_plans_and_fitness_progress

Revision ID: 007_workout_plans_and_progress
Revises: 006_privacy_leaderboard
Create Date: 2026-10-15 10:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007_workout_plans_and_progress"
down_revision: Union[str, Sequence[str], None] = "006_privacy_leaderboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. workout_plans table
    op.create_table(
        "workout_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("trainer_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goal", sa.String(length=50), server_default="general_fitness", nullable=False),
        sa.Column("difficulty", sa.String(length=30), server_default="intermediate", nullable=False),
        sa.Column("duration_weeks", sa.Integer(), server_default="4", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="active", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trainer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_plans_organization_id", "workout_plans", ["organization_id"])
    op.create_index("ix_workout_plans_branch_id", "workout_plans", ["branch_id"])
    op.create_index("ix_workout_plans_trainer_id", "workout_plans", ["trainer_id"])
    op.create_index("ix_workout_plans_goal", "workout_plans", ["goal"])
    op.create_index("ix_workout_plans_difficulty", "workout_plans", ["difficulty"])
    op.create_index("ix_workout_plans_status", "workout_plans", ["status"])

    # 2. workout_plan_assignments table
    op.create_table(
        "workout_plan_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workout_plan_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_by_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["workout_plan_id"], ["workout_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_plan_id", "member_id", name="uq_plan_member_assignment"),
    )
    op.create_index("ix_workout_plan_assignments_plan_id", "workout_plan_assignments", ["workout_plan_id"])
    op.create_index("ix_workout_plan_assignments_member_id", "workout_plan_assignments", ["member_id"])

    # 3. workout_plan_exercises table
    op.create_table(
        "workout_plan_exercises",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workout_plan_id", sa.String(length=36), nullable=False),
        sa.Column("day_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("day_name", sa.String(length=50), server_default="Day 1", nullable=False),
        sa.Column("exercise_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("target_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("target_distance_meters", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("target_weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), server_default="60", nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workout_plan_id"], ["workout_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_plan_exercises_plan_id", "workout_plan_exercises", ["workout_plan_id"])
    op.create_index("ix_workout_plan_exercises_day_order", "workout_plan_exercises", ["workout_plan_id", "day_number", "exercise_order"])

    # 4. workout_sessions table
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workout_plan_id", sa.String(length=36), nullable=True),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="in_progress", nullable=False),
        sa.Column("session_name", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_coach_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verified_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workout_plan_id"], ["workout_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["member_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_sessions_plan_id", "workout_sessions", ["workout_plan_id"])
    op.create_index("ix_workout_sessions_member_id", "workout_sessions", ["member_id"])
    op.create_index("ix_workout_sessions_branch_id", "workout_sessions", ["branch_id"])
    op.create_index("ix_workout_sessions_date", "workout_sessions", ["session_date"])
    op.create_index("ix_workout_sessions_status", "workout_sessions", ["status"])
    op.create_index("ix_workout_sessions_member_date", "workout_sessions", ["member_id", "session_date"])

    # 5. workout_session_exercises table
    op.create_table(
        "workout_session_exercises",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("plan_exercise_id", sa.String(length=36), nullable=True),
        sa.Column("exercise_name", sa.String(length=150), nullable=False),
        sa.Column("exercise_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sets_completed", sa.Integer(), nullable=True),
        sa.Column("reps_completed", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["workout_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_exercise_id"], ["workout_plan_exercises.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_session_exercises_session_id", "workout_session_exercises", ["session_id"])

    # 6. fitness_progress_records table
    op.create_table(
        "fitness_progress_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("recorded_date", sa.Date(), nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fitness_progress_user_id", "fitness_progress_records", ["user_id"])
    op.create_index("ix_fitness_progress_type", "fitness_progress_records", ["record_type"])
    op.create_index("ix_fitness_progress_date", "fitness_progress_records", ["recorded_date"])
    op.create_index("ix_fitness_progress_user_type_date", "fitness_progress_records", ["user_id", "record_type", "recorded_date"])


def downgrade() -> None:
    op.drop_index("ix_fitness_progress_user_type_date", table_name="fitness_progress_records")
    op.drop_index("ix_fitness_progress_date", table_name="fitness_progress_records")
    op.drop_index("ix_fitness_progress_type", table_name="fitness_progress_records")
    op.drop_index("ix_fitness_progress_user_id", table_name="fitness_progress_records")
    op.drop_table("fitness_progress_records")

    op.drop_index("ix_workout_session_exercises_session_id", table_name="workout_session_exercises")
    op.drop_table("workout_session_exercises")

    op.drop_index("ix_workout_sessions_member_date", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_status", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_date", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_branch_id", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_member_id", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_plan_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")

    op.drop_index("ix_workout_plan_exercises_day_order", table_name="workout_plan_exercises")
    op.drop_index("ix_workout_plan_exercises_plan_id", table_name="workout_plan_exercises")
    op.drop_table("workout_plan_exercises")

    op.drop_index("ix_workout_plan_assignments_member_id", table_name="workout_plan_assignments")
    op.drop_index("ix_workout_plan_assignments_plan_id", table_name="workout_plan_assignments")
    op.drop_table("workout_plan_assignments")

    op.drop_index("ix_workout_plans_status", table_name="workout_plans")
    op.drop_index("ix_workout_plans_difficulty", table_name="workout_plans")
    op.drop_index("ix_workout_plans_goal", table_name="workout_plans")
    op.drop_index("ix_workout_plans_trainer_id", table_name="workout_plans")
    op.drop_index("ix_workout_plans_branch_id", table_name="workout_plans")
    op.drop_index("ix_workout_plans_organization_id", table_name="workout_plans")
    op.drop_table("workout_plans")
