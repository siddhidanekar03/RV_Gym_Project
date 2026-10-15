from typing import Optional, List
from datetime import datetime, timezone
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_CATEGORIES = {
    "general",
    "facility",
    "class_schedule",
    "competition",
    "maintenance",
    "policy",
    "emergency",
}

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
VALID_STATUSES = {"draft", "published", "archived"}
VALID_AUDIENCES = {"public", "members_only", "staff_only"}


class AnnouncementBase(BaseModel):
    """Core announcement schema with comprehensive field-level validation."""

    title: str = Field(..., min_length=3, max_length=255, description="Announcement headline")
    body: str = Field(..., min_length=5, max_length=10000, description="Full markdown or text body")
    category: str = Field("general", description="Category of the operational notice")
    priority: str = Field("normal", description="Display priority: low, normal, high, urgent")
    audience: str = Field("public", description="Visibility audience: public, members_only, staff_only")
    branch_id: Optional[str] = Field(None, max_length=50, description="Target branch identifier if branch-specific")
    is_org_wide: bool = Field(False, description="Whether announcement applies organization-wide across all branches")
    pinned: bool = Field(False, description="Pin announcement to top of feed")
    image_url: Optional[str] = Field(None, max_length=500, description="Optional banner or media image URL")
    publish_at: Optional[datetime] = Field(None, description="Scheduled publication timestamp (UTC)")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp after which notice is hidden (UTC)")

    @field_validator("title", "body", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Field cannot be empty or purely whitespace.")
            return v_stripped
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {sorted(list(VALID_CATEGORIES))}")
        return v_clean

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in VALID_PRIORITIES:
            raise ValueError(f"Priority must be one of: {sorted(list(VALID_PRIORITIES))}")
        return v_clean

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in VALID_AUDIENCES:
            raise ValueError(f"Audience must be one of: {sorted(list(VALID_AUDIENCES))}")
        return v_clean

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip()
        if not v_clean:
            return None
        # Disallow unsafe URI schemes
        lower_v = v_clean.lower()
        if lower_v.startswith(("javascript:", "data:", "vbscript:", "file:")):
            raise ValueError("Unsafe image URL protocol provided.")
        # Allow relative paths like /uploads/... or http/https URLs
        if not (lower_v.startswith("http://") or lower_v.startswith("https://") or lower_v.startswith("/")):
            raise ValueError("image_url must be an absolute HTTP/HTTPS URL or safe relative /uploads path.")
        return v_clean

    @model_validator(mode="after")
    def validate_dates_and_scope(self) -> "AnnouncementBase":
        # Validate that expires_at > publish_at if both present
        pub = self.publish_at
        exp = self.expires_at
        if pub and exp:
            # Ensure timezone-aware comparison
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= pub:
                raise ValueError("expires_at must be strictly later than publish_at.")

        # Ensure branch consistency
        if self.is_org_wide and self.branch_id:
            # When marked org-wide, branch_id is cleared or neutralized
            self.branch_id = None

        return self


class AnnouncementCreate(AnnouncementBase):
    """Request payload for creating a new announcement."""
    status: Optional[str] = Field("draft", description="Initial status: draft, published, archived")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> str:
        if v is None:
            return "draft"
        v_clean = v.strip().lower()
        if v_clean not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {sorted(list(VALID_STATUSES))}")
        return v_clean


class AnnouncementUpdate(BaseModel):
    """Request payload for modifying an existing announcement."""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    body: Optional[str] = Field(None, min_length=5, max_length=10000)
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    audience: Optional[str] = None
    branch_id: Optional[str] = None
    is_org_wide: Optional[bool] = None
    pinned: Optional[bool] = None
    image_url: Optional[str] = None
    publish_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {sorted(list(VALID_CATEGORIES))}")
        return v_clean

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in VALID_PRIORITIES:
            raise ValueError(f"Priority must be one of: {sorted(list(VALID_PRIORITIES))}")
        return v_clean

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {sorted(list(VALID_STATUSES))}")
        return v_clean

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip().lower()
        if v_clean not in VALID_AUDIENCES:
            raise ValueError(f"Audience must be one of: {sorted(list(VALID_AUDIENCES))}")
        return v_clean

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip()
        if not v_clean:
            return None
        lower_v = v_clean.lower()
        if lower_v.startswith(("javascript:", "data:", "vbscript:", "file:")):
            raise ValueError("Unsafe image URL protocol provided.")
        if not (lower_v.startswith("http://") or lower_v.startswith("https://") or lower_v.startswith("/")):
            raise ValueError("image_url must be an absolute HTTP/HTTPS URL or safe relative /uploads path.")
        return v_clean


class AnnouncementPublishRequest(BaseModel):
    """Optional payload when publishing or scheduling an announcement."""
    publish_at: Optional[datetime] = Field(None, description="Publication timestamp; defaults to now if omitted")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp; must be after publish_at")


class AnnouncementResponse(BaseModel):
    """Structured response entity for announcements with camelCase frontend mapping."""
    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    branch_id: Optional[str] = Field(None, serialization_alias="branchId")
    branch_name: Optional[str] = Field(None, serialization_alias="branchName")
    is_org_wide: bool = Field(..., serialization_alias="isOrgWide")
    title: str
    body: str
    category: str
    priority: str
    status: str
    audience: str
    pinned: bool
    image_url: Optional[str] = Field(None, serialization_alias="imageUrl")
    author_id: Optional[str] = Field(None, serialization_alias="authorId")
    author_name: Optional[str] = Field(None, serialization_alias="authorName")
    published_at: Optional[datetime] = Field(None, serialization_alias="publishedAt")
    expires_at: Optional[datetime] = Field(None, serialization_alias="expiresAt")
    created_at: datetime = Field(..., serialization_alias="createdAt")
    updated_at: datetime = Field(..., serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AnnouncementListResponse(BaseModel):
    """Paginated or listed response container for announcements."""
    announcements: List[AnnouncementResponse]
    total: int
