from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import os
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
    status,
)
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.auth import (
    get_current_user,
    require_roles,
    require_csrf,
)
from backend.app.models.user import User
from backend.app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementUpdate,
    AnnouncementPublishRequest,
    AnnouncementResponse,
    AnnouncementListResponse,
)
from backend.app.services.announcement_service import (
    create_announcement,
    update_announcement,
    publish_announcement,
    unpublish_announcement,
    archive_announcement,
    delete_announcement,
    preview_announcement,
    get_public_announcements,
    get_feed_announcements,
    get_admin_announcements_list,
    serialize_announcement,
)

from backend.app.core.config import settings

router = APIRouter(prefix="/announcements")


# Storage directory for media uploads (configurable via settings.UPLOADS_DIR)
def get_announcements_upload_dir() -> str:
    path = os.path.join(settings.get_uploads_dir(), "announcements")
    os.makedirs(path, exist_ok=True)
    return path


UPLOAD_DIR = get_announcements_upload_dir()

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


@router.get("/public", summary="Public Announcements Feed")
def list_public_announcements(
    branch_id: Optional[str] = Query(None, description="Filter by physical branch or org-wide notices"),
    category: Optional[str] = Query(None, description="Filter by announcement category"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Publicly accessible announcement endpoint for website visitors.
    Excludes drafts, archived, expired, and non-public audience notices.
    """
    records = get_public_announcements(db=db, branch_id=branch_id, category=category, limit=limit)
    serialized = [serialize_announcement(r) for r in records]
    return {"announcements": serialized, "total": len(serialized)}


@router.get("/feed", summary="Personalized Member and Operational Feed")
def get_user_feed(
    branch_id: Optional[str] = Query(None, description="Branch scope filter for administrators"),
    category: Optional[str] = Query(None, description="Category filter"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Personalized operational notice feed for authenticated users.
    Applies member branch scoping and filters operational notices according to role.
    """
    records = get_feed_announcements(
        db=db, actor=current_user, branch_id=branch_id, category=category, limit=limit
    )
    serialized = [serialize_announcement(r) for r in records]
    return {"announcements": serialized, "total": len(serialized)}


@router.get("/admin/list", summary="Staff and Administrative Content List")
def list_admin_announcements(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by draft, published, archived"),
    branch_id: Optional[str] = Query(None, description="Target branch filter"),
    category: Optional[str] = Query(None, description="Category filter"),
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Administrative list of announcements with draft/published status and branch isolation.
    Branch managers and desk staff are restricted to their authorized facility.
    """
    records = get_admin_announcements_list(
        db=db,
        actor=current_user,
        status_filter=status_filter,
        branch_id=branch_id,
        category=category,
    )
    serialized = [serialize_announcement(r) for r in records]
    return {"announcements": serialized, "total": len(serialized)}


@router.get("/{announcement_id}/preview", summary="Preview Announcement")
def preview_announcement_endpoint(
    announcement_id: str,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager", "front_desk", "staff")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Preview draft or scheduled announcement for authorized staff."""
    record = preview_announcement(db=db, actor=current_user, announcement_id=announcement_id)
    return {"announcement": serialize_announcement(record)}


@router.get("/{announcement_id}", summary="Get Single Announcement")
def get_single_announcement(
    announcement_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve single announcement details. Publicly allows published public notices;
    non-public notices require appropriate authenticated permissions.
    """
    from backend.app.models.announcement import Announcement
    record = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found.")

    now = datetime.now(timezone.utc)
    # Check if publicly accessible
    if (
        record.status == "published"
        and record.audience == "public"
        and record.published_at
        and record.published_at <= now
        and (record.expires_at is None or record.expires_at > now)
    ):
        return {"announcement": serialize_announcement(record)}

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied. Notice is not available or requires administrative credentials.",
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create Announcement", dependencies=[Depends(require_csrf)])
def create_announcement_endpoint(
    data: AnnouncementCreate,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new announcement with RBAC enforcement and audit logging."""
    record = create_announcement(
        db=db,
        actor=current_user,
        data=data,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"announcement": serialize_announcement(record)}


@router.put("/{announcement_id}", summary="Update Announcement", dependencies=[Depends(require_csrf)])
def update_announcement_endpoint(
    announcement_id: str,
    data: AnnouncementUpdate,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update announcement fields with branch-isolation validation."""
    record = update_announcement(
        db=db,
        actor=current_user,
        announcement_id=announcement_id,
        data=data,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"announcement": serialize_announcement(record)}


@router.post("/{announcement_id}/publish", summary="Publish Announcement", dependencies=[Depends(require_csrf)])
def publish_announcement_endpoint(
    announcement_id: str,
    request: Request,
    payload: Optional[AnnouncementPublishRequest] = None,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Publish or schedule announcement for publication."""
    record = publish_announcement(
        db=db,
        actor=current_user,
        announcement_id=announcement_id,
        payload=payload,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"announcement": serialize_announcement(record)}


@router.post("/{announcement_id}/unpublish", summary="Unpublish Announcement", dependencies=[Depends(require_csrf)])
def unpublish_announcement_endpoint(
    announcement_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Revert a published announcement back to draft status."""
    record = unpublish_announcement(
        db=db,
        actor=current_user,
        announcement_id=announcement_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"announcement": serialize_announcement(record)}


@router.post("/{announcement_id}/archive", summary="Archive Announcement", dependencies=[Depends(require_csrf)])
def archive_announcement_endpoint(
    announcement_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Move announcement to archive status."""
    record = archive_announcement(
        db=db,
        actor=current_user,
        announcement_id=announcement_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"announcement": serialize_announcement(record)}


@router.delete("/{announcement_id}", summary="Delete Announcement", dependencies=[Depends(require_csrf)])
def delete_announcement_endpoint(
    announcement_id: str,
    request: Request,
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete announcement permanently."""
    success = delete_announcement(
        db=db,
        actor=current_user,
        announcement_id=announcement_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"success": success, "message": "Announcement deleted successfully."}


@router.post("/upload-image", summary="Upload Announcement Media", dependencies=[Depends(require_csrf)])
async def upload_image_endpoint(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("org_admin", "admin", "branch_manager", "manager")),
) -> Dict[str, str]:
    """
    Secure media upload endpoint for announcements.
    Enforces MIME type checking, magic-byte inspection, file size boundaries,
    and sanitized file paths.
    """
    mime_type = (file.content_type or "").lower().strip()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{mime_type}'. Allowed types: JPEG, PNG, WebP.",
        )

    # Read binary header for magic-byte verification
    header = await file.read(512)
    if not validate_image_magic_bytes(header, mime_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match claimed image format.",
        )

    # Reset cursor and check total file size
    await file.seek(0)
    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds maximum allowed size of 5 MB.",
        )

    ext = ALLOWED_MIME_TYPES[mime_type]
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(get_announcements_upload_dir(), safe_filename)

    with open(dest_path, "wb") as f:
        f.write(contents)

    return {"imageUrl": f"/uploads/announcements/{safe_filename}"}
