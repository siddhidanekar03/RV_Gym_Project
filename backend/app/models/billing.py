from typing import Optional, List, TYPE_CHECKING
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Boolean, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.user import User
    from backend.app.models.organization import Branch
    from backend.app.models.membership import Enrollment


class InvoiceSequence(Base):
    """Transactional counter for atomic concurrent invoice number generation."""

    __tablename__ = "invoice_sequences"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "INV-2026"
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    current_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Invoice(Base, TimestampMixin):
    """Formal invoice document for membership fees, personal training, or merchandise."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    enrollment_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Status: 'unpaid' | 'partially_paid' | 'paid' | 'void' | 'reversed'
    status: Mapped[str] = mapped_column(String(30), default="unpaid", nullable=False, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    balance_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    branch: Mapped["Branch"] = relationship("Branch", back_populates="invoices")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="invoices")
    enrollment: Mapped[Optional["Enrollment"]] = relationship(
        "Enrollment", back_populates="initial_invoice"
    )
    lines: Mapped[List["InvoiceLine"]] = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="invoice")


class InvoiceLine(Base, TimestampMixin):
    """Line item itemizing specific charges within an invoice."""

    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")


class Payment(Base):
    """
    Immutable ledger of payment events and reversals.
    Once created, rows are immutable. Reversals add a new reversing row.
    """

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Payment Method: 'cash' | 'upi_offline' | 'card_pos' | 'bank_transfer'
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, index=True, nullable=True
    )
    # Status: 'completed' | 'reversed'
    status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversed_payment_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=True
    )
    recorded_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="payments")
    branch: Mapped["Branch"] = relationship("Branch", back_populates="payments")
    user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[user_id], back_populates="payments"
    )
    recorded_by: Mapped["User"] = relationship("User", foreign_keys=[recorded_by_id])
    reversed_payment: Mapped[Optional["Payment"]] = relationship(
        "Payment", remote_side=[id], foreign_keys=[reversed_payment_id]
    )
