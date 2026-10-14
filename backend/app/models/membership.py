from typing import Optional, List, TYPE_CHECKING
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, Boolean, Text, Date, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.billing import Invoice


class MembershipPlan(Base, TimestampMixin):
    """Available membership plan offerings with pricing, cycle, and perks."""

    __tablename__ = "membership_plans"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Category: 'strength' | 'crossfit' | 'cardio' | 'personal_training' | 'general' | 'vip'
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False, index=True)
    # Access Scope: 'single_branch' | 'all_branches'
    access_scope: Mapped[str] = mapped_column(String(50), default="single_branch", nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="₹", nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    perks: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="membership_plan"
    )
    enrollments: Mapped[List["Enrollment"]] = relationship(
        "Enrollment", back_populates="plan", cascade="all, delete-orphan"
    )
    prices: Mapped[List["PlanPrice"]] = relationship(
        "PlanPrice", back_populates="plan", cascade="all, delete-orphan"
    )


class PlanPrice(Base, TimestampMixin):
    """Effective-dated price history for membership plans."""

    __tablename__ = "plan_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("membership_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="₹", nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    plan: Mapped["MembershipPlan"] = relationship("MembershipPlan", back_populates="prices")


class Enrollment(Base, TimestampMixin):
    """Membership enrollment applications submitted via portal or desk."""

    __tablename__ = "enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), default="narsobawadi", nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="₹", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending_verification", nullable=False, index=True
    )
    accepted_terms: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verified_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    plan: Mapped["MembershipPlan"] = relationship("MembershipPlan", back_populates="enrollments")
    verified_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[verified_by_id])
    initial_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", back_populates="enrollment", uselist=False
    )


class MembershipChange(Base, TimestampMixin):
    """Audit log of membership lifecycle alterations: enrollment, renewal, freeze, cancellation."""

    __tablename__ = "membership_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Action type: 'enrollment' | 'renewal' | 'freeze' | 'unfreeze' | 'cancellation'
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    days_extended: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="membership_changes"
    )
    performed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[performed_by_id])
