from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
import re


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def _require_identifier(self):
        if not self.email and not self.phone_number:
            raise ValueError("Provide either email or phone_number")
        return self


class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1, max_length=255)
    role_name: str = Field(..., max_length=50)
    phone_number: Optional[str] = Field(None, max_length=20)
    bank_id: Optional[UUID] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^\+?[0-9]{7,15}$", v):
            raise ValueError("Invalid phone number format")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    locale: Optional[str] = Field(None, max_length=10)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^\+?[0-9]{7,15}$", v):
            raise ValueError("Invalid phone number format")
        return v


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role_id: UUID
    role_name: Optional[str] = None
    bank_id: Optional[UUID] = None
    bank_name: Optional[str] = None
    bank_interest_rate: Optional[float] = None
    is_active: bool
    locale: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role_name: str
    is_active: bool
    locale: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleAssignment(BaseModel):
    role_name: str = Field(..., max_length=50)


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]

    model_config = {"from_attributes": True}
