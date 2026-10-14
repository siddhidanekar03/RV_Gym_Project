import concurrent.futures
from decimal import Decimal
from datetime import date, timedelta
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.models.organization import Organization, Branch
from backend.app.models.membership import MembershipPlan, Enrollment
from backend.app.models.billing import Invoice, Payment
from backend.app.services.billing_service import (
    generate_next_invoice_number,
    create_invoice_for_enrollment,
    record_offline_payment,
    reverse_payment,
)
from backend.app.core.security import hash_password
from backend.app.core.auth import create_user_session


def _ensure_default_org_branch(db: Session) -> Branch:
    org = db.query(Organization).filter(Organization.code == "RVF").first()
    if not org:
        org = Organization(name="RV Fitness", code="RVF", is_active=True)
        db.add(org)
        db.flush()

    branch = db.query(Branch).filter(Branch.id == "narsobawadi").first()
    if not branch:
        branch = Branch(
            id="narsobawadi",
            organization_id=org.id,
            name="Narsobawadi Main Campus",
            code="narsobawadi",
            is_active=True,
        )
        db.add(branch)
        db.flush()
    return branch


def test_concurrent_invoice_numbering(db_session: Session):
    """
    Verify invoice numbering generates strictly unique, sequential numbers
    under concurrent generation calls without collisions.
    """
    _ensure_default_org_branch(db_session)
    prefix = "INV-CONCUR"

    generated_numbers = []

    def generate_one():
        return generate_next_invoice_number(db_session, prefix=prefix)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(generate_one) for _ in range(25)]
        for f in concurrent.futures.as_completed(futures):
            generated_numbers.append(f.result())

    # All generated numbers must be distinct
    assert len(generated_numbers) == 25
    assert len(set(generated_numbers)) == 25

    # Check formatting and continuous sequence range
    seq_ints = sorted([int(num.split("-")[-1]) for num in generated_numbers])
    assert seq_ints == list(range(1, 26))


