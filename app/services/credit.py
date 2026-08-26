import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func as sa_func
from app.models.credit import CreditScoreRecord
from app.schemas.credit import ExplainabilityResponse, CategoricalPointsBreakdown
from app.core.config import settings


class CreditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def build_evaluation_payload(score, farmer_id: str, crop_type: str = "") -> dict:
        """Canonical credit-evaluation contract — mirrors the scoring service response:
        {response_id, farmer_id, crop_type, credit_evaluation, categorical_points_breakdown,
         raw_extracted_sub_scores}."""
        import json as _json

        def _load(raw):
            if not raw:
                return {}
            try:
                return _json.loads(raw)
            except (ValueError, TypeError):
                return {}

        is_amanuel = (score.model_version or "").startswith("amanuel")
        conf = float(score.confidence_rating or 0)
        return {
            "response_id": str(score.id),
            "farmer_id": farmer_id,
            "crop_type": crop_type,
            "credit_evaluation": {
                "target_crop": crop_type,
                "final_credit_score": score.score_value,
                "score_range": "300-850" if is_amanuel else "300-1000",
                "raw_geospatial_score_out_of_100": round(float(score.geospatial_score or 0), 2),
                "confidence_rating": {
                    "confidence_percentage": round(conf * 100, 2),
                    "tier": "HIGH" if conf >= 0.75 else ("MEDIUM" if conf >= 0.5 else "LOW"),
                },
            },
            "categorical_points_breakdown": _load(score.categorical_breakdown),
            "raw_extracted_sub_scores": _load(score.raw_sub_scores),
        }

    async def get_evaluation(self, farmer_id: str) -> dict | None:
        """Latest stored evaluation in canonical payload form."""
        from sqlalchemy import select
        from app.models.farmer import FarmParcel

        score = await self.get_latest_score(farmer_id)
        if not score:
            return None
        parcel_result = await self.db.execute(
            select(FarmParcel).where(FarmParcel.farmer_id == farmer_id).limit(1)
        )
        parcel = parcel_result.scalar_one_or_none()
        crop_type = parcel.primary_crop if parcel else ""
        return self.build_evaluation_payload(score, farmer_id, crop_type)

    async def get_latest_score(self, farmer_id: str) -> CreditScoreRecord | None:
        result = await self.db.execute(
            select(CreditScoreRecord)
            .where(CreditScoreRecord.farmer_id == farmer_id)
            .order_by(desc(CreditScoreRecord.calculated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_valid_score(self, farmer_id: str) -> CreditScoreRecord | None:
        latest = await self.get_latest_score(farmer_id)
        if latest and not self._is_expired(latest):
            return latest
        from app.services.brain import BrainService
        brain = BrainService(self.db)
        return await brain.trigger_score_calculation(farmer_id)

    @staticmethod
    def _is_expired(record: CreditScoreRecord) -> bool:
        if not record.calculated_at:
            return True
        calced = record.calculated_at
        if calced.tzinfo is None:
            calced = calced.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - calced
        return age > timedelta(hours=settings.credit_score_expiry_hours)

    async def get_score_history(self, farmer_id: str, page: int = 1, page_size: int = 20) -> tuple[list[CreditScoreRecord], int]:
        count_q = await self.db.execute(
            select(sa_func.count(CreditScoreRecord.id))
            .where(CreditScoreRecord.farmer_id == farmer_id)
        )
        total = count_q.scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(CreditScoreRecord)
            .where(CreditScoreRecord.farmer_id == farmer_id)
            .order_by(desc(CreditScoreRecord.calculated_at))
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_explainability(self, farmer_id: str, score: CreditScoreRecord) -> ExplainabilityResponse:
        categorical_breakdown = None
        if score.categorical_breakdown:
            try:
                raw = json.loads(score.categorical_breakdown)
                categorical_breakdown = CategoricalPointsBreakdown(**raw)
            except Exception:
                pass

        if categorical_breakdown:
            cats = categorical_breakdown
            factors = [
                {"name": "Track record", "importance": 0.30, "value": round(cats.track_record_30pct.points_earned, 2), "max": cats.track_record_30pct.max_points},
                {"name": "Current cycle viability", "importance": 0.30, "value": round(cats.current_cycle_viability_30pct.points_earned, 2), "max": cats.current_cycle_viability_30pct.max_points},
                {"name": "Environmental exposure", "importance": 0.25, "value": round(cats.environmental_exposure_25pct.points_earned, 2), "max": cats.environmental_exposure_25pct.max_points},
                {"name": "Structural land security", "importance": 0.15, "value": round(cats.structural_land_security_15pct.points_earned, 2), "max": cats.structural_land_security_15pct.max_points},
            ]
            summary = (
                f"Your credit score is {score.score_value} ({score.risk_tier.value}). "
                f"Track record contributed {cats.track_record_30pct.points_earned:.1f}/{cats.track_record_30pct.max_points:.0f} points, "
                f"current cycle viability contributed {cats.current_cycle_viability_30pct.points_earned:.1f}/{cats.current_cycle_viability_30pct.max_points:.0f}, "
                f"environmental exposure contributed {cats.environmental_exposure_25pct.points_earned:.1f}/{cats.environmental_exposure_25pct.max_points:.0f}, "
                f"and structural land security contributed {cats.structural_land_security_15pct.points_earned:.1f}/{cats.structural_land_security_15pct.max_points:.0f}."
            )
        else:
            factors = [
                {"name": "Geospatial (NDVI)", "importance": 0.35, "value": f"{score.geospatial_score:.2f}"},
                {"name": "Sales & payment history", "importance": 0.35, "value": f"{score.transactional_score:.2f}"},
                {"name": "Mobile money activity", "importance": 0.20, "value": f"{score.alternative_score:.2f}"},
                {"name": "Climate resilience", "importance": 0.10, "value": f"{score.alternative_score:.2f}"},
            ]
            summary = (
                f"Your credit score is {score.score_value} ({score.risk_tier.value}). "
                f"The main factors are your satellite crop health data and sales history."
            )

        return ExplainabilityResponse(
            farmer_id=farmer_id,
            score_value=score.score_value,
            risk_tier=score.risk_tier.value,
            summary=summary,
            top_factors=factors,
            categorical_breakdown=categorical_breakdown,
        )
