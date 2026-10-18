import io
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
            # Enforce payload consistency: key reuse with different parameters must be rejected
            if (
                existing_payment.invoice_id != invoice_id
                or existing_payment.amount != amount
                or existing_payment.payment_method != payment_method
            ):
                raise ValueError(
                    f"Idempotency key '{clean_key}' was previously used with a different payment payload."
                )
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
        if invoice.enrollment_id:
            from backend.app.services.membership_service import activate_enrollment_from_paid_invoice
            activate_enrollment_from_paid_invoice(db, invoice)
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

    # Branch isolation: if not org_admin or admin, manager must belong to payment branch
    if actor.role not in {"org_admin", "admin"}:
        if actor.branch_id and original.branch_id and actor.branch_id != original.branch_id:
            raise PermissionError(
                f"Access denied: Branch manager authorized for '{actor.branch_id}' cannot reverse payment for branch '{original.branch_id}'."
            )

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


def generate_invoice_pdf(invoice: Invoice, db: Session) -> bytes:
    """
    Generate an official RVFitness tax invoice PDF using ReportLab.
    Enforces black-and-gold visual aesthetic, complete financial tally,
    and verifiable payment breakdown.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    # Brand aesthetic tokens
    gold = colors.HexColor("#d4af37")
    dark_bg = colors.HexColor("#08090b")
    card_bg = colors.HexColor("#11141a")
    border_color = colors.HexColor("#2a2e39")
    text_light = colors.HexColor("#f8fafc")
    text_muted = colors.HexColor("#94a3b8")
    status_paid = colors.HexColor("#22c55e")
    status_unpaid = colors.HexColor("#ef4444")

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=gold,
    )
    subtitle_style = ParagraphStyle(
        "InvoiceSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=text_muted,
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=gold,
    )
    meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=text_light,
    )
    table_head = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=gold,
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=text_light,
    )

    story = []

    # Header
    story.append(Paragraph("RV FITNESS CLUB · OFFICIAL INVOICE", title_style))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph("Elite Strength & Conditioning | Narsobawadi & Sangli Centers", subtitle_style)
    )
    story.append(Spacer(1, 14))

    # Invoice Metadata Grid
    user = invoice.user
    member_name = user.name if user else "Walk-in Guest"
    member_email = user.email if user else "N/A"
    member_phone = user.phone if user else "N/A"
    membership_id = user.membership_id if user else "N/A"

    status_color = status_paid if invoice.status == "paid" else status_unpaid
    status_text = f"<font color='{status_color.hexval()}'><b>{invoice.status.upper()}</b></font>"

    info_data = [
        [
            Paragraph("<b>Invoice Number:</b>", meta_label),
            Paragraph(invoice.invoice_number, meta_val),
            Paragraph("<b>Status:</b>", meta_label),
            Paragraph(status_text, meta_val),
        ],
        [
            Paragraph("<b>Issue Date:</b>", meta_label),
            Paragraph(invoice.created_at.strftime("%Y-%m-%d"), meta_val),
            Paragraph("<b>Due Date:</b>", meta_label),
            Paragraph(invoice.due_date.strftime("%Y-%m-%d") if invoice.due_date else "Upon Receipt", meta_val),
        ],
        [
            Paragraph("<b>Billed To:</b>", meta_label),
            Paragraph(f"{member_name} ({membership_id})", meta_val),
            Paragraph("<b>Branch:</b>", meta_label),
            Paragraph(invoice.branch_id.capitalize(), meta_val),
        ],
        [
            Paragraph("<b>Contact:</b>", meta_label),
            Paragraph(f"{member_phone} | {member_email}", meta_val),
            Paragraph("<b>Payment Terms:</b>", meta_label),
            Paragraph("Immediate / Advance Subscription", meta_val),
        ],
    ]

    info_table = Table(info_data, colWidths=[100, 170, 90, 180])
    info_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), card_bg),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(info_table)
    story.append(Spacer(1, 16))

    # Line Items Table
    lines = invoice.lines or []
    item_rows = [
        [
            Paragraph("<b>Item Description</b>", table_head),
            Paragraph("<b>Qty</b>", table_head),
            Paragraph("<b>Unit Price (INR)</b>", table_head),
            Paragraph("<b>Amount (INR)</b>", table_head),
        ]
    ]

    for line in lines:
        item_rows.append([
            Paragraph(line.description, table_cell),
            Paragraph(str(line.quantity), table_cell),
            Paragraph(f"{line.unit_price:.2f}", table_cell),
            Paragraph(f"{line.amount:.2f}", table_cell),
        ])

    items_table = Table(item_rows, colWidths=[280, 50, 105, 105])
    items_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), card_bg),
            ("BACKGROUND", (0, 1), (-1, -1), dark_bg),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(items_table)
    story.append(Spacer(1, 14))

    # Totals Summary Table
    totals_data = [
        [Paragraph("Subtotal:", meta_label), Paragraph(f"INR {invoice.subtotal:.2f}", meta_val)],
        [Paragraph("Tax (GST Exempt / Composite):", meta_label), Paragraph(f"INR {invoice.tax:.2f}", meta_val)],
        [Paragraph("<b>Total Amount:</b>", meta_label), Paragraph(f"<b>INR {invoice.total_amount:.2f}</b>", meta_val)],
        [Paragraph("Amount Paid:", meta_label), Paragraph(f"INR {invoice.amount_paid:.2f}", meta_val)],
        [Paragraph("<b>Balance Due:</b>", meta_label), Paragraph(f"<b>INR {invoice.balance_due:.2f}</b>", meta_val)],
    ]
    totals_table = Table(totals_data, colWidths=[200, 120])
    totals_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), card_bg),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ])
    )

    # Wrap Totals in an outer aligned block
    wrapper_table = Table([["", totals_table]], colWidths=[220, 320])
    wrapper_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(wrapper_table)
    story.append(Spacer(1, 16))

    # Payment Records History Table (if any)
    payments = [p for p in (invoice.payments or []) if not p.is_reversal]
    if payments:
        story.append(Paragraph("<b>Recorded Payment Receipts:</b>", meta_label))
        story.append(Spacer(1, 6))
        pay_rows = [
            [
                Paragraph("<b>Payment ID</b>", table_head),
                Paragraph("<b>Date</b>", table_head),
                Paragraph("<b>Method</b>", table_head),
                Paragraph("<b>Ref #</b>", table_head),
                Paragraph("<b>Amount (INR)</b>", table_head),
            ]
        ]
        for p in payments:
            pay_rows.append([
                Paragraph(p.id[:10], table_cell),
                Paragraph(p.created_at.strftime("%Y-%m-%d %H:%M"), table_cell),
                Paragraph(p.payment_method.upper(), table_cell),
                Paragraph(p.reference_number or "-", table_cell),
                Paragraph(f"{p.amount:.2f}", table_cell),
            ])
        pay_table = Table(pay_rows, colWidths=[100, 110, 100, 130, 100])
        pay_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), card_bg),
                ("BACKGROUND", (0, 1), (-1, -1), dark_bg),
                ("BOX", (0, 0), (-1, -1), 1, border_color),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(pay_table)
        story.append(Spacer(1, 14))

    # Notes & Disclaimer Footer
    footer_text = (
        "Thank you for choosing RV Fitness. This is a computer-generated tax invoice and requires no physical signature. "
        "All subscription sales are final per gym membership regulations."
    )
    story.append(Paragraph(footer_text, subtitle_style))

    doc.build(story)
    return buffer.getvalue()

