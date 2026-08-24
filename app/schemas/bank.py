from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class BankPartnerCreate(BaseModel):
    """Admin form payload: creates the institution plus its single analyst login."""
    bank_name: str = Field(..., min_length=2, max_length=255)
    interest_rate: float = Field(..., gt=0, le=100, description="Annual interest rate percentage applied to approved loans")
    subscription_tier: str = Field("standard", max_length=50)
    analyst_full_name: str = Field(..., min_length=2, max_length=255)
    analyst_email: str = Field(..., max_length=255)
    analyst_password: str = Field(..., min_length=6)

    @field_validator("analyst_email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("must be a valid email address")
        return v


class BankPartnerResponse(BaseModel):
    id: UUID
    bank_name: str
    interest_rate: Optional[float] = None
    subscription_tier: str
    is_active: bool
    onboarding_date: datetime

    model_config = {"from_attributes": True}


class BankSettingsUpdate(BaseModel):
    """Banks cannot rename their institution; only pricing is self-service."""
    interest_rate: Optional[float] = Field(None, gt=0, le=100)