from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.rate_limit import rate_limit
from backend.app.models.membership import MembershipPlan, Enrollment
from backend.app.models.user import User
from backend.app.models.audit import AuditLog
from backend.app.services.billing_service import create_invoice_for_enrollment
from backend.app.schemas.membership import (
    EnrollmentRequest,
    EnrollmentResponse,
    EnrollmentDetail,
)

router = APIRouter()


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

    clean_email = (payload.email or "").strip().lower() or None

    # Check if applicant is already a registered user
    existing_user = None
    if clean_email:
        existing_user = db.query(User).filter(User.email == clean_email).first()

    # 1. Atomic Transaction: Create Enrollment and Initial Invoice together
    enrollment = Enrollment(
        plan_id=plan.id,
        branch_id="narsobawadi",
        name=clean_name,
        phone=clean_phone,
        email=clean_email,
        price=plan.price,
        currency=plan.currency,
        status="Pending Verification at Gym Desk",
        accepted_terms=True,
    )
    db.add(enrollment)
    db.flush()

    # 2. Create Initial Invoice in the same transaction
    invoice = create_invoice_for_enrollment(
        db=db,
        enrollment=enrollment,
        plan=plan,
        user_id=existing_user.id if existing_user else None,
        branch_id=enrollment.branch_id,
    )

    # 3. Audit trail
    audit = AuditLog(
        actor_id=existing_user.id if existing_user else None,
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

    detail = EnrollmentDetail(
        id=enrollment.id,
        planId=plan.id,
        planName=plan.name,
        price=int(plan.price),
        currency=plan.currency,
        name=enrollment.name,
        phone=enrollment.phone,
        email=enrollment.email or "",
        status=enrollment.status,
        enrolledAt=enrollment.enrolled_at.isoformat(),
        invoiceId=invoice.id,
        invoiceNumber=invoice.invoice_number,
    )

    return EnrollmentResponse(
        success=True,
        message=f"Enrollment submitted for {plan.name} plan! Please visit the gym desk to activate your RFID membership card.",
        enrollment=detail,
    )
