from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.db.session import get_db
from app.schemas.farmer import (
    FarmerRegistrationHub, FarmerProfileResponse, FarmerListResponse, FarmParcelCreate, FarmParcelResponse,
    ConsentRequest, FarmStatusResponse,
)
from app.schemas.credit import CreditScoreHistoryResponse, ExplainabilityResponse
from app.schemas import PaginatedResponse
from app.services.farmer import FarmerService
from app.services.credit import CreditService
from app.core.dependencies import (
    get_current_user,
    get_optional_user,
    get_scope_bank_id,
    require_roles,
)

router = APIRouter(prefix="/farmers", tags=["Farmers"])


@router.post("/register", status_code=201,
             summary="Register a new farmer",
             description="Creates a farmer user, profile, and optionally a farm parcel in a single transaction. "
                         "When called by a bank user, the farmer is linked to that institution for data scoping.")
async def register_hub(
    data: FarmerRegistrationHub,
    db: AsyncSession = Depends(get_db),
    current_user: dict | None = Depends(get_optional_user),
):
    service = FarmerService(db)
    registered_by_bank_id = get_scope_bank_id(current_user) if current_user else None
    try:
        profile, parcel = await service.register_hub(data, registered_by_bank_id=registered_by_bank_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "farmer_id": profile.id,
        "full_name": profile.full_name,
        "parcel_id": str(parcel.id) if parcel else None,
        "registered_by_bank_id": str(registered_by_bank_id) if registered_by_bank_id else None,
        "detail": "Farmer registered successfully",
    }


@router.get("/", response_model=PaginatedResponse[FarmerListResponse],
            summary="List all farmers (admin)",
            description="Returns a paginated list of all registered farmers. Requires Platform Admin role.",
            responses={403: {"description": "Insufficient permissions"}})
async def list_farmers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    region: Optional[str] = Query(None, description="Filter by region"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = FarmerService(db)
    return await service.list_farmers(page=page, page_size=page_size, region=region)


@router.get("/search",
            summary="Search farmers",
            description="Search farmers by name, phone, national ID, or email. Bank users only see farmers "
                        "registered by their institution or those with loan applications to it.",
            responses={403: {"description": "Insufficient permissions"}})
async def search_farmers(
    q: str = Query("", description="Search query"),
    region: Optional[str] = Query(None, description="Filter by region"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = FarmerService(db)
    return await service.search(
        q=q, region=region, limit=limit, bank_id=get_scope_bank_id(current_user)
    )


@router.get("/profile/{farmer_id}", response_model=FarmerProfileResponse,
            summary="Get farmer profile by ID",
            description="Returns the full profile for a given farmer.",
            responses={404: {"description": "Farmer not found"}})
async def get_profile(farmer_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = FarmerService(db)
    profile = await service.get_profile(farmer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return profile


@router.get("/me", response_model=FarmerProfileResponse,
            summary="Get own farmer profile",
            description="Returns the authenticated farmer's own profile.")
async def get_my_profile(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = FarmerService(db)
    profile = await service.get_profile_by_user(current_user["sub"])
    if not profile:
        raise HTTPException(status_code=404, detail="Farmer profile not found")
    return profile


@router.post("/consent", response_model=FarmerProfileResponse,
             summary="Set farmer consent",
             description="Grant or update data sharing consent for a farmer.",
             responses={404: {"description": "Farmer not found"}})
async def set_consent(
    farmer_id: str,
    data: ConsentRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    service = FarmerService(db)
    profile = await service.set_consent(farmer_id, data.consent)
    if not profile:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return profile


@router.post("/consent/revoke", response_model=FarmerProfileResponse,
             summary="Revoke farmer consent",
             description="Revoke data sharing consent for a farmer.",
             responses={404: {"description": "Farmer not found"}})
async def revoke_consent(
    farmer_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    service = FarmerService(db)
    profile = await service.set_consent(farmer_id, False)
    if not profile:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return profile


@router.post("/parcels", response_model=FarmParcelResponse, status_code=201,
             summary="Add a farm parcel",
             description="Register a new farm parcel for an existing farmer.")
async def create_parcel(
    data: FarmParcelCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Farmer", "Platform Admin")),
):
    service = FarmerService(db)
    return await service.add_parcel(data)


@router.get("/{farmer_id}/parcels", response_model=list[FarmParcelResponse],
            summary="List farmer's parcels",
            description="Returns all farm parcels for a given farmer.")
async def get_parcels(farmer_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = FarmerService(db)
    return await service.get_parcels(farmer_id)


@router.get("/{farmer_id}/credit-score",
            summary="Get farmer's full credit evaluation",
            description="Returns the complete credit evaluation exactly as received from the credit-score "
                        "calculator: final score, score range, geospatial sub-score, confidence rating, "
                        "categorical points breakdown, and raw extracted sub-scores. "
                        "Auto-refreshes from the scoring service if stored data is older than 24 hours.",
            responses={404: {"description": "No credit score found"}})
async def get_credit_score(farmer_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = CreditService(db)
    payload = await service.get_evaluation(farmer_id)
    if not payload:
        raise HTTPException(status_code=404, detail="No credit score found")
    return payload


@router.get("/{farmer_id}/credit-history",
            summary="Get credit score history",
            description="Returns paginated credit score history for a farmer.",
            responses={404: {"description": "Farmer not found"}})
async def get_credit_history(
    farmer_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    service = CreditService(db)
    scores, total = await service.get_score_history(farmer_id, page=page, page_size=page_size)
    trend = ""
    if scores and len(scores) >= 2:
        if scores[0].score_value > scores[-1].score_value:
            trend = "improving"
        elif scores[0].score_value < scores[-1].score_value:
            trend = "declining"
    return {
        "items": scores,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size),
        "trend": trend,
    }


@router.get("/{farmer_id}/explain", response_model=ExplainabilityResponse,
            summary="Explain credit score",
            description="Returns a farmer-readable explanation of why the credit score was assigned, including top contributing factors. Auto-refreshes score if stored data is older than 24 hours.",
            responses={404: {"description": "No credit score found"}})
async def explain_score(farmer_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    credit_service = CreditService(db)
    score = await credit_service.get_valid_score(farmer_id)
    if not score:
        raise HTTPException(status_code=404, detail="No credit score found")
    return await credit_service.get_explainability(farmer_id, score)


@router.get("/{farmer_id}/farm-status", response_model=FarmStatusResponse,
            summary="Get farm status (NDVI)",
            description="Returns current NDVI, trend data, and crop health label for the farmer's land.")
async def get_farm_status(farmer_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = FarmerService(db)
    return await service.get_farm_status(farmer_id)
