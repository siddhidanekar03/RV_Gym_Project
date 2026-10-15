from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles, require_csrf, verify_branch_access
from backend.app.models.user import User
from backend.app.models.billing import Invoice, Payment
from backend.app.services.billing_service import record_offline_payment, reverse_payment, generate_invoice_pdf
from backend.app.schemas.billing import (
    InvoiceDetail,
    InvoiceLineItem,
    InvoiceListResponse,
    PaymentSubmissionRequest,
    PaymentSubmissionResponse,
    PaymentReceipt,
    PaymentReversalRequest,
    PaymentReversalResponse,
)

router = APIRouter()


def _format_invoice(invoice: Invoice) -> InvoiceDetail:
    lines = [
        InvoiceLineItem(
            id=line.id,
            description=line.description,
            quantity=line.quantity,
            unitPrice=float(line.unit_price),
            amount=float(line.amount),
        )
        for line in invoice.lines
    ]
    return InvoiceDetail(
        id=invoice.id,
        invoiceNumber=invoice.invoice_number,
        userId=invoice.user_id,
        branchId=invoice.branch_id,
        status=invoice.status,
        subtotal=float(invoice.subtotal),
        tax=float(invoice.tax),
        totalAmount=float(invoice.total_amount),
        amountPaid=float(invoice.amount_paid),
        balanceDue=float(invoice.balance_due),
        dueDate=invoice.due_date.isoformat(),
        lines=lines,
    )


@router.get(
    "/billing/invoices",
    response_model=InvoiceListResponse,
    summary="List Invoices with Role & Branch Scoping",
)
def list_invoices(
    branch_id: Optional[str] = Query(None, description="Optional branch filter for staff/managers"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceListResponse:
    query = db.query(Invoice)

    if user.role == "member":
        # Member isolation: only view their own invoices
        query = query.filter(Invoice.user_id == user.id)
    elif user.role in ("branch_manager", "manager", "front_desk", "staff"):
        # Branch-scoped isolation
        target_branch = branch_id or user.branch_id
        verify_branch_access(user, target_branch)
        query = query.filter(Invoice.branch_id == target_branch)
    elif user.role in ("org_admin", "admin"):
        # Organization Admin: can filter or view all
        if branch_id:
            query = query.filter(Invoice.branch_id == branch_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    invoices = query.order_by(Invoice.created_at.desc()).all()
    return InvoiceListResponse(invoices=[_format_invoice(i) for i in invoices])


@router.get(
    "/billing/invoices/{invoice_id}",
    response_model=InvoiceDetail,
    summary="Retrieve Single Invoice by ID",
)
def get_invoice(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceDetail:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    # Authorization enforcement
    if user.role == "member" and invoice.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only view invoices issued to your account.",
        )
    if user.role in ("branch_manager", "manager", "front_desk", "staff"):
        verify_branch_access(user, invoice.branch_id)

    return _format_invoice(invoice)


@router.get(
    "/billing/invoices/{invoice_id}/pdf",
    summary="Download Official Invoice PDF",
    description="Generate and download a branded PDF tax invoice with branch and owner authorization.",
)
def download_invoice_pdf(
    invoice_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    if user.role == "member" and invoice.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only view invoices issued to your account.",
        )
    if user.role in ("branch_manager", "manager", "front_desk", "staff"):
        verify_branch_access(user, invoice.branch_id)

    pdf_bytes = generate_invoice_pdf(invoice, db)
    filename = f"RVFitness_Invoice_{invoice.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.post(
    "/billing/payments",
    response_model=PaymentSubmissionResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff"))],
    summary="Submit Offline Payment for Invoice",
)
def submit_payment(
    payload: PaymentSubmissionRequest,
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentSubmissionResponse:
    invoice = db.query(Invoice).filter(Invoice.id == payload.invoiceId).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target invoice not found.")

    verify_branch_access(user, invoice.branch_id)

    key = (idempotency_key_header or payload.idempotencyKey or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key is required on payment submissions.",
        )

    try:
        payment = record_offline_payment(
            db=db,
            invoice_id=payload.invoiceId,
            amount=Decimal(str(payload.amount)),
            payment_method=payload.paymentMethod,
            recorded_by=user,
            reference_number=payload.referenceNumber,
            idempotency_key=key,
            notes=payload.notes,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Handle concurrent race: look up existing payment inserted by competing transaction
        existing = db.query(Payment).filter(Payment.idempotency_key == key).first()
        if existing:
            if (
                existing.invoice_id != payload.invoiceId
                or existing.amount != Decimal(str(payload.amount))
                or existing.payment_method != payload.paymentMethod
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Idempotency key '{key}' was previously used with a different payment payload.",
                )
            payment = existing
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Data integrity collision on payment submission.")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Payment processing failed.")

    db.refresh(invoice)
    receipt = PaymentReceipt(
        id=payment.id,
        invoiceId=payment.invoice_id,
        amount=float(payment.amount),
        paymentMethod=payment.payment_method,
        referenceNumber=payment.reference_number,
        idempotencyKey=payment.idempotency_key,
        status=payment.status,
        isReversal=payment.is_reversal,
        createdAt=payment.created_at.isoformat(),
    )

    return PaymentSubmissionResponse(
        success=True,
        message=f"Payment of ₹{payment.amount} recorded successfully. Invoice status is now '{invoice.status}'.",
        payment=receipt,
        remainingBalance=float(invoice.balance_due),
    )


@router.post(
    "/billing/payments/{payment_id}/reverse",
    response_model=PaymentReversalResponse,
    dependencies=[Depends(require_csrf), Depends(require_roles("org_admin", "admin", "branch_manager", "manager"))],
    summary="Reverse Payment with Supervisory Authorization",
)
def handle_reversal(
    payment_id: str,
    payload: PaymentReversalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaymentReversalResponse:
    target_payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not target_payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")

    verify_branch_access(user, target_payment.branch_id)

    try:
        reversal = reverse_payment(
            db=db,
            payment_id=payment_id,
            actor=user,
            reason=payload.reason,
        )
        db.commit()
    except PermissionError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Reversal processing failed.")

    invoice = db.query(Invoice).filter(Invoice.id == reversal.invoice_id).first()

    return PaymentReversalResponse(
        success=True,
        message=f"Payment reversal processed successfully. Invoice balance restored to ₹{invoice.balance_due if invoice else 0.0}.",
        reversalPaymentId=reversal.id,
        restoredBalance=float(invoice.balance_due) if invoice else 0.0,
    )
