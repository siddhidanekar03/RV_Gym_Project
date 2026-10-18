import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.auth import get_current_user, require_roles, require_csrf, get_client_ip
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.models.organization import Branch
from backend.app.models.membership import MembershipPlan, PlanPrice, Enrollment
from backend.app.models.trainer import TrainerProfile, TrainerMemberAssignment
from backend.app.models.website_content import WebsiteContent, EquipmentItem, GalleryItem
from backend.app.models.audit import AuditLog
from backend.app.schemas.owner import (
    WebsiteContentUpdate,
    EquipmentCreateRequest,
    EquipmentUpdateRequest,
    GalleryCreateRequest,
    GalleryUpdateRequest,
    CoachCreateRequest,
    CoachUpdateRequest,
    PlanCreateRequest,
    PlanUpdateRequest,
)
from backend.app.schemas.membership import (
    EnrollmentDetail,
    EnrollmentResponse,
    EnrollmentApprovalRequest,
    EnrollmentRejectionRequest,
    EnrollmentListResponse,
    AssignMembershipRequest,
)
from backend.app.services.membership_service import (
    approve_enrollment,
    reject_enrollment,
    assign_membership_to_user,
)
from backend.app.api.v1.endpoints.enrollment import build_enrollment_detail

router = APIRouter(prefix="/owner")

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def validate_image_magic_bytes(header: bytes, mime_type: str) -> bool:
    """Validate binary file signature matching claimed MIME type."""
    if mime_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/webp":
        return header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"
    return False


def get_owner_upload_dir(subfolder: str) -> str:
    base = settings.get_uploads_dir()
    path = os.path.join(base, subfolder)
    os.makedirs(path, exist_ok=True)
    return path


def safe_cleanup_file_if_unreferenced(db: Session, relative_url: Optional[str]) -> bool:
    """
    Remove physical media file if not referenced by any other equipment, gallery, or announcement.
    Prevents path traversal and checks that path resides within uploads directory.
    """
    if not relative_url or not relative_url.startswith("/uploads/"):
        return False

    subpath = relative_url[len("/uploads/"):]
    uploads_dir = os.path.abspath(settings.get_uploads_dir())
    target_abs = os.path.abspath(os.path.join(uploads_dir, subpath))

    # Guard against path traversal
    if not target_abs.startswith(uploads_dir):
        return False

    # Check whether any other record references this exact relative_url
    other_eq = db.query(EquipmentItem).filter(
        or_(
            EquipmentItem.primary_image_url == relative_url,
        )
    ).count()

    other_gal = db.query(GalleryItem).filter(GalleryItem.image_url == relative_url).count()
    other_coach = db.query(TrainerProfile).filter(TrainerProfile.photo_url == relative_url).count()

    # Check website content
    hero_item = db.query(WebsiteContent).filter(WebsiteContent.id == "content_homepage_hero").first()
    in_hero = False
    if hero_item and hero_item.data and hero_item.data.get("coverImageUrl") == relative_url:
        in_hero = True

    if other_eq > 0 or other_gal > 0 or other_coach > 0 or in_hero:
        return False

    if os.path.isfile(target_abs):
        try:
            os.remove(target_abs)
            return True
        except OSError:
            pass
    return False


async def process_and_save_upload(file: UploadFile, subfolder: str) -> str:
    """Validate MIME type, magic bytes, file size, and store with sanitized filename."""
    mime_type = (file.content_type or "").lower().strip()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{mime_type}'. Permitted formats: JPEG, PNG, WebP.",
        )

    header = await file.read(512)
    if not validate_image_magic_bytes(header, mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match the declared image format.",
        )

    await file.seek(0)
    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds maximum allowed size of 5 MB.",
        )

    ext = ALLOWED_MIME_TYPES[mime_type]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_dir = get_owner_upload_dir(subfolder)
    dest_path = os.path.join(dest_dir, safe_name)

    with open(dest_path, "wb") as f:
        f.write(contents)

    return f"/uploads/{subfolder}/{safe_name}"


# ==============================================================================
# 0. Overview Metrics
# ==============================================================================

