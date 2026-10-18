from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, field_validator
from backend.app.core.validation import validate_and_normalize_phone


class WebsiteContentUpdate(BaseModel):
    data: Dict[str, Any] = Field(..., description="Key-value content payload for section")


class EquipmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    category: str = Field(..., min_length=2, max_length=50)
    spec: str = Field(..., min_length=2)
    brand_model: Optional[str] = Field(None, max_length=100)
    branch_id: str = Field("narsobawadi", max_length=50)
    primary_image_url: Optional[str] = Field(None, max_length=500)
    images: List[str] = Field(default_factory=list)
    is_published: bool = True
    display_order: int = 0


class EquipmentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    spec: Optional[str] = Field(None, min_length=2)
    brand_model: Optional[str] = Field(None, max_length=100)
    branch_id: Optional[str] = Field(None, max_length=50)
    primary_image_url: Optional[str] = Field(None, max_length=500)
    images: Optional[List[str]] = None
    is_published: Optional[bool] = None
    display_order: Optional[int] = None


class GalleryCreateRequest(BaseModel):
    zone: str = Field(..., min_length=2, max_length=100)
    description: str = Field(..., min_length=2)
    image_url: str = Field(..., min_length=2, max_length=500)
    status: str = Field("In Active Use", max_length=50)
    branch_id: str = Field("narsobawadi", max_length=50)
    is_published: bool = True
    display_order: int = 0


class GalleryUpdateRequest(BaseModel):
    zone: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, min_length=2)
    image_url: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, max_length=50)
    branch_id: Optional[str] = Field(None, max_length=50)
    is_published: Optional[bool] = None
    display_order: Optional[int] = None


class CoachCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8)
    phone: Optional[str] = Field(None, max_length=50)
    branch_id: str = Field("narsobawadi", max_length=50)
    specialization: str = Field("Strength & Conditioning Coach", max_length=100)
    bio: Optional[str] = None
    certifications: List[str] = Field(default_factory=list)
    experience_years: int = Field(1, ge=0, le=50)
    max_clients: int = Field(20, ge=1, le=100)
    is_accepting_clients: bool = True
    photo_url: Optional[str] = Field(None, max_length=500)

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_and_normalize_phone(v, required=False, field_name="phone")


class CoachUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = Field(None, max_length=50)
    branch_id: Optional[str] = Field(None, max_length=50)
    specialization: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = None
    certifications: Optional[List[str]] = None
    experience_years: Optional[int] = Field(None, ge=0, le=50)
    max_clients: Optional[int] = Field(None, ge=1, le=100)
    is_accepting_clients: Optional[bool] = None
    is_active: Optional[bool] = None
    photo_url: Optional[str] = Field(None, max_length=500)

    @field_validator("phone")
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        return validate_and_normalize_phone(v, required=False, field_name="phone")


class PlanCreateRequest(BaseModel):
    id: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    category: str = Field("general", max_length=50)
    access_scope: str = Field("single_branch", max_length=50)
    price: Decimal = Field(..., ge=0)
    currency: str = Field("₹", max_length=10)
    billing_cycle: str = Field("per month", max_length=50)
    duration_days: int = Field(30, ge=1)
    is_featured: bool = False
    is_active: bool = True
    description: Optional[str] = None
    perks: List[str] = Field(default_factory=list)


class PlanUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    access_scope: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    billing_cycle: Optional[str] = Field(None, max_length=50)
    duration_days: Optional[int] = Field(None, ge=1)
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    perks: Optional[List[str]] = None
