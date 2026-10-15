from typing import Optional, List, TYPE_CHECKING
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String,
    Integer,
    Numeric,
    Date,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.organization import Branch, Organization


class WorkoutPlan(Base, TimestampMixin):
    """
    Coach-authored workout regimen defining exercises, splits, and training targets.
    Scoped by organization, branch, and authoring trainer.
    """

    __tablename__ = "workout_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Goal: 'strength' | 'hypertrophy' | 'endurance' | 'mobility' | 'general_fitness'
    goal: Mapped[str] = mapped_column(String(50), default="general_fitness", nullable=False, index=True)
    # Difficulty: 'beginner' | 'intermediate' | 'advanced'
    difficulty: Mapped[str] = mapped_column(String(30), default="intermediate", nullable=False, index=True)
    duration_weeks: Mapped[int] = mapped_column(Integer, default=4, nullable=False)

    # Status: 'draft' | 'active' | 'completed' | 'archived'
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Relationships
    trainer: Mapped["User"] = relationship("User", foreign_keys=[trainer_id])
    branch: Mapped["Branch"] = relationship("Branch", foreign_keys=[branch_id])
    organization: Mapped["Organization"] = relationship("Organization", foreign_keys=[organization_id])
    exercises: Mapped[List["WorkoutPlanExercise"]] = relationship(
        "WorkoutPlanExercise", back_populates="plan", cascade="all, delete-orphan", order_by="WorkoutPlanExercise.day_number, WorkoutPlanExercise.exercise_order"
    )
    assignments: Mapped[List["WorkoutPlanAssignment"]] = relationship(
        "WorkoutPlanAssignment", back_populates="plan", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["WorkoutSession"]] = relationship(
        "WorkoutSession", back_populates="plan"
    )


class WorkoutPlanAssignment(Base):
    """
    Direct assignment linking a WorkoutPlan to an enrolled member.
    """

    __tablename__ = "workout_plan_assignments"
    __table_args__ = (
        UniqueConstraint("workout_plan_id", "member_id", name="uq_plan_member_assignment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workout_plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    plan: Mapped["WorkoutPlan"] = relationship("WorkoutPlan", back_populates="assignments")
    member: Mapped["User"] = relationship("User", foreign_keys=[member_id])
    assigned_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by_id])


class WorkoutPlanExercise(Base, TimestampMixin):
    """Prescribed exercise within a plan organized by day and order."""

    __tablename__ = "workout_plan_exercises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workout_plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    day_name: Mapped[str] = mapped_column(String(50), default="Day 1", nullable=False)
    exercise_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sets: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_distance_meters: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    target_weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    rest_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=60, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    plan: Mapped["WorkoutPlan"] = relationship("WorkoutPlan", back_populates="exercises")


class WorkoutSession(Base, TimestampMixin):
    """
    Execution record of a workout session performed by a member.
    Tracks session lifecycle: in_progress -> completed | abandoned.
    """

    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workout_plan_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("workout_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    member_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status: 'in_progress' | 'completed' | 'abandoned'
    status: Mapped[str] = mapped_column(String(30), default="in_progress", nullable=False, index=True)
    session_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Coach verification
    is_coach_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    plan: Mapped[Optional["WorkoutPlan"]] = relationship("WorkoutPlan", back_populates="sessions")
    member: Mapped["User"] = relationship("User", foreign_keys=[member_id])
    branch: Mapped["Branch"] = relationship("Branch", foreign_keys=[branch_id])
    verified_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[verified_by_id])
    completed_exercises: Mapped[List["WorkoutSessionExercise"]] = relationship(
        "WorkoutSessionExercise", back_populates="session", cascade="all, delete-orphan", order_by="WorkoutSessionExercise.exercise_order"
    )


class WorkoutSessionExercise(Base):
    """
    Individual exercise performance metrics recorded during a workout session.
    """

    __tablename__ = "workout_session_exercises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_exercise_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("workout_plan_exercises.id", ondelete="SET NULL"), nullable=True
    )

    exercise_name: Mapped[str] = mapped_column(String(150), nullable=False)
    exercise_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sets_completed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reps_completed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    session: Mapped["WorkoutSession"] = relationship("WorkoutSession", back_populates="completed_exercises")
    plan_exercise: Mapped[Optional["WorkoutPlanExercise"]] = relationship("WorkoutPlanExercise")


class FitnessProgressRecord(Base):
    """
    Member-controlled fitness metrics and measurement journal.
    Private to member by default; accessible to assigned coach only when authorized.
    """

    __tablename__ = "fitness_progress_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Record type: 'body_weight' | 'body_fat_pct' | 'chest_cm' | 'waist_cm' | 'bicep_cm' | 'progress_note' | 'custom'
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Privacy protection: Member-controlled visibility flag
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
