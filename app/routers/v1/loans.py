from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from decimal import Decimal
from app.db.session import get_db
from app.schemas.loan import (
    LoanApplicationCreate, LoanApplicationResponse, LoanReviewRequest,
    LoanListFilter, ApplicantDetailResponse, DashboardReportResponse,
    RiskHeatmapPoint, HighRiskLoanWarning,
)
from app.models.loan import LoanStatus
from app.services.loan import LoanService
from app.services.credit import CreditService
from app.core.dependencies import get_current_user, get_scope_bank_id, require_roles

router = APIRouter(prefix="/loans", tags=["Loans"])


@router.post("/", response_model=LoanApplicationResponse, status_code=201,
             summary="Create a loan application",
             description="Submit a new loan application. Snapshots the farmer's current credit score at submission time.",
             responses={403: {"description": "Insufficient permissions"}})
async def create_loan(
    data: LoanApplicationCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Farmer", "Platform Admin")),
):
    credit_service = CreditService(db)
    latest = await credit_service.get_latest_score(str(data.farmer_id))
    score = latest.score_value if latest else 300
    loan_service = LoanService(db)
    return await loan_service.create_application(data, score)


@router.get("/",
            summary="List loan applications",
            description="Returns filtered and paginated loan applications with farmer details. "
                        "Bank users only see applications submitted to their institution.")
async def list_loans(
    farmer_id: Optional[str] = Query(None, description="Filter by farmer ID"),
    status: Optional[LoanStatus] = Query(None, description="Filter by status (PENDING/APPROVED/REJECTED/DISBURSED)"),
    region: Optional[str] = Query(None, description="Filter by region"),
    crop_type: Optional[str] = Query(None, description="Filter by crop type"),
    min_amount: Optional[Decimal] = Query(None, description="Minimum loan amount"),
    max_amount: Optional[Decimal] = Query(None, description="Maximum loan amount"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    filters = LoanListFilter(
        status=status, region=region, crop_type=crop_type,
        min_amount=min_amount, max_amount=max_amount,
        page=page, page_size=page_size,
    )
    service = LoanService(db)
    return await service.get_filtered_applications(filters, bank_id=get_scope_bank_id(current_user))


@router.get("/reports/dashboard", response_model=DashboardReportResponse,
            summary="Loan dashboard report",
            description="Returns aggregated counts of loans by status. Requires Bank Analyst or higher.",
            responses={403: {"description": "Insufficient permissions"}})
async def dashboard_report(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = LoanService(db)
    return await service.get_dashboard_report(bank_id=get_scope_bank_id(current_user))


@router.get("/reports/high-risk", response_model=list[HighRiskLoanWarning],
            summary="High-risk loan warnings",
            description="Returns pending loans with credit scores below 500 (high risk).",
            responses={403: {"description": "Insufficient permissions"}})
async def high_risk_warnings(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = LoanService(db)
    return await service.get_high_risk_warnings(bank_id=get_scope_bank_id(current_user))


@router.get("/reports/heatmap", response_model=list[RiskHeatmapPoint],
            summary="Risk heatmap data",
            description="Returns GeoJSON risk heatmap data aggregated by region/crop. Falls back to mock data if Amanuel's service is unreachable.",
            responses={403: {"description": "Insufficient permissions"}})
async def risk_heatmap(
    region: Optional[str] = Query(None, description="Filter by region"),
    crop_type: Optional[str] = Query(None, description="Filter by crop type"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    from app.services.scoring import ScoringService
    try:
        scoring = ScoringService()
        data = await scoring.get_heatmap_data({"region": region or "", "crop_type": crop_type or ""})
        return data.get("points", [])
    except Exception:
        return [
            {"lat": 9.0, "lng": 38.7, "risk_tier": "MEDIUM", "farmer_count": 45, "avg_score": 580.0, "region": "Oromia"},
            {"lat": 8.5, "lng": 39.2, "risk_tier": "LOW", "farmer_count": 30, "avg_score": 720.0, "region": "SNNPR"},
        ]


@router.get("/{app_id}",
            summary="Get loan application",
            description="Returns a single loan application by ID.",
            responses={404: {"description": "Loan application not found"}})
async def get_loan_status(app_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = LoanService(db)
    app = await service.get_by_id(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return app


@router.get("/{app_id}/detail",
            summary="Applicant full credit report",
            description="Returns detailed credit report for a loan applicant including score, trend, consent, and land verification status.",
            responses={404: {"description": "Loan application not found"}})
async def applicant_detail(app_id: str, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_user)):
    service = LoanService(db)
    detail = await service.get_applicant_detail(app_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return detail


@router.patch("/{app_id}/review", response_model=LoanApplicationResponse,
              summary="Review a loan application",
              description="Approve, reject, or mark a loan as disbursed. Requires Loan Officer, Bank Analyst, or Platform Admin.",
              responses={403: {"description": "Insufficient permissions"}, 404: {"description": "Loan application not found"}})
async def review_loan(
    app_id: str,
    data: LoanReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Loan Officer", "Bank Analyst", "Platform Admin")),
):
    service = LoanService(db)
    app = await service.review_application(app_id, data.status, current_user["sub"])
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return app
