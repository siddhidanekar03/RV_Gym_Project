from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, Text, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from backend.app.models.organization import Branch
    from backend.app.models.user import User


class WebsiteContent(Base, TimestampMixin):
    """
    Persistent configurable content blocks for the public gym website,
    including homepage hero, facility overview, hours, and contact details.
    """

    __tablename__ = "website_content"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    section: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    branch_id: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    branch: Mapped[Optional["Branch"]] = relationship("Branch")
    updated_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by_id])


class EquipmentItem(Base, TimestampMixin):
    """
    Physical training equipment and apparatus inventory displayed on the public site
    with verified photos, category classification, and specifications.
    """

    __tablename__ = "equipment_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), default="narsobawadi", nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    spec: Mapped[str] = mapped_column(Text, nullable=False)
    brand_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    primary_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    images: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    branch: Mapped["Branch"] = relationship("Branch")


class GalleryItem(Base, TimestampMixin):
    """
    Facility floor photography and zone overview showcases displayed on the public site.
    """

    __tablename__ = "gallery_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    branch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("branches.id", ondelete="CASCADE"), default="narsobawadi", nullable=False, index=True
    )
    zone: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="In Active Use", nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    branch: Mapped["Branch"] = relationship("Branch")
