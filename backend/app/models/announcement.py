from typing import Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Index, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.organization import Organization, Branch
    from backend.app.models.user import User


class Announcement(Base, TimestampMixin):
    """
    Facility and operational announcements, schedule alterations, competitions,
    and administrative notices published across the gym network.
    """

    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_org_wide: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Categories: 'general' | 'facility' | 'class_schedule' | 'competition' | 'maintenance' | 'policy' | 'emergency'
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False, index=True)

    # Priority: 'low' | 'normal' | 'high' | 'urgent'
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)

    # Status: 'draft' | 'published' | 'archived'
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)

    # Audience: 'public' | 'members_only' | 'staff_only'
    audience: Mapped[str] = mapped_column(String(30), default="public", nullable=False, index=True)

    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    author_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    branch: Mapped[Optional["Branch"]] = relationship("Branch")
    author: Mapped[Optional["User"]] = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        Index("ix_announcements_org_status_published", "organization_id", "status", "published_at"),
        Index("ix_announcements_branch_status", "branch_id", "status"),
        CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="chk_announcement_expiry_after_publish",
        ),
    )
