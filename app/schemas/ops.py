from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class QueueItemResponse(BaseModel):
    id: UUID
    farmer_id: UUID
    full_name: str
    phone_number: str
    email: str
    national_id: str
    region: str
    primary_crop: str
    farm_size: Optional[float]
    gps_coordinates: Optional[str]
    score: Optional[int]
    risk_tier: Optional[str]
    status: str
    submitted_via: str
    submitted_at: datetime
    flag_reason: Optional[str]
    land_proof_document: Optional[str]
    consent_status: bool


class SupportTicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: str = "Telemetry"
    priority: str = "Medium"
    description: Optional[str] = None


class SupportTicketResponse(BaseModel):
    id: UUID
    title: str
    category: str
    priority: str
    status: str
    description: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class CommandExecuteRequest(BaseModel):
    command: str = Field(..., min_length=1)


class CommandExecuteResponse(BaseModel):
    status: str
    output: str


class CommandLogEntry(BaseModel):
    id: UUID
    command: str
    status: str
    output: Optional[str]
    executed_at: datetime

    model_config = {"from_attributes": True}


class SystemSettingsUpdate(BaseModel):
    site_name: Optional[str] = None
    environment: Optional[str] = None
    currency: Optional[str] = None
    min_credit_score_approval: Optional[str] = None
    max_loan_amount: Optional[str] = None
    default_loan_term_months: Optional[str] = None
    maintenance_mode: Optional[str] = None


class SystemSettingsResponse(BaseModel):
    settings: dict


class NotificationResponse(BaseModel):
    id: UUID
    role: str
    title: str
    message: str
    type: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskSimulationRequest(BaseModel):
    scenario: str = "drought"


class RiskSimulationResponse(BaseModel):
    name: str
    newCriticalPct: str
    pctChange: str
    atRiskCapital: str
    impactedCount: int
    ndviDrop: str
    recommendedAction: str


class PortfolioSegment(BaseModel):
    name: str
    exposure: float
    score: int
    trend: str
    status: str


class PortfolioSummary(BaseModel):
    approved_total: float
    pending_total: float
    at_risk_total: float
    recovery_rate: float
    holdings: list[dict]
    allocations: list[dict]
    segments: list[PortfolioSegment]
    activity: list[str]


class YieldForecastPoint(BaseModel):
    region: str
    crop: str
    predicted: float
    actual: float


class YieldForecastResponse(BaseModel):
    crop: str
    points: list[YieldForecastPoint]


class PipelineRunResponse(BaseModel):
    id: UUID
    pipeline_name: str
    status: str
    duration_seconds: float
    started_at: datetime

    model_config = {"from_attributes": True}