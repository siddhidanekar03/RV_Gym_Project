from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple
import threading
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.models.billing import Invoice, InvoiceLine, Payment, InvoiceSequence
from backend.app.models.membership import Enrollment, MembershipPlan
from backend.app.models.user import User
from backend.app.models.audit import AuditLog

# Local lock for SQLite concurrency safety in single-process test runs
_seq_lock = threading.Lock()


def generate_next_invoice_number(db: Session, prefix: str = "INV-2026") -> str:
    """
    Generate sequential, unique invoice numbers with concurrency protection.
    Format: INV-2026-00001
    """
    with _seq_lock:
        seq = (
            db.query(InvoiceSequence)
            .filter(InvoiceSequence.id == prefix)
            .with_for_update()
            .first()
        )
        if not seq:
            seq = InvoiceSequence(id=prefix, prefix=prefix, current_number=0)
            db.add(seq)
            db.flush()

        seq.current_number += 1
        invoice_num = f"{prefix}-{seq.current_number:05d}"
        db.flush()
        return invoice_num


def create_invoice_for_enrollment(
    db: Session,
    enrollment: Enrollment,
    plan: MembershipPlan,
    user_id: Optional[str] = None,
    branch_id: str = "narsobawadi",
    notes: Optional[str] = None,
) -> Invoice:
    """
    Atomically creates an initial invoice and line item for an enrollment application.
    Must be called within an active database transaction.
    """
    current_year = date.today().year
    prefix = f"INV-{current_year}"
    inv_number = generate_next_invoice_number(db, prefix=prefix)

    amount = Decimal(str(plan.price))
    due_date = date.today() + timedelta(days=7)

    invoice = Invoice(
        invoice_number=inv_number,
        user_id=user_id,
        branch_id=branch_id,
        enrollment_id=enrollment.id,
        status="unpaid",
        subtotal=amount,
        tax=Decimal("0.00"),
        total_amount=amount,
        amount_paid=Decimal("0.00"),
        balance_due=amount,
        due_date=due_date,
        notes=notes or f"Initial enrollment invoice for {plan.name} plan.",
    )
    db.add(invoice)
    db.flush()

    line = InvoiceLine(
        invoice_id=invoice.id,
        description=f"{plan.name} Membership ({plan.billing_cycle})",
        quantity=1,
        unit_price=amount,
        amount=amount,
    )
    db.add(line)
    db.flush()

    return invoice


def record_offline_payment(
    db: Session,
    invoice_id: str,
    amount: Decimal,
    payment_method: str,
    recorded_by: User,
    reference_number: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    notes: Optional[str] = None,
) -> Payment:
    """
    Record an immutable offline payment (cash, upi_offline, card_pos, bank_transfer).
    Enforces idempotency, handles partial payments, and updates outstanding balances.
    """
    # 1. Idempotency Check
    if idempotency_key:
        clean_key = idempotency_key.strip()
        existing_payment = (
            db.query(Payment)
            .filter(Payment.idempotency_key == clean_key)
            .first()
        )
        if existing_payment:
            return existing_payment

    # 2. Retrieve target invoice
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).with_for_update().first()
    if not invoice:
        raise ValueError(f"Invoice '{invoice_id}' not found.")

    if invoice.status in ("paid", "void", "reversed"):
        raise ValueError(
            f"Cannot apply payment to invoice with status '{invoice.status}'. Balance due is ₹{invoice.balance_due}."
        )

    # 3. Validation: Amount
    amount = Decimal(str(amount))
    if amount <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")

    if amount > invoice.balance_due:
        raise ValueError(
            f"Payment amount ₹{amount} exceeds outstanding invoice balance of ₹{invoice.balance_due}."
        )

    # 4. Create immutable Payment record
    payment = Payment(
        invoice_id=invoice.id,
        user_id=invoice.user_id,
        branch_id=invoice.branch_id,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference_number,
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
        status="completed",
        is_reversal=False,
        recorded_by_id=recorded_by.id,
        notes=notes,
    )
    db.add(payment)
    db.flush()

    # 5. Update invoice financial tallies
    invoice.amount_paid += amount
    invoice.balance_due -= amount

    if invoice.balance_due == Decimal("0.00"):
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"

    # 6. Audit Trail
    audit = AuditLog(
        actor_id=recorded_by.id,
        action="billing.payment_received",
        resource_type="invoice",
        resource_id=invoice.id,
        details={
            "invoice_number": invoice.invoice_number,
            "payment_id": payment.id,
            "amount": str(amount),
            "method": payment_method,
            "remaining_balance": str(invoice.balance_due),
        },
    )
    db.add(audit)
    db.flush()

    return payment


def reverse_payment(
    db: Session,
    payment_id: str,
    actor: User,
    reason: str,
) -> Payment:
    """
    Authorized payment reversal.
    Creates an immutable reversing entry, restores invoice balance, and updates status.
    Only permitted for Organization Admins and Branch Managers.
    """
    # 1. Authorization Check
    authorized_roles = {"org_admin", "admin", "branch_manager", "manager"}
    if actor.role not in authorized_roles:
        raise PermissionError(
            "Access denied: Payment reversals require Organization Admin or Branch Manager authorization."
        )

    # 2. Retrieve original payment
    original = db.query(Payment).filter(Payment.id == payment_id).first()
    if not original:
        raise ValueError(f"Payment record '{payment_id}' not found.")

    if original.is_reversal:
        raise ValueError("Cannot reverse a reversal transaction.")

    if original.status == "reversed":
        raise ValueError("Payment has already been reversed.")

    invoice = db.query(Invoice).filter(Invoice.id == original.invoice_id).with_for_update().first()
    if not invoice:
        raise ValueError(f"Associated invoice '{original.invoice_id}' not found.")

    # 3. Create immutable reversing Payment row
    reversal = Payment(
        invoice_id=invoice.id,
        user_id=original.user_id,
        branch_id=original.branch_id,
        amount=-original.amount,
        payment_method=original.payment_method,
        reference_number=f"REV-{original.id[:8]}",
        status="reversed",
        is_reversal=True,
        reversed_payment_id=original.id,
        recorded_by_id=actor.id,
        notes=f"Reversal authorized by {actor.name}. Reason: {reason}",
    )
    original.status = "reversed"
    db.add(reversal)
    db.flush()

    # 4. Restore invoice balance
    invoice.amount_paid -= original.amount
    invoice.balance_due += original.amount

    if invoice.amount_paid == Decimal("0.00"):
        invoice.status = "unpaid"
    else:
        invoice.status = "partially_paid"

    # 5. Audit Trail
    audit = AuditLog(
        actor_id=actor.id,
        action="billing.payment_reversed",
        resource_type="payment",
        resource_id=original.id,
        details={
            "invoice_id": invoice.id,
            "reversed_amount": str(original.amount),
            "restored_balance": str(invoice.balance_due),
            "reason": reason,
        },
    )
    db.add(audit)
    db.flush()

    return reversal
