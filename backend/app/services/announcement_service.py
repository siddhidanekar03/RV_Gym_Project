from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from backend.app.models.announcement import Announcement
from backend.app.models.organization import Branch, Organization
from backend.app.models.user import User
from backend.app.models.audit import AuditLog
from backend.app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementUpdate,
    AnnouncementPublishRequest,
)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime object is timezone-aware and converted to UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def record_audit(
    db: Session,
    actor_id: Optional[str],
    action: str,
    resource_id: str,
    details: Dict[str, Any],
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Record content management events in the append-only audit trail."""
    audit_entry = AuditLog(
        id=str(uuid.uuid4()),
        actor_id=actor_id,
        action=action,
        resource_type="announcement",
        resource_id=resource_id,
        details=details,
        ip_address=client_ip,
        user_agent=user_agent,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_entry)


def serialize_announcement(announcement: Announcement) -> Dict[str, Any]:
    """Format announcement entity into dictionary with branch and author names."""
    return {
        "id": announcement.id,
        "organizationId": announcement.organization_id,
        "branchId": announcement.branch_id,
        "branchName": announcement.branch.name if announcement.branch else ("All Branches" if announcement.is_org_wide else None),
        "isOrgWide": announcement.is_org_wide,
        "title": announcement.title,
        "body": announcement.body,
        "category": announcement.category,
        "priority": announcement.priority,
        "status": announcement.status,
        "audience": announcement.audience,
        "pinned": announcement.pinned,
        "imageUrl": announcement.image_url,
        "authorId": announcement.author_id,
        "authorName": announcement.author.name if announcement.author else None,
        "publishedAt": announcement.published_at,
        "expiresAt": announcement.expires_at,
        "createdAt": announcement.created_at,
        "updatedAt": announcement.updated_at,
    }


def create_announcement(
    db: Session,
    actor: User,
    data: AnnouncementCreate,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Announcement:
    """
    Create a new announcement with strict RBAC and multi-branch isolation.
    - Org Admins: can create org-wide or branch-specific announcements across any branch.
    - Branch Managers: can create announcements ONLY for their assigned branch.
    - Front Desk, Trainers, Members: Forbidden.
    """
    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to create announcements.",
        )

    # Branch Manager scope validation
    if actor.role in ("branch_manager", "manager"):
        if data.is_org_wide:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Branch managers cannot create organization-wide announcements.",
            )
        target_branch = data.branch_id or actor.branch_id
        if target_branch != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Branch managers can only create announcements for their assigned branch.",
            )
        data.branch_id = actor.branch_id
        data.is_org_wide = False

    # Org Admin scope normalization
    if actor.role in ("org_admin", "admin"):
        if data.is_org_wide:
            data.branch_id = None
        elif not data.branch_id:
            # If not specified and not marked org-wide, default to actor's branch or org-wide
            data.branch_id = actor.branch_id or None

    # Resolve organization ID
    org_id = None
    if data.branch_id:
        branch = db.query(Branch).filter(Branch.id == data.branch_id).first()
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target branch '{data.branch_id}' does not exist.",
            )
        org_id = branch.organization_id
    else:
        # Org-wide: resolve from actor's branch or default org
        if actor.branch and actor.branch.organization_id:
            org_id = actor.branch.organization_id
        else:
            first_org = db.query(Organization).first()
            if first_org:
                org_id = first_org.id
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Organization tenant not configured.",
                )

    pub_at = ensure_utc(data.publish_at)
    exp_at = ensure_utc(data.expires_at)

    if pub_at and exp_at and exp_at <= pub_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expires_at must be strictly later than publish_at.",
        )

    # Initial status handling
    init_status = data.status or "draft"
    if init_status == "published" and pub_at is None:
        pub_at = datetime.now(timezone.utc)

    announcement = Announcement(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        branch_id=data.branch_id,
        is_org_wide=data.is_org_wide,
        title=data.title,
        body=data.body,
        category=data.category,
        priority=data.priority,
        status=init_status,
        audience=data.audience,
        pinned=data.pinned,
        image_url=data.image_url,
        author_id=actor.id,
        published_at=pub_at,
        expires_at=exp_at,
    )

    db.add(announcement)
    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.create",
        resource_id=announcement.id,
        details={
            "title": announcement.title,
            "branch_id": announcement.branch_id,
            "is_org_wide": announcement.is_org_wide,
            "status": announcement.status,
            "audience": announcement.audience,
        },
        client_ip=client_ip,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(announcement)
    return announcement


def update_announcement(
    db: Session,
    actor: User,
    announcement_id: str,
    data: AnnouncementUpdate,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Announcement:
    """
    Update announcement fields with strict IDOR and cross-branch prevention.
    """
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to edit announcements.",
        )

    # Branch Manager scope validation
    if actor.role in ("branch_manager", "manager"):
        if announcement.is_org_wide:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Branch managers cannot modify organization-wide announcements.",
            )
        if announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You cannot modify announcements outside your authorized branch.",
            )
        if data.is_org_wide is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Branch managers cannot convert announcements to organization-wide.",
            )
        if data.branch_id and data.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Branch managers cannot reassign announcements to another branch.",
            )

    # Apply updates
    if data.title is not None:
        announcement.title = data.title.strip()
    if data.body is not None:
        announcement.body = data.body.strip()
    if data.category is not None:
        announcement.category = data.category
    if data.priority is not None:
        announcement.priority = data.priority
    if data.audience is not None:
        announcement.audience = data.audience
    if data.pinned is not None:
        announcement.pinned = data.pinned
    if data.image_url is not None:
        announcement.image_url = data.image_url

    # Scope alterations
    if actor.role in ("org_admin", "admin"):
        if data.is_org_wide is not None:
            announcement.is_org_wide = data.is_org_wide
            if data.is_org_wide:
                announcement.branch_id = None
        if data.branch_id is not None and not announcement.is_org_wide:
            announcement.branch_id = data.branch_id

    # Date updates
    if data.publish_at is not None:
        announcement.published_at = ensure_utc(data.publish_at)
    if data.expires_at is not None:
        announcement.expires_at = ensure_utc(data.expires_at)

    if announcement.published_at and announcement.expires_at:
        if announcement.expires_at <= announcement.published_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="expires_at must be strictly later than publish_at.",
            )

    if data.status is not None:
        announcement.status = data.status
        if data.status == "published" and announcement.published_at is None:
            announcement.published_at = datetime.now(timezone.utc)

    announcement.updated_at = datetime.now(timezone.utc)

    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.update",
        resource_id=announcement.id,
        details={
            "title": announcement.title,
            "status": announcement.status,
            "branch_id": announcement.branch_id,
            "is_org_wide": announcement.is_org_wide,
        },
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(announcement)
    return announcement


def publish_announcement(
    db: Session,
    actor: User,
    announcement_id: str,
    payload: Optional[AnnouncementPublishRequest] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Announcement:
    """
    Publish an announcement immediately or schedule it for a future timestamp.
    """
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to publish announcements.",
        )

    if actor.role in ("branch_manager", "manager"):
        if announcement.is_org_wide or announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only publish announcements for your authorized branch.",
            )

    pub_at = ensure_utc(payload.publish_at) if payload and payload.publish_at else None
    exp_at = ensure_utc(payload.expires_at) if payload and payload.expires_at else announcement.expires_at

    if not pub_at:
        pub_at = announcement.published_at or datetime.now(timezone.utc)

    if exp_at and pub_at and exp_at <= pub_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expires_at must be strictly later than publish_at.",
        )

    announcement.status = "published"
    announcement.published_at = pub_at
    announcement.expires_at = exp_at
    announcement.updated_at = datetime.now(timezone.utc)

    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.publish",
        resource_id=announcement.id,
        details={
            "published_at": announcement.published_at.isoformat() if announcement.published_at else None,
            "expires_at": announcement.expires_at.isoformat() if announcement.expires_at else None,
        },
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(announcement)
    return announcement


def unpublish_announcement(
    db: Session,
    actor: User,
    announcement_id: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Announcement:
    """Revert a published announcement back to draft status."""
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to unpublish announcements.",
        )

    if actor.role in ("branch_manager", "manager"):
        if announcement.is_org_wide or announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only unpublish announcements for your authorized branch.",
            )

    announcement.status = "draft"
    announcement.updated_at = datetime.now(timezone.utc)

    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.unpublish",
        resource_id=announcement.id,
        details={"status": "draft"},
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(announcement)
    return announcement


def archive_announcement(
    db: Session,
    actor: User,
    announcement_id: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Announcement:
    """Move an announcement to archived status."""
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to archive announcements.",
        )

    if actor.role in ("branch_manager", "manager"):
        if announcement.is_org_wide or announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only archive announcements for your authorized branch.",
            )

    announcement.status = "archived"
    announcement.updated_at = datetime.now(timezone.utc)

    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.archive",
        resource_id=announcement.id,
        details={"status": "archived"},
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(announcement)
    return announcement


def delete_announcement(
    db: Session,
    actor: User,
    announcement_id: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """Delete an announcement with branch-isolation validation and audit trail."""
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role in ("front_desk", "staff", "trainer", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your role is not authorized to delete announcements.",
        )

    if actor.role in ("branch_manager", "manager"):
        if announcement.is_org_wide or announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only delete announcements within your authorized branch.",
            )

    record_audit(
        db=db,
        actor_id=actor.id,
        action="announcement.delete",
        resource_id=announcement.id,
        details={"title": announcement.title, "branch_id": announcement.branch_id},
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.delete(announcement)
    db.commit()
    return True


def preview_announcement(db: Session, actor: User, announcement_id: str) -> Announcement:
    """Preview draft or scheduled announcement for authorized staff and administrators."""
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found.",
        )

    if actor.role == "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Preview mode is restricted to staff and administrators.",
        )

    if actor.role in ("branch_manager", "manager", "front_desk", "staff"):
        if not announcement.is_org_wide and announcement.branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Cannot preview announcements outside your assigned branch.",
            )

    return announcement


def get_public_announcements(
    db: Session,
    branch_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
) -> List[Announcement]:
    """
    Retrieve publicly accessible announcements.
    Excludes drafts, archived, expired, and non-public audience notices.
    """
    now = datetime.now(timezone.utc)
    query = (
        db.query(Announcement)
        .filter(Announcement.status == "published")
        .filter(Announcement.audience == "public")
        .filter(Announcement.published_at <= now)
        .filter(or_(Announcement.expires_at.is_(None), Announcement.expires_at > now))
    )

    if branch_id:
        query = query.filter(
            or_(Announcement.branch_id == branch_id, Announcement.is_org_wide == True)
        )

    if category:
        query = query.filter(Announcement.category == category)

    return (
        query.order_by(
            Announcement.pinned.desc(),
            Announcement.published_at.desc(),
            Announcement.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_feed_announcements(
    db: Session,
    actor: User,
    branch_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
) -> List[Announcement]:
    """
    Retrieve authenticated user's personalized operational announcement feed.
    - Members: see 'public' and 'members_only' for their branch or org-wide.
    - Staff/Trainers: see 'public', 'members_only', and 'staff_only' for their branch or org-wide.
    - Managers/Admins: see all published notices for their branch scope.
    Excludes drafts and expired announcements.
    """
    now = datetime.now(timezone.utc)
    query = (
        db.query(Announcement)
        .filter(Announcement.status == "published")
        .filter(Announcement.published_at <= now)
        .filter(or_(Announcement.expires_at.is_(None), Announcement.expires_at > now))
    )

    # Audience filtering
    if actor.role == "member":
        query = query.filter(Announcement.audience.in_(["public", "members_only"]))
    elif actor.role in ("front_desk", "staff", "trainer"):
        query = query.filter(Announcement.audience.in_(["public", "members_only", "staff_only"]))

    # Branch scoping
    if actor.role in ("member", "front_desk", "staff", "trainer", "branch_manager", "manager"):
        user_branch = actor.branch_id
        query = query.filter(
            or_(Announcement.branch_id == user_branch, Announcement.is_org_wide == True)
        )
    elif actor.role in ("org_admin", "admin"):
        if branch_id:
            query = query.filter(
                or_(Announcement.branch_id == branch_id, Announcement.is_org_wide == True)
            )

    if category:
        query = query.filter(Announcement.category == category)

    return (
        query.order_by(
            Announcement.pinned.desc(),
            Announcement.published_at.desc(),
            Announcement.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_admin_announcements_list(
    db: Session,
    actor: User,
    status_filter: Optional[str] = None,
    branch_id: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Announcement]:
    """
    Retrieve announcements for management and staff operational oversight.
    Enforces branch boundaries for branch managers and staff.
    """
    if actor.role == "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Member role cannot access administrative announcement lists.",
        )

    query = db.query(Announcement)

    # Branch isolation for managers and front desk staff
    if actor.role in ("branch_manager", "manager", "front_desk", "staff"):
        if branch_id and branch_id != actor.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your administrative scope is restricted to your assigned branch.",
            )
        query = query.filter(
            or_(Announcement.branch_id == actor.branch_id, Announcement.is_org_wide == True)
        )
    elif actor.role in ("org_admin", "admin"):
        if branch_id:
            query = query.filter(
                or_(Announcement.branch_id == branch_id, Announcement.is_org_wide == True)
            )

    if status_filter:
        query = query.filter(Announcement.status == status_filter)

    if category:
        query = query.filter(Announcement.category == category)

    return (
        query.order_by(
            Announcement.pinned.desc(),
            Announcement.created_at.desc(),
        )
        .all()
    )
