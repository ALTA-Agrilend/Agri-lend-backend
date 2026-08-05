from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.credit import RiskTier


class ConfidenceRating(BaseModel):
    confidence_percentage: float
    tier: str


class CreditEvaluation(BaseModel):
    target_crop: str
    final_credit_score: int
    score_range: str
    raw_geospatial_score_out_of_100: float
    confidence_rating: ConfidenceRating


class CategoricalBreakdownItem(BaseModel):
    points_earned: float
    max_points: float


class CategoricalPointsBreakdown(BaseModel):
    track_record_30pct: CategoricalBreakdownItem
    current_cycle_viability_30pct: CategoricalBreakdownItem
    environmental_exposure_25pct: CategoricalBreakdownItem
    structural_land_security_15pct: CategoricalBreakdownItem


class RawExtractedSubScores(BaseModel):
    peak_stability: float
    cropping_consistency: float
    growth_trajectory: float
    vai: float
    environmental_exposure: float
    slope: float
    water_proximity: float


class AmanuellScoreResponse(BaseModel):
    response_id: str
    farmer_id: str
    crop_type: str
    credit_evaluation: CreditEvaluation
    categorical_points_breakdown: CategoricalPointsBreakdown
    raw_extracted_sub_scores: RawExtractedSubScores


class CreditScoreResponse(BaseModel):
    id: UUID
    farmer_id: UUID
    score_value: int
    risk_tier: RiskTier
    model_version: str
    confidence_rating: Decimal
    calculated_at: datetime

    model_config = {"from_attributes": True}


class CreditScoreHistoryResponse(BaseModel):
    items: list[CreditScoreResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    trend: str


class ExplainabilityResponse(BaseModel):
    farmer_id: UUID
    score_value: int
    risk_tier: str
    summary: str
    top_factors: list[dict]
    categorical_breakdown: Optional[CategoricalPointsBreakdown] = None
