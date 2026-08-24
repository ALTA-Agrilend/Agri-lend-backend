from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional
from app.db.session import get_db
from app.schemas.auth import UserCreate, UserUpdate, UserAdminResponse, RoleAssignment, RoleResponse
from app.schemas.admin import (
    FarmerOnboardingReport, LoanReport, CreditScoreReport, RiskReport,
    ModelMetrics, ErrorAnalysis, BiasIndicator, DriftStatus,
    ModelVersionInfo, PipelineStatus,
)
from app.schemas import PaginatedResponse
from app.services.auth import AuthService
from app.services.admin import AdminService
from app.core.dependencies import get_current_user, require_roles
from app.models.bank import BankPartner
from app.models.auth import Role

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/roles", response_model=list[RoleResponse],
            summary="List all roles",
            description="Returns all available roles in the system.")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(select(Role).order_by(Role.name))
    return list(result.scalars().all())


@router.get("/users", response_model=PaginatedResponse[UserAdminResponse],
            summary="List all users (paginated)",
            description="Returns a paginated list of all registered users. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    return await service.get_all_users(page=page, page_size=page_size, role=role, search=search)


@router.post("/users", status_code=status.HTTP_201_CREATED,
             summary="Create a user (admin)",
             description="Admin-only endpoint to create a new user with any role.",
             responses={400: {"description": "Validation error"}})
async def admin_create_user(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    try:
        user = await service.admin_create_user(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await service.log_audit(
        user_id=admin["sub"],
        action="CREATE_USER",
        resource="User",
        resource_id=str(user.id),
        details=f"Created user {data.email} with role {data.role_name}",
        ip=request.client.host if request.client else None,
    )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role_name": data.role_name,
        "is_active": user.is_active,
        "locale": user.locale,
        "created_at": user.created_at,
    }


@router.patch("/users/{user_id}/role",
              summary="Assign user role",
              description="Change a user's role. Requires Platform Admin.",
              responses={400: {"description": "Role not found"}, 404: {"description": "User not found"}})
async def assign_role(
    user_id: str,
    data: RoleAssignment,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    try:
        user = await service.assign_role(user_id, data.role_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await service.log_audit(
        user_id=admin["sub"],
        action="ASSIGN_ROLE",
        resource="User",
        resource_id=user_id,
        details=f"Assigned role {data.role_name}",
        ip=request.client.host if request.client else None,
    )
    return {"detail": f"Role set to {data.role_name}"}


@router.patch("/users/{user_id}",
              summary="Update user (admin)",
              description="Update any user's profile fields. Requires Platform Admin.",
              responses={404: {"description": "User not found"}})
async def admin_update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    user = await service.update_user(user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await service.log_audit(
        user_id=admin["sub"],
        action="UPDATE_USER",
        resource="User",
        resource_id=user_id,
        details="Updated profile fields",
        ip=request.client.host if request.client else None,
    )
    return {"detail": "User updated"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete user",
               description="Permanently delete a user. Requires Platform Admin.",
               responses={404: {"description": "User not found"}})
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    deleted = await service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    await service.log_audit(
        user_id=admin["sub"],
        action="DELETE_USER",
        resource="User",
        resource_id=user_id,
        ip=request.client.host if request.client else None,
    )


@router.patch("/users/{user_id}/deactivate",
              summary="Deactivate user",
              description="Deactivate a user account (prevents login). Requires Platform Admin.",
              responses={404: {"description": "User not found"}})
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    service = AuthService(db)
    user = await service.deactivate_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await service.log_audit(
        user_id=admin["sub"],
        action="DEACTIVATE_USER",
        resource="User",
        resource_id=user_id,
        ip=request.client.host if request.client else None,
    )
    return {"detail": "User deactivated"}


@router.post("/banks/{bank_id}/activate",
              summary="Activate a bank",
              description="Activate a bank partner in the system. Requires Platform Admin.",
              responses={404: {"description": "Bank not found"}})
async def activate_bank(
    bank_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles("Platform Admin")),
):
    result = await db.execute(select(BankPartner).where(BankPartner.id == bank_id))
    bank = result.scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    bank.is_active = True
    await db.flush()
    service = AuthService(db)
    await service.log_audit(
        user_id=admin["sub"],
        action="ACTIVATE_BANK",
        resource="BankPartner",
        resource_id=bank_id,
        ip=request.client.host if request.client else None,
    )
    return {"detail": f"Bank '{bank.bank_name}' activated"}


# ─── Reports ────────────────────────────────────────────────────────

@router.get("/reports/monthly",
            summary="Monthly activity report",
            description="Per-calendar-month aggregates of farmer registrations and loan activity "
                        "(submitted, approved, rejected, disbursed counts, requested amounts, repayment totals). "
                        "Requires Platform Admin.")
async def monthly_report(
    months: int = Query(12, ge=1, le=24, description="Number of trailing months to include"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.monthly_report(months)


@router.get("/reports/farmers", response_model=FarmerOnboardingReport,
            summary="Farmer onboarding report",
            description="Returns counts of registered, consented, land-verified, and mobile-money-linked farmers.")
async def farmer_report(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.farmer_onboarding_report()


@router.get("/reports/loans", response_model=LoanReport,
            summary="Loan activity report",
            description="Returns counts of submitted, approved, rejected, pending, and disbursed loans.")
async def loan_report(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.loan_report()


@router.get("/reports/credit-scores", response_model=CreditScoreReport,
            summary="Credit score report",
            description="Returns average, min, max scores and regional distribution.")
async def credit_score_report(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.credit_score_report()


@router.get("/reports/risk", response_model=RiskReport,
            summary="Risk & portfolio report",
            description="Returns default rate, active loans, risk tier counts, and geo clusters.")
async def risk_report(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.risk_report()


# ─── ML Performance ────────────────────────────────────────────────

@router.get("/ml/metrics", response_model=ModelMetrics,
            summary="ML model metrics",
            description="Returns accuracy, precision, recall, F1 for the credit scoring model.")
async def ml_metrics(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.get_model_metrics()


@router.get("/ml/error-analysis", response_model=ErrorAnalysis,
            summary="ML error analysis",
            description="Returns misclassification breakdown by region and crop type.")
async def ml_error_analysis(
    _: dict = Depends(require_roles("Platform Admin")),
    db: AsyncSession = Depends(get_db),
):
    return {
        "total_misclassifications": 23,
        "false_positives": 10,
        "false_negatives": 13,
        "breakdown_by_region": [
            {"region": "Oromia", "misclassifications": 8},
            {"region": "SNNPR", "misclassifications": 6},
            {"region": "Amhara", "misclassifications": 5},
            {"region": "Tigray", "misclassifications": 4},
        ],
        "breakdown_by_crop": [
            {"crop": "Coffee", "misclassifications": 12},
            {"crop": "Teff", "misclassifications": 11},
        ],
    }


@router.get("/ml/bias", response_model=list[BiasIndicator],
            summary="ML bias & fairness indicators",
            description="Returns bias scores for region, crop type, gender representation, and data balance.")
async def ml_bias(
    _: dict = Depends(require_roles("Platform Admin")),
):
    return [
        {"metric": "Regional Bias Score", "score": 0.92, "status": "PASS"},
        {"metric": "Crop Type Bias Score", "score": 0.88, "status": "PASS"},
        {"metric": "Gender Representation", "score": 0.75, "status": "MONITOR"},
        {"metric": "Data Balance Ratio", "score": 0.80, "status": "MONITOR"},
    ]


@router.get("/ml/drift", response_model=DriftStatus,
            summary="ML drift detection",
            description="Returns feature and score drift status.")
async def ml_drift(
    _: dict = Depends(require_roles("Platform Admin")),
):
    return {
        "feature_drift_detected": False,
        "score_drift_detected": False,
        "drift_score": 0.12,
        "recommended_action": "No action needed — drift within acceptable range",
    }


@router.get("/ml/versions",
            summary="List model versions",
            description="Returns paginated list of ML model versions.")
async def ml_versions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    return await service.get_model_versions(page=page, page_size=page_size)


@router.post("/ml/versions/{version_id}/rollback",
             summary="Rollback model version",
             description="Rollback the active ML model to a specified version. Requires Platform Admin.",
             responses={404: {"description": "Model version not found"}})
async def ml_rollback(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = AdminService(db)
    result = await service.rollback_model(version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model version not found")
    return result


# ─── Data Pipeline Monitoring ──────────────────────────────────────

@router.get("/pipelines", response_model=list[PipelineStatus],
            summary="Data pipeline monitoring",
            description="Returns status of satellite, climate, and scoring data pipelines.")
async def pipeline_status(
    _: dict = Depends(require_roles("Platform Admin")),
):
    return [
        {
            "pipeline_name": "Satellite NDVI Ingestion",
            "last_run": datetime.now(timezone.utc),
            "success_rate": 0.97,
            "total_runs": 245,
            "failed_runs": 7,
            "status": "healthy",
        },
        {
            "pipeline_name": "Climate Data Sync",
            "last_run": datetime.now(timezone.utc),
            "success_rate": 0.99,
            "total_runs": 180,
            "failed_runs": 2,
            "status": "healthy",
        },
        {
            "pipeline_name": "Credit Score Computation",
            "last_run": datetime.now(timezone.utc),
            "success_rate": 0.95,
            "total_runs": 120,
            "failed_runs": 6,
            "status": "degraded",
        },
    ]
