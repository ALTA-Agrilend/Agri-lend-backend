from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.credit import CreditScoreResponse
from app.services.brain import BrainService
from app.services.credit import CreditService
from app.core.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/brain", tags=["Brain Integration"])


@router.post("/trigger-score/{farmer_id}", response_model=CreditScoreResponse,
             summary="Trigger score calculation for a farmer",
             description="Triggers an on-demand credit score calculation for a specific farmer. Calls Amanuel's scoring service (or falls back to NDVI-based scoring).",
             responses={404: {"description": "Farmer not found"}})
async def trigger_score(
    farmer_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_roles("Platform Admin", "Risk Analyst"))],
):
    service = BrainService(db)
    record = await service.trigger_score_calculation(farmer_id)
    if not record:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return record


@router.post("/trigger-all",
             summary="Trigger score calculation for all farmers",
             description="Triggers credit score recalculation for every registered farmer. Requires Platform Admin.",
             responses={403: {"description": "Insufficient permissions"}})
async def trigger_all_scores(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_roles("Platform Admin"))],
):
    service = BrainService(db)
    records = await service.trigger_for_all_farmers()
    return {"detail": f"Scores calculated for {len(records)} farmers"}


@router.get("/evaluation/{farmer_id}",
            summary="Latest credit evaluation payload",
            description="Returns the farmer's most recent credit evaluation in the canonical scoring-service "
                        "response shape (credit_evaluation, categorical_points_breakdown, raw_extracted_sub_scores).",
            responses={404: {"description": "No credit score found"}})
async def credit_evaluation(
    farmer_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    import json as _json
    from app.models.farmer import FarmParcel
    from sqlalchemy import select

    credit = CreditService(db)
    score = await credit.get_latest_score(farmer_id)
    if not score:
        raise HTTPException(status_code=404, detail="No credit score found")

    parcel_result = await db.execute(
        select(FarmParcel).where(FarmParcel.farmer_id == farmer_id).limit(1)
    )
    parcel = parcel_result.scalar_one_or_none()

    def _load(raw):
        if not raw:
            return {}
        try:
            return _json.loads(raw)
        except (ValueError, TypeError):
            return {}

    is_amanuel = (score.model_version or "").startswith("amanuel")
    return {
        "response_id": str(score.id),
        "farmer_id": farmer_id,
        "crop_type": parcel.primary_crop if parcel else "",
        "credit_evaluation": {
            "target_crop": parcel.primary_crop if parcel else "",
            "final_credit_score": score.score_value,
            "score_range": "300-850" if is_amanuel else "300-1000",
            "raw_geospatial_score_out_of_100": float(score.geospatial_score or 0),
            "confidence_rating": {
                "confidence_percentage": round(float(score.confidence_rating or 0) * 100, 2),
                "tier": "HIGH" if (score.confidence_rating or 0) >= 0.75 else ("MEDIUM" if (score.confidence_rating or 0) >= 0.5 else "LOW"),
            },
        },
        "categorical_points_breakdown": _load(score.categorical_breakdown),
        "raw_extracted_sub_scores": _load(score.raw_sub_scores),
    }


@router.get("/risk-tier/{farmer_id}",
            summary="Get risk tier detail",
            description="Returns risk tier classification, contributing factors, and recommended loan range for a farmer. Auto-refreshes score if stored data is older than the expiry hours specified in the configuration.",
            responses={404: {"description": "No credit score found"}})
async def risk_tier_detail(
    farmer_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    credit = CreditService(db)
    score = await credit.get_valid_score(farmer_id)
    if not score:
        raise HTTPException(status_code=404, detail="No credit score found")
    return BrainService.get_risk_tier_detail(score.score_value, score.risk_tier)


@router.post("/webhook/satellite-ingestion",
             summary="Satellite ingestion webhook",
             description="Webhook endpoint called by Eyosiyas's pipeline when new satellite data is ingested for a parcel. Triggers score recalculation.")
async def satellite_ingestion_webhook(
    parcel_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = BrainService(db)
    return await service.handle_satellite_ingestion_webhook(parcel_id)


@router.get("/yield-prediction/{farmer_id}",
            summary="Get yield prediction [STUB]",
            description="**FLAGGED — confirm scope with team (FR-B-002).** Returns a stub yield prediction. Requires integration with Eyosiyas's crop yield model.",
            responses={404: {"description": "Farmer not found"}})
async def yield_prediction(
    farmer_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    from app.services.farmer import FarmerService
    service = FarmerService(db)
    profile = await service.get_profile(farmer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Farmer not found")
    parcels = await service.get_parcels(farmer_id)
    return {
        "farmer_id": farmer_id,
        "status": "stub",
        "note": "Yield prediction (FR-B-002) is flagged — confirm scope with team before implementing. Requires Eyosiyas's crop yield model integration.",
        "estimated_yield_quintals": None,
        "confidence": None,
        "crop_type": parcels[0].primary_crop if parcels else None,
        "farm_size_hectares": float(parcels[0].size_hectares) if parcels else None,
        "season": "2026/2027",
    }
