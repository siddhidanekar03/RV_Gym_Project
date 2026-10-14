from typing import Optional, List, TYPE_CHECKING
from datetime import date
from sqlalchemy import String, Boolean, Date, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.attendance import AttendanceRecord
    from backend.app.models.billing import Invoice, Payment


class Organization(Base, TimestampMixin):
    """Top-level enterprise tenant representing gym brand or entity."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    branches: Mapped[List["Branch"]] = relationship(
        "Branch", back_populates="organization", cascade="all, delete-orphan"
    )


class Branch(Base, TimestampMixin):
    """Physical branch facility within an organization."""

    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), default="Narsobawadi", nullable=False)
    state: Mapped[str] = mapped_column(String(100), default="Maharashtra", nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="branches")
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="branch", foreign_keys="User.branch_id"
    )
    attendance_records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="branch", foreign_keys="AttendanceRecord.branch_id"
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice", back_populates="branch", foreign_keys="Invoice.branch_id"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="branch", foreign_keys="Payment.branch_id"
    )


class MemberBranchAccess(Base, TimestampMixin):
    """
    Explicit cross-branch access authorization grant for a member.
    Enables access to additional branches beyond the home branch.
    """

    __tablename__ = "member_branch_access"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    expires_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="branch_access_grants")
    branch: Mapped["Branch"] = relationship("Branch")
