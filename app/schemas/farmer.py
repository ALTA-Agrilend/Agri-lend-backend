from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
import re


class FarmerRegistrationHub(BaseModel):
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1, max_length=255)
    national_id: str = Field(..., max_length=100)
    phone_number: str = Field(..., max_length=20)
    gps_coordinates: Optional[str] = Field(None, max_length=100)
    land_proof_document: Optional[str] = Field(None, max_length=500)
    crop_type: Optional[str] = Field(None, max_length=100)
    farm_size_hectares: Optional[Decimal] = None
    region: Optional[str] = Field(None, max_length=100)
    locale: str = Field("en", max_length=10)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+?[0-9]{7,15}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("crop_type")
    @classmethod
    def titlecase_crop(cls, v: str | None) -> str | None:
        if v:
            return v.strip().title()
        return v


class FarmerProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    national_id: str
    phone_number: str
    mobile_money_id: Optional[str]
    gps_coordinates: Optional[str]
    land_proof_document: Optional[str]
    consent_status: bool
    consent_date: Optional[datetime]
    locale: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FarmerListResponse(BaseModel):
    id: UUID
    full_name: str
    phone_number: str
    email: Optional[str] = None
    region: Optional[str] = None
    primary_crop: Optional[str] = None
    consent_status: bool
    locale: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FarmParcelCreate(BaseModel):
    farmer_id: UUID
    parcel_name: str = Field(..., min_length=1, max_length=255)
    size_hectares: Decimal = Field(..., gt=0)
    primary_crop: str = Field(..., max_length=100)
    region: str = Field(..., max_length=100)

    @field_validator("primary_crop")
    @classmethod
    def titlecase_crop(cls, v: str) -> str:
        return v.strip().title()


class FarmParcelResponse(BaseModel):
    id: UUID
    farmer_id: UUID
    parcel_name: str
    size_hectares: Decimal
    primary_crop: str
    region: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsentRequest(BaseModel):
    consent: bool


class ExplainabilityResponse(BaseModel):
    farmer_id: UUID
    score_value: int
    risk_tier: str
    summary: str
    top_factors: list[dict]


class FarmStatusResponse(BaseModel):
    farmer_id: UUID
    ndvi_current: Optional[float]
    ndvi_trend: list[dict]
    crop_health_label: str
