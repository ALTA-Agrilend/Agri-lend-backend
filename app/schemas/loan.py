from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.loan import LoanStatus


class LoanApplicationCreate(BaseModel):
    farmer_id: UUID
    bank_id: UUID
    requested_amount: Decimal
    loan_purpose: str


class LoanApplicationResponse(BaseModel):
    id: UUID
    farmer_id: UUID
    bank_id: UUID
    requested_amount: Decimal
    loan_purpose: str
    credit_score_at_application: int
    status: LoanStatus
    submitted_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[UUID]
    interest_rate_applied: Optional[Decimal] = None
    repayment_amount: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class LoanReviewRequest(BaseModel):
    status: LoanStatus


class LoanListFilter(BaseModel):
    status: Optional[LoanStatus] = None
    region: Optional[str] = None
    crop_type: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    page: int = 1
    page_size: int = 20


class ApplicantDetailResponse(BaseModel):
    application: LoanApplicationResponse
    farmer_name: str
    farmer_phone: str
    farmer_region: str
    farmer_crop: str
    farm_size_hectares: Optional[Decimal]
    credit_score_current: Optional[int]
    risk_tier: Optional[str]
    score_trend: str
    consent_status: bool
    land_verified: bool


class DashboardReportResponse(BaseModel):
    total: int
    approved: int
    rejected: int
    pending: int
    disbursed: int


class RiskHeatmapPoint(BaseModel):
    lat: float
    lng: float
    risk_tier: str
    farmer_count: int
    avg_score: float
    region: str


class HighRiskLoanWarning(BaseModel):
    application_id: UUID
    farmer_name: str
    amount: Decimal
    score: int
    risk_tier: str
    reason: str
