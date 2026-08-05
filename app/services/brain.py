import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.credit import CreditScoreRecord, RiskTier
from app.models.satellite import SatelliteObservation
from app.services.scoring import ScoringService
from app.services.geospatial import GeospatialService
from datetime import datetime, timezone
from decimal import Decimal


class BrainService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def trigger_score_calculation(self, farmer_id: str) -> CreditScoreRecord | None:
        farmer_result = await self.db.execute(
            select(FarmerProfile).where(FarmerProfile.id == farmer_id)
        )
        farmer = farmer_result.scalar_one_or_none()
        if not farmer:
            return None

        parcel_result = await self.db.execute(
            select(FarmParcel).where(FarmParcel.farmer_id == farmer_id).limit(1)
        )
        parcel = parcel_result.scalar_one_or_none()

        ndvi_values = []
        if parcel:
            obs_result = await self.db.execute(
                select(SatelliteObservation)
                .where(SatelliteObservation.parcel_id == parcel.id)
                .order_by(SatelliteObservation.observation_date.desc())
                .limit(10)
            )
            observations = obs_result.scalars().all()
            ndvi_values = [float(o.ndvi_value) for o in observations if o.ndvi_value is not None]

        categorical_breakdown = None
        raw_sub_scores = None

        try:
            scoring = ScoringService()
            polygon = None
            if parcel and parcel.location_polygon:
                try:
                    polygon = json.loads(parcel.location_polygon)
                except (json.JSONDecodeError, TypeError):
                    polygon = parcel.location_polygon
            crop_type = parcel.primary_crop if parcel else ""
            ai_result = await scoring.get_credit_score(str(farmer_id), polygon, crop_type)

            ce = ai_result["credit_evaluation"]
            score_value = ce["final_credit_score"]
            risk_tier = BrainService._tier_from_score(score_value)
            geo_score = Decimal(str(round(ce["raw_geospatial_score_out_of_100"], 2)))
            confidence = Decimal(str(round(ce["confidence_rating"]["confidence_percentage"] / 100, 2)))
            model_ver = "amanuel-v1"
            categorical_breakdown = json.dumps(ai_result.get("categorical_points_breakdown"))
            raw_sub_scores = json.dumps(ai_result.get("raw_extracted_sub_scores"))

        except Exception:
            if ndvi_values:
                avg = sum(ndvi_values) / len(ndvi_values)
                if avg < 0.3:
                    score_value = 350
                    risk_tier = RiskTier.HIGH
                elif avg < 0.5:
                    score_value = 550
                    risk_tier = RiskTier.MEDIUM
                else:
                    score_value = 720
                    risk_tier = RiskTier.LOW
            else:
                score_value = 500
                risk_tier = RiskTier.MEDIUM
            geo_score = Decimal("0.0")
            confidence = Decimal("0.85")
            model_ver = "fallback-ndvi"

        record = CreditScoreRecord(
            farmer_id=farmer_id,
            score_value=score_value,
            risk_tier=risk_tier,
            geospatial_score=geo_score,
            transactional_score=Decimal("0.0"),
            alternative_score=Decimal("0.0"),
            model_version=model_ver,
            confidence_rating=confidence,
            calculated_at=datetime.now(timezone.utc),
            categorical_breakdown=categorical_breakdown,
            raw_sub_scores=raw_sub_scores,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def trigger_for_all_farmers(self) -> list[CreditScoreRecord]:
        result = await self.db.execute(select(FarmerProfile))
        farmers = result.scalars().all()
        records = []
        for farmer in farmers:
            record = await self.trigger_score_calculation(str(farmer.id))
            if record:
                records.append(record)
        return records

    @staticmethod
    def _tier_from_score(score: int) -> RiskTier:
        if score >= 650:
            return RiskTier.LOW
        elif score >= 500:
            return RiskTier.MEDIUM
        return RiskTier.HIGH

    @staticmethod
    def get_risk_tier_detail(score: int, risk_tier: RiskTier) -> dict:
        ranges = {
            RiskTier.LOW: {"label": "Low Risk", "min": 50000, "max": 200000},
            RiskTier.MEDIUM: {"label": "Medium Risk", "min": 10000, "max": 50000},
            RiskTier.HIGH: {"label": "High Risk", "min": 0, "max": 10000},
        }
        info = ranges[risk_tier]
        return {
            "score_value": score,
            "risk_tier": risk_tier.value,
            "label": info["label"],
            "recommended_loan_min": info["min"],
            "recommended_loan_max": info["max"],
            "contributing_factors": [
                {"factor": "Track record (30%)", "weight": "30%"},
                {"factor": "Current cycle viability (30%)", "weight": "30%"},
                {"factor": "Environmental exposure (25%)", "weight": "25%"},
                {"factor": "Structural land security (15%)", "weight": "15%"},
            ],
        }

    async def handle_satellite_ingestion_webhook(self, parcel_id: str) -> dict:
        parcel_result = await self.db.execute(
            select(FarmParcel).where(FarmParcel.id == parcel_id)
        )
        parcel = parcel_result.scalar_one_or_none()
        if not parcel:
            return {"detail": "Parcel not found"}
        geo = GeospatialService()
        try:
            ndvi_data = await geo.get_ndvi_timeseries(parcel_id, days=1)
            if ndvi_data:
                latest = ndvi_data[-1]
                obs = SatelliteObservation(
                    parcel_id=parcel_id,
                    observation_date=datetime.now(timezone.utc).date(),
                    ndvi_value=Decimal(str(latest.get("ndvi_value", 0))),
                    cloud_cover_pct=Decimal(str(latest.get("cloud_cover", 0))),
                    data_source=latest.get("source", "Sentinel-2"),
                )
                self.db.add(obs)
                await self.db.flush()
        except Exception:
            pass
        record = await self.trigger_score_calculation(str(parcel.farmer_id))
        return {
            "detail": "Satellite data ingested and score recalculated",
            "parcel_id": parcel_id,
            "farmer_id": str(parcel.farmer_id),
            "new_score": record.score_value if record else None,
        }
