from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid


class PersonalRecord(Base, TimestampMixin):
    """Verified lifting milestone and athletic benchmark for gym members."""

    __tablename__ = "personal_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="kg", nullable=False)
    reps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_coach_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    verified_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="personal_records"
    )
    verified_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[verified_by_id]
    )
