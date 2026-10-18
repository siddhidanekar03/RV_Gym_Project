from typing import Optional, List, TYPE_CHECKING
from datetime import date, datetime
from sqlalchemy import (
    String,
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
    from backend.app.models.organization import Branch


def default_member_identity(context) -> str:
    """Fallback generator for canonical member_identity when not provided."""
    params = context.get_current_parameters() if context else {}
    user_id = params.get("user_id")
    if user_id:
        return f"user:{user_id}"
    mem_id = params.get("membership_id")
    if mem_id:
        return f"member:{str(mem_id).strip().upper()}"
    phone = params.get("member_phone")
    name = params.get("member_name")
    if phone:
        digits = "".join(c for c in str(phone) if c.isdigit())
        phone_key = digits[-10:] if len(digits) >= 10 else digits
        if name and str(name).strip():
            norm_name = "_".join(str(name).strip().lower().split())
            return f"phone:{phone_key}:{norm_name}"
        return f"phone:{phone_key}"
    rec_id = params.get("id") or generate_uuid()
    return f"anon:{rec_id}"


class AttendanceRecord(Base, TimestampMixin):
    """
    Daily gym floor attendance record.
    Enforces atomic uniqueness per member, branch, and branch-local calendar date
    to prevent duplicate check-ins.
    Tracks check-in source (qr, manual, override, backfill) and audit metadata.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "branch_id",
            "check_in_date",
            name="uq_user_branch_attendance_daily",
        ),
        UniqueConstraint(
            "member_identity",
            "branch_id",
            "check_in_date",
            name="uq_member_branch_attendance_daily",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # Canonical non-null member identity string (e.g. 'user:<id>', 'member:<card_id>', 'phone:<digits>:<name>')
    # Guarantees database-enforced daily attendance uniqueness across both registered users and walk-in members.
    member_identity: Mapped[str] = mapped_column(
        String(100), default=default_member_identity, nullable=False, index=True
    )

    def __init__(self, **kwargs):
        if "member_identity" not in kwargs or not kwargs["member_identity"]:
            user_id = kwargs.get("user_id")
            membership_id = kwargs.get("membership_id")
            member_phone = kwargs.get("member_phone")
            member_name = kwargs.get("member_name")
            if user_id:
                kwargs["member_identity"] = f"user:{user_id}"
            elif membership_id:
                kwargs["member_identity"] = f"member:{str(membership_id).strip().upper()}"
            elif member_phone:
                digits = "".join(c for c in str(member_phone) if c.isdigit())
                phone_key = digits[-10:] if len(digits) >= 10 else digits
                if member_name and str(member_name).strip():
                    norm_name = "_".join(str(member_name).strip().lower().split())
                    kwargs["member_identity"] = f"phone:{phone_key}:{norm_name}"
                else:
                    kwargs["member_identity"] = f"phone:{phone_key}"
            else:
                kwargs["member_identity"] = f"anon:{generate_uuid()}"
        super().__init__(**kwargs)

    # user_id is nullable to permit desk check-in for members without web portal accounts
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id"), default="narsobawadi", nullable=False, index=True
    )
    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Check-in channel/source: 'qr' | 'manual' | 'override' | 'backfill' | 'portal'
    source: Mapped[str] = mapped_column(String(30), default="portal", nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(30), default="portal", nullable=False)

    # Manual check-in reason code: 'no_account' | 'no_internet' | 'qr_invalid' | 'other'
    manual_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Staff member who facilitated or verified the attendance
    staff_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Backfill tracking for desk power/internet outages
    is_backfill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backfill_operator_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    backfill_entry_operator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    backfill_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # For desk check-ins of members who have not yet created a web portal account
    member_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    member_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    membership_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[user_id], back_populates="attendance_records"
    )
    staff: Mapped[Optional["User"]] = relationship("User", foreign_keys=[staff_id])
    backfill_operator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[backfill_operator_id])
    branch: Mapped[Optional["Branch"]] = relationship(
        "Branch",
        back_populates="attendance_records",
        foreign_keys=[branch_id],
        primaryjoin="AttendanceRecord.branch_id == Branch.id",
    )


class AttendanceAttempt(Base):
    """
    Append-only log of unsuccessful check-in attempts, QR failures,
    and subsequent manager overrides.
    Rejected attempts do not block subsequent valid check-ins on the same day.
    """

    __tablename__ = "attendance_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    member_identity: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    membership_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    member_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    member_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Source: 'qr' | 'manual' | 'portal' | 'desk'
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # Failure reason: 'expired_membership' | 'frozen_membership' | 'cancelled_membership'
    # | 'branch_ineligible' | 'qr_expired' | 'qr_replay' | 'unpaid_dues' | 'already_checked_in'
    # | 'user_not_found' | 'invalid_payload'
    failure_reason: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    failure_detail: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    staff_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Manager Override tracking (never deletes original attempt)
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    overridden_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    override_attendance_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("attendance_records.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    branch: Mapped[Optional["Branch"]] = relationship("Branch", foreign_keys=[branch_id])
    staff: Mapped[Optional["User"]] = relationship("User", foreign_keys=[staff_id])
    overridden_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[overridden_by_id])
    override_attendance: Mapped[Optional["AttendanceRecord"]] = relationship(
        "AttendanceRecord", foreign_keys=[override_attendance_id]
    )


class ConsumedQRToken(Base):
    """
    Nonce ledger preventing replay attacks on short-lived QR check-in tokens.
    Consumed nonces are inserted with conflict detection and pruned once expired.
    """

    __tablename__ = "consumed_qr_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
