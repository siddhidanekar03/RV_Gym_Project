from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.rate_limit import rate_limit
from backend.app.models.contact import ContactInquiry
from backend.app.models.audit import AuditLog
from backend.app.schemas.contact import ContactRequest, ContactResponse

router = APIRouter()


@router.post(
    "/contact",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
    summary="Submit Facility Inquiry",
)
def submit_contact_inquiry(
    payload: ContactRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ContactResponse:
    clean_name = payload.name.strip()
    clean_phone = payload.phone.strip()

    if len(clean_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid full name (at least 2 characters).",
        )

    if len(clean_phone) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid contact phone number (at least 8 digits).",
        )

    inquiry = ContactInquiry(
        name=clean_name,
        phone=clean_phone,
        email=(payload.email or "").strip() or None,
        message=(payload.message or "").strip() or None,
        status="new",
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)

    # Audit log
    audit = AuditLog(
        action="contact.inquiry_created",
        resource_type="contact_inquiry",
        resource_id=inquiry.id,
        details={"name": clean_name, "phone": clean_phone},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    db.commit()

    return ContactResponse(
        success=True,
        message="Thank you! Your enquiry has been recorded. Our staff will contact you shortly.",
        id=inquiry.id,
    )
