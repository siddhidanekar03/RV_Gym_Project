from typing import Optional, TYPE_CHECKING
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.organization import Branch


class AttendanceRecord(Base, TimestampMixin):
    """
    Daily gym floor attendance record.
    Enforces atomic uniqueness per member per day to prevent duplicate check-ins.
    Tracks branch location where check-in occurred.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("user_id", "check_in_date", name="uq_user_attendance_daily"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id"), default="narsobawadi", nullable=False, index=True
    )
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Check-in channel: 'portal' | 'rfid' | 'desk'
    method: Mapped[str] = mapped_column(String(30), default="portal", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="attendance_records")
    branch: Mapped[Optional["Branch"]] = relationship(
        "Branch",
        back_populates="attendance_records",
        foreign_keys=[branch_id],
        primaryjoin="AttendanceRecord.branch_id == Branch.id",
    )
