from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, generate_uuid


class ContactInquiry(Base, TimestampMixin):
    """Prospective client and general member contact inquiries."""

    __tablename__ = "contact_inquiries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Status: 'new' | 'contacted' | 'closed'
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False, index=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
