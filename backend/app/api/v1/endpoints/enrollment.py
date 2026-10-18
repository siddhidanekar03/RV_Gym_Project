from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.core.rate_limit import rate_limit
from backend.app.core.auth import get_current_user, get_current_user_optional
from backend.app.models.membership import MembershipPlan, Enrollment
from backend.app.models.organization import Branch
from backend.app.models.user import User
from backend.app.models.audit import AuditLog
from backend.app.services.billing_service import create_invoice_for_enrollment
from backend.app.schemas.membership import (
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentDetail,
    MyEnrollmentResponse,
)

router = APIRouter()


def build_enrollment_detail(enrollment: Enrollment, db: Session) -> EnrollmentDetail:
    """Helper to construct rich EnrollmentDetail with branch and invoice info."""
    plan = enrollment.plan or db.query(MembershipPlan).filter(MembershipPlan.id == enrollment.plan_id).first()
    branch = db.query(Branch).filter(Branch.id == enrollment.branch_id).first()
    invoice = enrollment.initial_invoice

    return EnrollmentDetail(
        id=enrollment.id,
        userId=enrollment.user_id,
        planId=enrollment.plan_id,
        planName=plan.name if plan else "Membership Plan",
        durationDays=plan.duration_days if plan else 30,
        branchId=enrollment.branch_id,
        branchName=branch.name if branch else "Narsobawadi Main Campus",
        price=int(enrollment.price),
        currency=enrollment.currency,
        name=enrollment.name,
        phone=enrollment.phone,
        email=enrollment.email or "",
        status=enrollment.status,
        enrolledAt=enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else "",
        verifiedAt=enrollment.verified_at.isoformat() if enrollment.verified_at else None,
        verifiedBy=enrollment.verified_by.name if enrollment.verified_by else None,
        rejectionReason=enrollment.rejection_reason,
        notes=enrollment.notes,
        invoiceId=invoice.id if invoice else None,
        invoiceNumber=invoice.invoice_number if invoice else None,
        invoiceStatus=invoice.status if invoice else "unpaid",
        totalAmount=float(invoice.total_amount) if invoice else float(enrollment.price),
        amountPaid=float(invoice.amount_paid) if invoice else 0.0,
        balanceDue=float(invoice.balance_due) if invoice else float(enrollment.price),
    )


@router.post(
    "/memberships/enroll",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
    summary="Submit Membership Enrollment Application",
)
def enroll_member(
    payload: EnrollmentRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> EnrollmentResponse:
    if not payload.acceptedTerms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the Terms & Conditions and Privacy Policy to enroll.",
        )

    clean_name = payload.name.strip()
    clean_phone = payload.phone.strip()

    if len(clean_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide your full legal name.",
        )

    if len(clean_phone) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid contact phone number.",
        )

    plan = (
        db.query(MembershipPlan)
        .filter(MembershipPlan.id == payload.planId, MembershipPlan.is_active == True)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Selected membership plan not found or currently unavailable.",
        )

    clean_email = (payload.email or "").strip().lower() or (current_user.email if current_user else None)

    # Associate user
    user = current_user
    if not user and clean_email:
        user = db.query(User).filter(func.lower(User.email) == clean_email).first()

    branch_id = (payload.branchId or "").strip() or (user.branch_id if user and user.branch_id else "narsobawadi")

    # 1. Atomic Transaction: Create Enrollment and Initial Invoice together
    enrollment = Enrollment(
        plan_id=plan.id,
        user_id=user.id if user else None,
        branch_id=branch_id,
        name=clean_name,
        phone=clean_phone,
        email=clean_email,
        price=plan.price,
        currency=plan.currency,
        status="pending_verification",
        accepted_terms=True,
    )
    db.add(enrollment)
    db.flush()

    # 2. Create Initial Invoice in the same transaction
    invoice = create_invoice_for_enrollment(
        db=db,
        enrollment=enrollment,
        plan=plan,
        user_id=user.id if user else None,
        branch_id=enrollment.branch_id,
    )

    # 3. Audit trail
    audit = AuditLog(
        actor_id=user.id if user else None,
        action="enrollment.created",
        resource_type="enrollment",
        resource_id=enrollment.id,
        details={
            "plan_id": plan.id,
            "plan_name": plan.name,
            "amount": str(plan.price),
            "applicant": clean_name,
            "invoice_number": invoice.invoice_number,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()
    db.refresh(enrollment)

    detail = build_enrollment_detail(enrollment, db)

    return EnrollmentResponse(
        success=True,
        message=f"Enrollment submitted for {plan.name} plan! Please visit the gym desk to activate your RFID membership card.",
        enrollment=detail,
    )


@router.get(
    "/memberships/my-enrollment",
    response_model=MyEnrollmentResponse,
    summary="Get Current Member Latest Enrollment Application",
)
def get_my_enrollment(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyEnrollmentResponse:
    """Retrieve the logged-in member's most recent membership application."""
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user.id)
        .order_by(Enrollment.enrolled_at.desc())
        .first()
    )

    if not enrollment and user.email:
        clean_email = user.email.strip().lower()
        enrollment = (
            db.query(Enrollment)
            .filter(func.lower(Enrollment.email) == clean_email)
            .order_by(Enrollment.enrolled_at.desc())
            .first()
        )
        if enrollment and not enrollment.user_id:
            enrollment.user_id = user.id
            db.commit()
            db.refresh(enrollment)

    if not enrollment:
        return MyEnrollmentResponse(enrollment=None)

    detail = build_enrollment_detail(enrollment, db)
    return MyEnrollmentResponse(enrollment=detail)
