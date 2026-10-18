from typing import Optional, List, TYPE_CHECKING
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Integer,
    Boolean,
    Date,
    DateTime,
    Text,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User


class MemberProfile(Base, TimestampMixin):
    """
    Comprehensive member personal information, health and injury history,
    movement restrictions, and physical training targets.
    Keeps sensitive health disclosures isolated from the core user authentication record.
    """

    __tablename__ = "member_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # Personal details
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Health & injury disclosures (sensitive personal data)
    past_injuries: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_injuries: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exercise_restrictions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allergies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    surgery_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_medications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_medication_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fitness_goals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_health_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Physical training targets
    height_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    target_weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    primary_goal: Mapped[str] = mapped_column(String(50), default="general_fitness", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="profile")
    measurements: Mapped[List["MemberBodyMeasurement"]] = relationship(
        "MemberBodyMeasurement",
        primaryjoin="MemberProfile.user_id == foreign(MemberBodyMeasurement.user_id)",
        order_by="MemberBodyMeasurement.recorded_date.desc()",
        cascade="all, delete-orphan",
    )

    def calculate_age(self) -> Optional[int]:
        """Compute member age dynamically from date of birth rather than storing duplicate mutable state."""
        if not self.date_of_birth:
            return None
        today = date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )


class MemberBodyMeasurement(Base):
    """
    Time-series body measurement records capturing dated weight, height, body fat,
    and anatomical circumferences for fitness progress tracking.
    """

    __tablename__ = "member_measurements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recorded_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    # Measurements
    weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    height_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    body_fat_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    chest_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    waist_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    hips_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    arms_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    thighs_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)
    calves_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True)

    # Metadata
    recorded_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], overlaps="measurements")
    recorded_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[recorded_by_id])
