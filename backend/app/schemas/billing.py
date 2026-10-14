from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel, Field


class InvoiceLineItem(BaseModel):
    id: str
    description: str
    quantity: int
    unitPrice: float
    amount: float


class InvoiceDetail(BaseModel):
    id: str
    invoiceNumber: str
    userId: Optional[str] = None
    branchId: str
    status: str
    subtotal: float
    tax: float
    totalAmount: float
    amountPaid: float
    balanceDue: float
    dueDate: str
    lines: List[InvoiceLineItem] = []


class InvoiceListResponse(BaseModel):
    invoices: List[InvoiceDetail]


class PaymentSubmissionRequest(BaseModel):
    invoiceId: str
    amount: float = Field(..., gt=0)
    paymentMethod: str = Field(..., description="cash | upi_offline | card_pos | bank_transfer")
    referenceNumber: Optional[str] = None
    idempotencyKey: Optional[str] = None
    notes: Optional[str] = None


class PaymentReceipt(BaseModel):
    id: str
    invoiceId: str
    amount: float
    paymentMethod: str
    referenceNumber: Optional[str] = None
    idempotencyKey: Optional[str] = None
    status: str
    isReversal: bool
    createdAt: str


class PaymentSubmissionResponse(BaseModel):
    success: bool
    message: str
    payment: PaymentReceipt
    remainingBalance: float


class PaymentReversalRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class PaymentReversalResponse(BaseModel):
    success: bool
    message: str
    reversalPaymentId: str
    restoredBalance: float