@router.get("/overview", summary="Gym Owner Operational and Website Overview Metrics")
def get_owner_overview(
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve operational and website metrics for the Gym Owner Overview."""
    equipment_count = db.query(func.count(EquipmentItem.id)).scalar() or 0
    gallery_count = db.query(func.count(GalleryItem.id)).scalar() or 0
    coach_count = db.query(func.count(User.id)).filter(User.role == "trainer").scalar() or 0
    active_members = (
        db.query(func.count(User.id))
        .filter(User.role == "member", User.is_active == True)
        .scalar()
        or 0
    )
    plan_count = db.query(func.count(MembershipPlan.id)).scalar() or 0
    branch_count = db.query(func.count(Branch.id)).scalar() or 0
    pending_enrollment_count = (
        db.query(func.count(Enrollment.id))
        .filter(Enrollment.status.in_(["pending_verification", "Pending Verification at Gym Desk", "payment_pending"]))
        .scalar()
        or 0
    )

    return {
        "metrics": {
            "equipmentCount": equipment_count,
            "galleryCount": gallery_count,
            "coachCount": coach_count,
            "activeMembers": active_members,
            "planCount": plan_count,
            "branchCount": branch_count,
            "pendingEnrollmentCount": pending_enrollment_count,
        },
        "user": {
            "name": current_user.name,
            "role": current_user.role,
            "staffRole": current_user.staff_role,
        },
    }


# ==============================================================================
# 0B. Membership Enrollment Queue and Approvals
# ==============================================================================

@router.get(
    "/enrollments",
    response_model=EnrollmentListResponse,
    summary="List Membership Enrollment Applications",
)
def list_enrollments(
    status_filter: Optional[str] = Query(None, alias="status"),
    branch_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> EnrollmentListResponse:
    query = db.query(Enrollment)

    # Branch scoping: Branch managers restricted to their assigned branch
    if current_user.role in ("branch_manager", "manager"):
        if current_user.branch_id:
            query = query.filter(Enrollment.branch_id == current_user.branch_id)
    elif branch_id and branch_id.strip():
        query = query.filter(Enrollment.branch_id == branch_id.strip())

    # Status filter
    if status_filter and status_filter.strip() and status_filter.lower() != "all":
        s = status_filter.strip().lower()
        if s == "pending":
            query = query.filter(Enrollment.status.in_(["pending_verification", "Pending Verification at Gym Desk"]))
        elif s == "payment_pending":
            query = query.filter(Enrollment.status == "payment_pending")
        elif s in ("active", "approved"):
            query = query.filter(Enrollment.status.in_(["active", "approved"]))
        elif s == "rejected":
            query = query.filter(Enrollment.status == "rejected")
        else:
            query = query.filter(Enrollment.status == s)

    # Text search
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Enrollment.name).like(term),
                func.lower(Enrollment.phone).like(term),
                func.lower(Enrollment.email).like(term),
                func.lower(Enrollment.id).like(term),
            )
        )

    enrollments = query.order_by(Enrollment.enrolled_at.desc()).all()

    # Calculate pending counts for badge / filter stats
    base_count_q = db.query(Enrollment)
    if current_user.role in ("branch_manager", "manager") and current_user.branch_id:
        base_count_q = base_count_q.filter(Enrollment.branch_id == current_user.branch_id)

    pending_count = base_count_q.filter(
        Enrollment.status.in_(["pending_verification", "Pending Verification at Gym Desk"])
    ).count()

    payment_pending_count = base_count_q.filter(
        Enrollment.status == "payment_pending"
    ).count()

    items = [build_enrollment_detail(e, db) for e in enrollments]

    return EnrollmentListResponse(
        success=True,
        enrollments=items,
        totalCount=len(items),
        pendingCount=pending_count,
        paymentPendingCount=payment_pending_count,
    )


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentResponse,
    summary="Get Enrollment Application Details",
)
def get_enrollment_detail(
    enrollment_id: str,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> EnrollmentResponse:
    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment application not found.")

    if current_user.role in ("branch_manager", "manager"):
        if current_user.branch_id and enrollment.branch_id != current_user.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You are not authorized to view applications for branch '{enrollment.branch_id}'.",
            )

    detail = build_enrollment_detail(enrollment, db)
    return EnrollmentResponse(
        success=True,
        message="Enrollment retrieved successfully.",
        enrollment=detail,
    )


@router.post(
    "/enrollments/{enrollment_id}/approve",
    response_model=EnrollmentResponse,
    dependencies=[Depends(require_csrf)],
    summary="Approve Membership Enrollment Request",
)
def approve_enrollment_endpoint(
    enrollment_id: str,
    payload: EnrollmentApprovalRequest,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> EnrollmentResponse:
    payment_amt = Decimal(str(payload.paymentAmount)) if payload.paymentAmount is not None else None
    try:
        enrollment = approve_enrollment(
            db=db,
            enrollment_id=enrollment_id,
            actor=current_user,
            record_payment=payload.recordPayment,
            payment_method=payload.paymentMethod,
            payment_amount=payment_amt,
            reference_number=payload.referenceNumber,
            notes=payload.notes,
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Enrollment approval failed: {str(e)}")

    detail = build_enrollment_detail(enrollment, db)
    msg = "Enrollment approved and membership activated!" if enrollment.status == "active" else "Enrollment approved! Awaiting front desk payment."
    return EnrollmentResponse(
        success=True,
        message=msg,
        enrollment=detail,
    )


@router.post(
    "/enrollments/{enrollment_id}/reject",
    response_model=EnrollmentResponse,
    dependencies=[Depends(require_csrf)],
    summary="Reject Membership Enrollment Request",
)
def reject_enrollment_endpoint(
    enrollment_id: str,
    payload: EnrollmentRejectionRequest,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> EnrollmentResponse:
    try:
        enrollment = reject_enrollment(
            db=db,
            enrollment_id=enrollment_id,
            actor=current_user,
            reason=payload.reason,
            notes=payload.notes,
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Enrollment rejection failed: {str(e)}")

    detail = build_enrollment_detail(enrollment, db)
    return EnrollmentResponse(
        success=True,
        message=f"Enrollment application rejected. Reason: {payload.reason}",
        enrollment=detail,
    )


# ==============================================================================
# 0C. Member Lookup & Direct Membership Assignment
# ==============================================================================

@router.get("/members/search", summary="Search Members for Direct Membership Assignment")
def search_members_for_assignment(
    q: str = Query(..., min_length=1),
    branch_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    clean_q = q.strip().lower()
    query = db.query(User).filter(User.role == "member")

    if current_user.role in ("branch_manager", "manager") and current_user.branch_id:
        query = query.filter(User.branch_id == current_user.branch_id)
    elif branch_id and branch_id.strip() and branch_id.strip() != "all":
        query = query.filter(User.branch_id == branch_id.strip())

    term = f"%{clean_q}%"
    users = query.filter(
        or_(
            func.lower(User.name).like(term),
            func.lower(User.email).like(term),
            func.lower(User.phone).like(term),
            func.lower(User.membership_id).like(term),
        )
    ).limit(20).all()

    members = []
    for u in users:
        members.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "branchId": u.branch_id,
            "branchName": u.branch.name if u.branch else "Narsobawadi Main Campus",
            "membershipId": u.membership_id or "Pending Card",
            "status": u.membership_status,
            "planId": u.membership_plan_id,
            "planName": u.membership_plan.name if u.membership_plan else "No Plan Assigned",
            "validUntil": u.valid_until.strftime("%B %d, %Y") if u.valid_until else "Pending",
        })

    return {"members": members}


@router.post("/members/assign-membership", dependencies=[Depends(require_csrf)], summary="Assign Membership Plan Directly to Existing Member")
def assign_membership_endpoint(
    payload: AssignMembershipRequest,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    pay_amt = Decimal(str(payload.paymentAmount)) if payload.paymentAmount is not None else None
    try:
        enrollment, invoice, target_user = assign_membership_to_user(
            db=db,
            target_user_id=payload.userId,
            plan_id=payload.planId,
            actor=current_user,
            branch_id=payload.branchId,
            record_payment=payload.recordPayment,
            payment_method=payload.paymentMethod,
            payment_amount=pay_amt,
            reference_number=payload.referenceNumber,
            notes=payload.notes,
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to assign membership: {str(e)}")

    detail = build_enrollment_detail(enrollment, db)
    return {
        "success": True,
        "message": "Membership assigned and activated successfully!" if enrollment.status == "active" else "Membership assigned! Enrollment request created in Membership Requests.",
        "enrollment": detail,
        "invoiceNumber": invoice.invoice_number,
        "membershipId": target_user.membership_id,
        "userStatus": target_user.membership_status,
    }


# ==============================================================================
# 1. Website Content Management
# ==============================================================================

@router.get("/website-content", summary="Get Configured Website Content Sections")
def get_website_content(
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    items = db.query(WebsiteContent).all()
    sections = {}
    for item in items:
        sections[item.section] = {
            "id": item.id,
            "section": item.section,
            "data": item.data,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else None,
        }
    return {"sections": sections}


@router.put("/website-content/{section}", dependencies=[Depends(require_csrf)], summary="Update Website Content Section")
def update_website_content_section(
    section: str,
    payload: WebsiteContentUpdate,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    valid_sections = {
        "homepage_hero",
        "facility_info",
        "hours",
        "contact",
        "promotions_banner",
        "announcements_banner",
    }
    if section not in valid_sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section '{section}'. Allowed sections: {sorted(list(valid_sections))}",
        )

    record_id = f"content_{section}"
    item = db.query(WebsiteContent).filter(WebsiteContent.id == record_id).first()
    if not item:
        item = WebsiteContent(
            id=record_id,
            section=section,
            data=payload.data,
            updated_by_id=current_user.id,
        )
        db.add(item)
    else:
        item.data = payload.data
        item.updated_by_id = current_user.id
        item.updated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        actor_id=current_user.id,
        action="website.content_update",
        resource_type="website_content",
        resource_id=record_id,
        details={"section": section, "keys_updated": list(payload.data.keys())},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "message": f"Website section '{section}' updated successfully.",
        "section": section,
        "data": item.data,
    }


# ==============================================================================
# 2. Equipment Management
# ==============================================================================

@router.get("/equipment", summary="List Equipment for Management")
def list_owner_equipment(
    branch_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(EquipmentItem)
    if branch_id:
        query = query.filter(EquipmentItem.branch_id == branch_id)
    items = query.order_by(EquipmentItem.display_order.asc(), EquipmentItem.created_at.desc()).all()

    return {
        "equipment": [
            {
                "id": e.id,
                "branchId": e.branch_id,
                "name": e.name,
                "category": e.category,
                "spec": e.spec,
                "brandModel": e.brand_model,
                "primaryImageUrl": e.primary_image_url,
                "images": e.images or [],
                "isPublished": e.is_published,
                "displayOrder": e.display_order,
                "createdAt": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ]
    }


@router.post("/equipment", dependencies=[Depends(require_csrf)], summary="Add New Equipment Item")
def create_owner_equipment(
    payload: EquipmentCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Branch '{payload.branch_id}' does not exist.",
        )

    item = EquipmentItem(
        branch_id=payload.branch_id,
        name=payload.name.strip(),
        category=payload.category.strip(),
        spec=payload.spec.strip(),
        brand_model=payload.brand_model.strip() if payload.brand_model else None,
        primary_image_url=payload.primary_image_url,
        images=payload.images or [],
        is_published=payload.is_published,
        display_order=payload.display_order,
    )
    db.add(item)

    audit = AuditLog(
        actor_id=current_user.id,
        action="equipment.create",
        resource_type="equipment_item",
        resource_id=item.id,
        details={"name": item.name, "category": item.category, "branchId": item.branch_id},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()
    db.refresh(item)

    return {
        "success": True,
        "message": f"Equipment '{item.name}' added successfully.",
        "id": item.id,
    }


@router.put("/equipment/{equipment_id}", dependencies=[Depends(require_csrf)], summary="Update Equipment Item")
def update_owner_equipment(
    equipment_id: str,
    payload: EquipmentUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    item = db.query(EquipmentItem).filter(EquipmentItem.id == equipment_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment item not found.")

    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.category is not None:
        item.category = payload.category.strip()
    if payload.spec is not None:
        item.spec = payload.spec.strip()
    if payload.brand_model is not None:
        item.brand_model = payload.brand_model.strip() if payload.brand_model else None
    if payload.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
        if not branch:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{payload.branch_id}' not found.")
        item.branch_id = payload.branch_id
    if payload.primary_image_url is not None:
        item.primary_image_url = payload.primary_image_url
    if payload.images is not None:
        item.images = payload.images
    if payload.is_published is not None:
        item.is_published = payload.is_published
    if payload.display_order is not None:
        item.display_order = payload.display_order

    audit = AuditLog(
        actor_id=current_user.id,
        action="equipment.update",
        resource_type="equipment_item",
        resource_id=item.id,
        details={"name": item.name, "isPublished": item.is_published},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "message": f"Equipment '{item.name}' updated successfully.",
        "id": item.id,
    }


@router.delete("/equipment/{equipment_id}", dependencies=[Depends(require_csrf)], summary="Remove Equipment Item")
def delete_owner_equipment(
    equipment_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    item = db.query(EquipmentItem).filter(EquipmentItem.id == equipment_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment item not found.")

    item_name = item.name
    primary_url = item.primary_image_url
    images_list = list(item.images or [])

    db.delete(item)

    audit = AuditLog(
        actor_id=current_user.id,
        action="equipment.delete",
        resource_type="equipment_item",
        resource_id=equipment_id,
        details={"name": item_name},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    # Safely clean up physical files if no longer referenced
    if primary_url:
        safe_cleanup_file_if_unreferenced(db, primary_url)
    for img in images_list:
        safe_cleanup_file_if_unreferenced(db, img)

    return {"success": True, "message": f"Equipment '{item_name}' removed successfully."}


@router.post("/equipment/{equipment_id}/upload-photo", dependencies=[Depends(require_csrf)], summary="Upload Equipment Photograph")
async def upload_equipment_photo(
    equipment_id: str,
    file: UploadFile = File(...),
    set_primary: bool = Query(True),
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    item = db.query(EquipmentItem).filter(EquipmentItem.id == equipment_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment item not found.")

    image_url = await process_and_save_upload(file, "equipment")

    current_images = list(item.images or [])
    if image_url not in current_images:
        current_images.append(image_url)
    item.images = current_images

    if set_primary or not item.primary_image_url:
        item.primary_image_url = image_url

    db.commit()
    db.refresh(item)

    return {
        "success": True,
        "message": "Equipment photo uploaded successfully.",
        "imageUrl": image_url,
        "primaryImageUrl": item.primary_image_url,
        "images": item.images,
    }


# ==============================================================================
# 3. Gallery Management
# ==============================================================================

@router.get("/gallery", summary="List Gallery Items for Management")
def list_owner_gallery(
    branch_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(GalleryItem)
    if branch_id:
        query = query.filter(GalleryItem.branch_id == branch_id)
    items = query.order_by(GalleryItem.display_order.asc(), GalleryItem.created_at.desc()).all()

    return {
        "gallery": [
            {
                "id": g.id,
                "branchId": g.branch_id,
                "zone": g.zone,
                "description": g.description,
                "imageUrl": g.image_url,
                "status": g.status,
                "isPublished": g.is_published,
                "displayOrder": g.display_order,
                "createdAt": g.created_at.isoformat() if g.created_at else None,
            }
            for g in items
        ]
    }


@router.post("/gallery", dependencies=[Depends(require_csrf)], summary="Add New Gallery Showcase Item")
def create_owner_gallery(
    payload: GalleryCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{payload.branch_id}' not found.")

    item = GalleryItem(
        branch_id=payload.branch_id,
        zone=payload.zone.strip(),
        description=payload.description.strip(),
        image_url=payload.image_url.strip(),
        status=payload.status.strip(),
        is_published=payload.is_published,
        display_order=payload.display_order,
    )
    db.add(item)

    audit = AuditLog(
        actor_id=current_user.id,
        action="gallery.create",
        resource_type="gallery_item",
        resource_id=item.id,
        details={"zone": item.zone, "branchId": item.branch_id},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()
    db.refresh(item)

    return {
        "success": True,
        "message": f"Gallery zone '{item.zone}' created successfully.",
        "id": item.id,
    }


@router.put("/gallery/{gallery_id}", dependencies=[Depends(require_csrf)], summary="Update Gallery Item")
def update_owner_gallery(
    gallery_id: str,
    payload: GalleryUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    item = db.query(GalleryItem).filter(GalleryItem.id == gallery_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery item not found.")

    if payload.zone is not None:
        item.zone = payload.zone.strip()
    if payload.description is not None:
        item.description = payload.description.strip()
    if payload.image_url is not None:
        item.image_url = payload.image_url.strip()
    if payload.status is not None:
        item.status = payload.status.strip()
    if payload.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
        if not branch:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{payload.branch_id}' not found.")
        item.branch_id = payload.branch_id
    if payload.is_published is not None:
        item.is_published = payload.is_published
    if payload.display_order is not None:
        item.display_order = payload.display_order

    audit = AuditLog(
        actor_id=current_user.id,
        action="gallery.update",
        resource_type="gallery_item",
        resource_id=item.id,
        details={"zone": item.zone, "isPublished": item.is_published},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"Gallery zone '{item.zone}' updated successfully.", "id": item.id}


@router.delete("/gallery/{gallery_id}", dependencies=[Depends(require_csrf)], summary="Remove Gallery Item")
def delete_owner_gallery(
    gallery_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    item = db.query(GalleryItem).filter(GalleryItem.id == gallery_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery item not found.")

    zone_name = item.zone
    image_url = item.image_url
    db.delete(item)

    audit = AuditLog(
        actor_id=current_user.id,
        action="gallery.delete",
        resource_type="gallery_item",
        resource_id=gallery_id,
        details={"zone": zone_name},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    if image_url:
        safe_cleanup_file_if_unreferenced(db, image_url)

    return {"success": True, "message": f"Gallery item '{zone_name}' removed successfully."}


@router.post("/gallery/upload-photo", dependencies=[Depends(require_csrf)], summary="Upload Gallery Photograph")
async def upload_gallery_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("org_admin", "admin")),
) -> Dict[str, str]:
    image_url = await process_and_save_upload(file, "gallery")
    return {"imageUrl": image_url}


# ==============================================================================
# 4. Coaches & Staff Management
# ==============================================================================

@router.get("/coaches", summary="List Coaches and Trainers for Management")
def list_owner_coaches(
    branch_id: Optional[str] = Query(None),
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(User).filter(User.role == "trainer")
    if branch_id:
        query = query.filter(User.branch_id == branch_id)
    coaches = query.order_by(User.name.asc()).all()

    result = []
    for c in coaches:
        prof = c.trainer_profile
        assigned_count = db.query(User).filter(User.assigned_trainer_id == c.id, User.is_active == True).count()
        result.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "branchId": c.branch_id,
            "branchName": c.branch.name if c.branch else "Main Branch",
            "staffRole": c.staff_role or "Trainer",
            "isActive": c.is_active,
            "specialization": prof.specialization if prof else "Strength & Conditioning",
            "bio": prof.bio if prof else None,
            "certifications": prof.certifications if prof else [],
            "experienceYears": prof.experience_years if prof else 1,
            "maxClients": prof.max_clients if prof else 20,
            "assignedMembersCount": assigned_count,
            "isAcceptingClients": prof.is_accepting_clients if prof else True,
            "photoUrl": prof.photo_url if prof else None,
            "createdAt": c.created_at.isoformat() if c.created_at else None,
        })

    return {"coaches": result}


@router.post("/coaches", dependencies=[Depends(require_csrf)], summary="Add New Coach or Trainer Account")
def create_owner_coach(
    payload: CoachCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    existing = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{payload.email}' already exists.",
        )

    branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{payload.branch_id}' not found.")

    # Never store plaintext passwords
    hashed = hash_password(payload.password)

    coach = User(
        email=payload.email.lower().strip(),
        hashed_password=hashed,
        name=payload.name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        role="trainer",
        staff_role=payload.specialization.strip(),
        branch_id=payload.branch_id,
        is_active=True,
    )
    db.add(coach)
    db.flush()

    profile = TrainerProfile(
        user_id=coach.id,
        specialization=payload.specialization.strip(),
        bio=payload.bio.strip() if payload.bio else None,
        certifications=payload.certifications or [],
        experience_years=payload.experience_years,
        max_clients=payload.max_clients,
        is_accepting_clients=payload.is_accepting_clients,
        photo_url=payload.photo_url,
    )
    db.add(profile)

    audit = AuditLog(
        actor_id=current_user.id,
        action="coach.create",
        resource_type="user",
        resource_id=coach.id,
        details={"name": coach.name, "email": coach.email, "branchId": coach.branch_id, "hasPhoto": bool(payload.photo_url)},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "message": f"Coach '{coach.name}' created successfully.",
        "id": coach.id,
    }


@router.put("/coaches/{coach_id}", dependencies=[Depends(require_csrf)], summary="Update Coach Profile and Status")
def update_owner_coach(
    coach_id: str,
    payload: CoachUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    coach = db.query(User).filter(User.id == coach_id, User.role == "trainer").first()
    if not coach:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coach account not found.")

    if payload.name is not None:
        coach.name = payload.name.strip()
    if payload.phone is not None:
        coach.phone = payload.phone.strip() if payload.phone else None
    if payload.branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
        if not branch:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Branch '{payload.branch_id}' not found.")
        coach.branch_id = payload.branch_id
    if payload.is_active is not None:
        coach.is_active = payload.is_active

    prof = coach.trainer_profile
    if not prof:
        prof = TrainerProfile(user_id=coach.id, specialization="Coach")
        db.add(prof)

    if payload.specialization is not None:
        prof.specialization = payload.specialization.strip()
        coach.staff_role = payload.specialization.strip()
    if payload.bio is not None:
        prof.bio = payload.bio.strip() if payload.bio else None
    if payload.certifications is not None:
        prof.certifications = payload.certifications
    if payload.experience_years is not None:
        prof.experience_years = payload.experience_years
    if payload.max_clients is not None:
        prof.max_clients = payload.max_clients
    if payload.is_accepting_clients is not None:
        prof.is_accepting_clients = payload.is_accepting_clients

    old_photo = None
    if payload.photo_url is not None:
        if prof.photo_url and prof.photo_url != payload.photo_url:
            old_photo = prof.photo_url
        prof.photo_url = payload.photo_url.strip() if payload.photo_url else None

    audit = AuditLog(
        actor_id=current_user.id,
        action="coach.update",
        resource_type="user",
        resource_id=coach.id,
        details={"name": coach.name, "isActive": coach.is_active, "branchId": coach.branch_id},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    if old_photo:
        safe_cleanup_file_if_unreferenced(db, old_photo)

    return {"success": True, "message": f"Coach '{coach.name}' updated successfully."}


@router.post("/coaches/upload-photo", dependencies=[Depends(require_csrf)], summary="Upload Coach Photograph")
async def upload_coach_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("org_admin", "admin")),
) -> Dict[str, str]:
    image_url = await process_and_save_upload(file, "coaches")
    return {"imageUrl": image_url}


@router.delete("/coaches/{coach_id}/photo", dependencies=[Depends(require_csrf)], summary="Delete Coach Photograph")
def delete_coach_photo(
    coach_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    coach = db.query(User).filter(User.id == coach_id, User.role == "trainer").first()
    if not coach:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coach account not found.")

    prof = coach.trainer_profile
    old_photo = None
    if prof and prof.photo_url:
        old_photo = prof.photo_url
        prof.photo_url = None
        db.commit()

    if old_photo:
        safe_cleanup_file_if_unreferenced(db, old_photo)

    audit = AuditLog(
        actor_id=current_user.id,
        action="coach.delete_photo",
        resource_type="user",
        resource_id=coach.id,
        details={"name": coach.name},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"Photograph removed for coach '{coach.name}'."}


# ==============================================================================
# 5. Membership Plans Management
# ==============================================================================

@router.get("/plans", summary="List All Membership Plans for Management")
def list_owner_plans(
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    plans = db.query(MembershipPlan).order_by(MembershipPlan.price.asc()).all()
    results = []
    for p in plans:
        user_count = db.query(User).filter(User.membership_plan_id == p.id).count()
        enrollment_count = db.query(Enrollment).filter(Enrollment.plan_id == p.id).count()
        results.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "accessScope": p.access_scope,
            "price": float(p.price),
            "currency": p.currency,
            "billingCycle": p.billing_cycle,
            "durationDays": p.duration_days,
            "isFeatured": p.is_featured,
            "isActive": p.is_active,
            "description": p.description,
            "perks": p.perks or [],
            "activeSubscribersCount": user_count,
            "enrollmentCount": enrollment_count,
            "hasDependencies": (user_count > 0 or enrollment_count > 0),
        })

    return {"plans": results}


@router.post("/plans", dependencies=[Depends(require_csrf)], summary="Create New Membership Plan")
def create_owner_plan(
    payload: PlanCreateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    plan_id = payload.id.strip().lower().replace(" ", "_")
    existing = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A membership plan with identifier '{plan_id}' already exists.",
        )

    plan = MembershipPlan(
        id=plan_id,
        name=payload.name.strip(),
        category=payload.category.strip(),
        access_scope=payload.access_scope.strip(),
        price=payload.price,
        currency=payload.currency.strip(),
        billing_cycle=payload.billing_cycle.strip(),
        duration_days=payload.duration_days,
        is_featured=payload.is_featured,
        is_active=payload.is_active,
        description=payload.description.strip() if payload.description else None,
        perks=payload.perks or [],
    )
    db.add(plan)
    db.flush()

    # Create effective-dated price entry for historical ledger tracking
    price_entry = PlanPrice(
        plan_id=plan.id,
        price=plan.price,
        currency=plan.currency,
        effective_from=datetime.now(timezone.utc).date(),
        is_active=True,
    )
    db.add(price_entry)

    audit = AuditLog(
        actor_id=current_user.id,
        action="plan.create",
        resource_type="membership_plan",
        resource_id=plan.id,
        details={"name": plan.name, "price": str(plan.price), "durationDays": plan.duration_days},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "message": f"Membership plan '{plan.name}' created successfully.",
        "id": plan.id,
    }


@router.put("/plans/{plan_id}", dependencies=[Depends(require_csrf)], summary="Update Membership Plan Details")
def update_owner_plan(
    plan_id: str,
    payload: PlanUpdateRequest,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership plan not found.")

    if payload.name is not None:
        plan.name = payload.name.strip()
    if payload.category is not None:
        plan.category = payload.category.strip()
    if payload.access_scope is not None:
        plan.access_scope = payload.access_scope.strip()
    if payload.currency is not None:
        plan.currency = payload.currency.strip()
    if payload.billing_cycle is not None:
        plan.billing_cycle = payload.billing_cycle.strip()
    if payload.duration_days is not None:
        plan.duration_days = payload.duration_days
    if payload.is_featured is not None:
        plan.is_featured = payload.is_featured
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    if payload.description is not None:
        plan.description = payload.description.strip() if payload.description else None
    if payload.perks is not None:
        plan.perks = payload.perks

    # If price has changed, add new effective PlanPrice without mutating historical receipts
    if payload.price is not None and payload.price != plan.price:
        plan.price = payload.price
        new_price_entry = PlanPrice(
            plan_id=plan.id,
            price=payload.price,
            currency=plan.currency,
            effective_from=datetime.now(timezone.utc).date(),
            is_active=True,
        )
        db.add(new_price_entry)

    audit = AuditLog(
        actor_id=current_user.id,
        action="plan.update",
        resource_type="membership_plan",
        resource_id=plan.id,
        details={"name": plan.name, "isActive": plan.is_active, "price": str(plan.price)},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"Membership plan '{plan.name}' updated successfully."}


@router.delete("/plans/{plan_id}", dependencies=[Depends(require_csrf)], summary="Delete or Archive Membership Plan")
def delete_or_archive_owner_plan(
    plan_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    plan = db.query(MembershipPlan).filter(MembershipPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership plan not found.")

    user_count = db.query(User).filter(User.membership_plan_id == plan.id).count()
    enrollment_count = db.query(Enrollment).filter(Enrollment.plan_id == plan.id).count()

    if user_count > 0 or enrollment_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete plan '{plan.name}' because {user_count} active members "
                f"and {enrollment_count} enrollments depend on it. Please unpublish or archive the plan instead."
            ),
        )

    plan_name = plan.name
    db.delete(plan)

    audit = AuditLog(
        actor_id=current_user.id,
        action="plan.delete",
        resource_type="membership_plan",
        resource_id=plan_id,
        details={"name": plan_name},
        ip_address=get_client_ip(request),
    )
    db.add(audit)
    db.commit()

    return {"success": True, "message": f"Plan '{plan_name}' deleted successfully."}


# ==============================================================================
# 6. General Media Upload
# ==============================================================================

@router.post("/upload-media", dependencies=[Depends(require_csrf)], summary="Upload General Media Asset")
async def upload_general_media(
    file: UploadFile = File(...),
    subfolder: str = Query("website"),
    current_user: User = Depends(require_roles("org_admin", "admin")),
) -> Dict[str, str]:
    safe_folder = "website" if subfolder not in {"website", "equipment", "gallery", "banners", "coaches"} else subfolder
    image_url = await process_and_save_upload(file, safe_folder)
    return {"imageUrl": image_url}


# ==============================================================================
# 7. Branches Overview for Management
# ==============================================================================

@router.get("/branches", summary="List All Branches for Management")
def list_owner_branches(
    current_user: User = Depends(require_roles("org_admin", "admin")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    branches = db.query(Branch).order_by(Branch.name.asc()).all()
    return {
        "branches": [
            {
                "id": b.id,
                "name": b.name,
                "code": b.code,
                "city": b.city,
                "address": b.address,
                "phone": b.phone,
                "isActive": b.is_active,
            }
            for b in branches
        ]
    }
