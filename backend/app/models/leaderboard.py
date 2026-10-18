from typing import Optional, TYPE_CHECKING
from datetime import date
from sqlalchemy import (
    String,
    Integer,
    Date,
    DateTime,
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


class PointLedgerEntry(Base, TimestampMixin):
    """
    Durable, auditable, and idempotent points ledger for member gamification.
    Tracks every point-earning and point-adjustment event with deterministic sourcing.
    """

    __tablename__ = "point_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            name="uq_point_ledger_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Source type: 'attendance_verified', 'streak_milestone', 'pr_verified', 'admin_adjustment', 'attendance_reversal'
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Source identifier: e.g. attendance_record.id, pr.id, or unique milestone key
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    points: Mapped[int] = mapped_column(Integer, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="point_ledger_entries"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by]
    )
    branch: Mapped["Branch"] = relationship(
        "Branch", foreign_keys=[branch_id]
    )
    organization: Mapped["Organization"] = relationship(
        "Organization", foreign_keys=[organization_id]
    )