def test_atomic_enrollment_and_initial_invoice(client: TestClient, db_session: Session):
    """
    Verify submitting an enrollment creates both the enrollment record
    and its initial invoice atomically in the database.
    """
    _ensure_default_org_branch(db_session)
    plan = MembershipPlan(
        id="test_plan_quarterly",
        name="Quarterly Test",
        price=Decimal("4000.00"),
        currency="₹",
        billing_cycle="3 months",
        duration_days=90,
        is_active=True,
        perks=["Floor access"],
    )
    db_session.add(plan)
    db_session.commit()

    resp = client.post(
        "/api/memberships/enroll",
        json={
            "planId": "test_plan_quarterly",
            "name": "Prathamesh Kulkarni",
            "phone": "+91 98220 99999",
            "email": "prathamesh.k@example.com",
            "acceptedTerms": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["enrollment"]["invoiceId"] is not None
    assert data["enrollment"]["invoiceNumber"] is not None

    # Verify both records persist in the database
    enrollment = db_session.query(Enrollment).filter(Enrollment.id == data["enrollment"]["id"]).first()
    assert enrollment is not None
    assert enrollment.price == Decimal("4000.00")

    invoice = db_session.query(Invoice).filter(Invoice.id == data["enrollment"]["invoiceId"]).first()
    assert invoice is not None
    assert invoice.enrollment_id == enrollment.id
    assert invoice.total_amount == Decimal("4000.00")
    assert invoice.balance_due == Decimal("4000.00")
    assert invoice.amount_paid == Decimal("0.00")
    assert invoice.status == "unpaid"
    assert len(invoice.lines) == 1
    assert invoice.lines[0].amount == Decimal("4000.00")


def test_offline_payments_and_partial_payments(db_session: Session):
    """
    Verify offline payment recording, partial payments, balance reduction,
    and prevention of overpayment.
    """
    branch = _ensure_default_org_branch(db_session)
    staff = User(
        email="desk@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Front Desk Staff",
        role="front_desk",
        branch_id=branch.id,
    )
    db_session.add(staff)
    db_session.flush()

    invoice = Invoice(
        invoice_number="INV-TEST-001",
        branch_id=branch.id,
        status="unpaid",
        subtotal=Decimal("4000.00"),
        total_amount=Decimal("4000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("4000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.commit()

    # 1. Partial payment of 1500
    p1 = record_offline_payment(
        db=db_session,
        invoice_id=invoice.id,
        amount=Decimal("1500.00"),
        payment_method="cash",
        recorded_by=staff,
    )
    db_session.commit()

    db_session.refresh(invoice)
    assert invoice.amount_paid == Decimal("1500.00")
    assert invoice.balance_due == Decimal("2500.00")
    assert invoice.status == "partially_paid"
    assert p1.status == "completed"

    # 2. Overpayment attempt should fail
    with pytest.raises(ValueError, match="exceeds outstanding invoice balance"):
        record_offline_payment(
            db=db_session,
            invoice_id=invoice.id,
            amount=Decimal("3000.00"),  # Only 2500 remaining
            payment_method="upi_offline",
            recorded_by=staff,
        )

    # 3. Final payment of 2500
    p2 = record_offline_payment(
        db=db_session,
        invoice_id=invoice.id,
        amount=Decimal("2500.00"),
        payment_method="upi_offline",
        recorded_by=staff,
    )
    db_session.commit()

    db_session.refresh(invoice)
    assert invoice.amount_paid == Decimal("4000.00")
    assert invoice.balance_due == Decimal("0.00")
    assert invoice.status == "paid"


def test_payment_idempotency(db_session: Session):
    """
    Verify submitting a payment with the same idempotency key
    returns the existing record and does not double-charge or double-credit.
    """
    branch = _ensure_default_org_branch(db_session)
    staff = User(
        email="desk2@rvfitness.in",
        hashed_password=hash_password("StaffPass123"),
        name="Front Desk Staff 2",
        role="front_desk",
        branch_id=branch.id,
    )
    db_session.add(staff)
    db_session.flush()

    invoice = Invoice(
        invoice_number="INV-IDEMP-001",
        branch_id=branch.id,
        status="unpaid",
        subtotal=Decimal("4000.00"),
        total_amount=Decimal("4000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("4000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.commit()

    idempotency_key = "idemp_trans_xyz_123"

    # First submission
    p1 = record_offline_payment(
        db=db_session,
        invoice_id=invoice.id,
        amount=Decimal("2000.00"),
        payment_method="card_pos",
        recorded_by=staff,
        idempotency_key=idempotency_key,
    )
    db_session.commit()

    # Second submission with the exact same key
    p2 = record_offline_payment(
        db=db_session,
        invoice_id=invoice.id,
        amount=Decimal("2000.00"),
        payment_method="card_pos",
        recorded_by=staff,
        idempotency_key=idempotency_key,
    )

    assert p1.id == p2.id
    db_session.refresh(invoice)
    # Balance should only have been deducted once!
    assert invoice.amount_paid == Decimal("2000.00")
    assert invoice.balance_due == Decimal("2000.00")


def test_authorized_payment_reversal(db_session: Session):
    """
    Verify payment reversals require manager/admin authorization,
    create immutable reversing entries, and restore invoice balance.
    """
    branch = _ensure_default_org_branch(db_session)
    admin = User(
        email="manager@rvfitness.in",
        hashed_password=hash_password("ManagerPass123"),
        name="Branch Manager",
        role="branch_manager",
        branch_id=branch.id,
    )
    member = User(
        email="member_rev@rvfitness.in",
        hashed_password=hash_password("MemberPass123"),
        name="Member User",
        role="member",
        branch_id=branch.id,
    )
    db_session.add_all([admin, member])
    db_session.flush()

    invoice = Invoice(
        invoice_number="INV-REV-001",
        branch_id=branch.id,
        user_id=member.id,
        status="unpaid",
        subtotal=Decimal("3000.00"),
        total_amount=Decimal("3000.00"),
        amount_paid=Decimal("0.00"),
        balance_due=Decimal("3000.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice)
    db_session.flush()

    payment = record_offline_payment(
        db=db_session,
        invoice_id=invoice.id,
        amount=Decimal("3000.00"),
        payment_method="cash",
        recorded_by=admin,
    )
    db_session.commit()

    # Unauthorized user (member) attempting reversal
    with pytest.raises(PermissionError, match="require Organization Admin or Branch Manager authorization"):
        reverse_payment(
            db=db_session,
            payment_id=payment.id,
            actor=member,
            reason="Unpermitted member attempt",
        )

    # Authorized manager reversal
    reversal = reverse_payment(
        db=db_session,
        payment_id=payment.id,
        actor=admin,
        reason="Mistaken duplicate cash receipt",
    )
    db_session.commit()

    assert reversal.is_reversal is True
    assert reversal.amount == Decimal("-3000.00")
    assert reversal.reversed_payment_id == payment.id

    db_session.refresh(invoice)
    db_session.refresh(payment)
    assert payment.status == "reversed"
    assert invoice.amount_paid == Decimal("0.00")
    assert invoice.balance_due == Decimal("3000.00")
    assert invoice.status == "unpaid"

    # Attempting to reverse again should fail
    with pytest.raises(ValueError, match="Payment has already been reversed"):
        reverse_payment(
            db=db_session,
            payment_id=payment.id,
            actor=admin,
            reason="Second reversal attempt",
        )
