from typing import Optional, List, TYPE_CHECKING
from datetime import date
from sqlalchemy import String, Integer, Boolean, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.membership import MembershipPlan, MembershipChange
    from backend.app.models.attendance import AttendanceRecord
    from backend.app.models.personal_record import PersonalRecord
    from backend.app.models.audit import AuditLog
    from backend.app.models.session import UserSession
    from backend.app.models.organization import Branch, MemberBranchAccess
    from backend.app.models.trainer import TrainerProfile
    from backend.app.models.billing import Invoice, Payment
    from backend.app.models.leaderboard import PointLedgerEntry
    from backend.app.models.workout import (
        WorkoutPlan,
        WorkoutPlanAssignment,
        WorkoutSession,
        FitnessProgressRecord,
    )
    from backend.app.models.member_profile import MemberProfile, MemberBodyMeasurement


class User(Base, TimestampMixin):
    """User account entity covering members, coaches, staff, and administrators."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Access Role: 'org_admin' | 'branch_manager' | 'front_desk' | 'trainer' | 'member'
    # (also compatible with legacy 'admin' and 'staff' aliases)
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False, index=True)
    staff_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Membership Details
    membership_id: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    membership_plan_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("membership_plans.id", ondelete="SET NULL"), nullable=True
    )
    # Status: 'pending' | 'active' | 'expired' | 'frozen' | 'cancelled' | 'suspended'
    membership_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    member_since: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Leaderboard & Gamification Privacy Fields
    leaderboard_alias: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    is_leaderboard_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Branch and Coaching Assignment Scope
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id"), default="narsobawadi", nullable=False, index=True
    )
    assigned_trainer_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    branch: Mapped[Optional["Branch"]] = relationship(
        "Branch", back_populates="users", foreign_keys=[branch_id], primaryjoin="User.branch_id == Branch.id"
    )
    branch_access_grants: Mapped[List["MemberBranchAccess"]] = relationship(
        "MemberBranchAccess", back_populates="user", cascade="all, delete-orphan"
    )
    membership_plan: Mapped[Optional["MembershipPlan"]] = relationship(
        "MembershipPlan", back_populates="users"
    )
    membership_changes: Mapped[List["MembershipChange"]] = relationship(
        "MembershipChange",
        foreign_keys="MembershipChange.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    attendance_records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord",
        foreign_keys="AttendanceRecord.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    personal_records: Mapped[List["PersonalRecord"]] = relationship(
        "PersonalRecord",
        back_populates="user",
        foreign_keys="PersonalRecord.user_id",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="actor",
        foreign_keys="AuditLog.actor_id",
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    trainer_profile: Mapped[Optional["TrainerProfile"]] = relationship(
        "TrainerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    profile: Mapped[Optional["MemberProfile"]] = relationship(
        "MemberProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    assigned_trainer: Mapped[Optional["User"]] = relationship(
        "User",
        remote_side=[id],
        foreign_keys=[assigned_trainer_id],
        back_populates="assigned_members",
    )
    assigned_members: Mapped[List["User"]] = relationship(
        "User",
        foreign_keys=[assigned_trainer_id],
        back_populates="assigned_trainer",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice", back_populates="user"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", foreign_keys="Payment.user_id", back_populates="user"
    )
    point_ledger_entries: Mapped[List["PointLedgerEntry"]] = relationship(
        "PointLedgerEntry",
        foreign_keys="PointLedgerEntry.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    workout_plan_assignments: Mapped[List["WorkoutPlanAssignment"]] = relationship(
        "WorkoutPlanAssignment",
        foreign_keys="WorkoutPlanAssignment.member_id",
        back_populates="member",
        cascade="all, delete-orphan",
    )
    workout_sessions: Mapped[List["WorkoutSession"]] = relationship(
        "WorkoutSession",
        foreign_keys="WorkoutSession.member_id",
        back_populates="member",
        cascade="all, delete-orphan",
    )
    fitness_progress_records: Mapped[List["FitnessProgressRecord"]] = relationship(
        "FitnessProgressRecord",
        foreign_keys="FitnessProgressRecord.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
