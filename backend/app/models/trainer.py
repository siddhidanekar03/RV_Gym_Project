from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Boolean, Text, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User


class TrainerProfile(Base, TimestampMixin):
    """Professional coach profile, credentials, and capacity."""

    __tablename__ = "trainer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    specialization: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    certifications: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    experience_years: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("5.00"), nullable=False)
    max_clients: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_accepting_clients: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="trainer_profile")


class TrainerMemberAssignment(Base, TimestampMixin):
    """Historical and active assignment records between coaches and members."""

    __tablename__ = "trainer_member_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trainer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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

    trainer: Mapped["User"] = relationship("User", foreign_keys=[trainer_id])
    member: Mapped["User"] = relationship("User", foreign_keys=[member_id])
    assigned_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by_id])
