from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, case
from decimal import Decimal
from typing import Optional
from uuid import UUID


def _to_uuid(val) -> UUID | None:
    if val is None or isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, TypeError):
        return None

from app.db.session import get_db
from app.schemas.bank import BankPartnerCreate, BankPartnerResponse, BankSettingsUpdate
from app.schemas import PaginatedResponse
from app.core.dependencies import get_current_user, require_roles
from app.models.bank import BankPartner
from app.models.auth import User, Role
from app.models.loan import LoanApplication, LoanStatus
from app.services.auth import AuthService

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.post("/", response_model=BankPartnerResponse, status_code=201,
             summary="Create a bank partner with its analyst account",
             description="Registers a new institution and provisions exactly one login account "
                         "(Bank Analyst role) for it. Requires Platform Admin.",
             responses={409: {"description": "Analyst email already registered"}})
async def create_bank(
    data: BankPartnerCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    existing_account = await db.execute(select(User).where(User.email == data.analyst_email))
    if existing_account.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    role_result = await db.execute(select(Role).where(Role.name == "Bank Analyst"))
    analyst_role = role_result.scalar_one_or_none()
    if not analyst_role:
        raise HTTPException(status_code=500, detail="Bank Analyst role missing — seed the database")

    bank = BankPartner(
        bank_name=data.bank_name,
        interest_rate=Decimal(str(data.interest_rate)),
        subscription_tier=data.subscription_tier,
    )
    db.add(bank)
    await db.flush()

    from app.core.security import hash_password
    analyst = User(
        email=data.analyst_email,
        hashed_password=hash_password(data.analyst_password),
        full_name=data.analyst_full_name,
        role_id=analyst_role.id,
        bank_id=bank.id,
    )
    db.add(analyst)
    await db.flush()
    return bank


@router.get("/",
            summary="List bank partners",
            description="Returns a paginated list of all registered bank partners.")
async def list_banks(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    count_q = await db.execute(select(sa_func.count(BankPartner.id)))
    total = count_q.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        select(BankPartner).order_by(BankPartner.onboarding_date.desc()).offset(offset).limit(page_size)
    )
    banks = list(result.scalars().all())
    return {
        "items": banks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size) if total > 0 else 0,
    }


@router.get("/{bank_id}/detail",
            summary="Bank partner detail",
            description="Returns full institution profile, its analyst login accounts, and loan book statistics. Requires Platform Admin.",
            responses={404: {"description": "Bank not found"}})
async def get_bank_detail(
    bank_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    result = await db.execute(select(BankPartner).where(BankPartner.id == _to_uuid(bank_id)))
    bank = result.scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    analysts_result = await db.execute(
        select(User).where(User.bank_id == bank.id).order_by(User.created_at.asc())
    )
    analysts = [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in analysts_result.scalars().all()
    ]

    from sqlalchemy import func as sa_func
    loan_stats_q = await db.execute(
        select(
            sa_func.count(LoanApplication.id),
            sa_func.coalesce(sa_func.sum(LoanApplication.requested_amount), 0),
            sa_func.coalesce(sa_func.sum(
                case((LoanApplication.status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED]), LoanApplication.repayment_amount))), 0),
        ).where(LoanApplication.bank_id == bank.id)
    )
    loan_count, amount_total, repayment_total = loan_stats_q.one()

    approved_q = await db.execute(
        select(sa_func.count(LoanApplication.id)).where(
            LoanApplication.bank_id == bank.id,
            LoanApplication.status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED]),
        )
    )

    return {
        "bank": {
            "id": str(bank.id),
            "bank_name": bank.bank_name,
            "interest_rate": float(bank.interest_rate) if bank.interest_rate is not None else None,
            "subscription_tier": bank.subscription_tier,
            "is_active": bank.is_active,
            "onboarding_date": bank.onboarding_date,
        },
        "analysts": analysts,
        "loan_stats": {
            "total_loans": loan_count or 0,
            "approved_loans": approved_q.scalar() or 0,
            "total_requested": float(amount_total or 0),
            "repayment_total": float(repayment_total or 0),
        },
    }


@router.get("/{bank_id}", response_model=BankPartnerResponse,
            summary="Get bank details",
            description="Returns details for a specific bank partner.",
            responses={404: {"description": "Bank not found"}})
async def get_bank(
    bank_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Bank Administrator", "Platform Admin")),
):
    result = await db.execute(select(BankPartner).where(BankPartner.id == _to_uuid(bank_id)))
    bank = result.scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    return bank


@router.patch("/{bank_id}/settings",
              summary="Update bank lending settings",
              description="Banks can only adjust their annual interest rate — institution names are immutable. "
                          "Requires Bank Administrator or Platform Admin.",
              responses={404: {"description": "Bank not found"}})
async def update_bank_settings(
    bank_id: str,
    data: BankSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Bank Administrator", "Platform Admin")),
):
    result = await db.execute(select(BankPartner).where(BankPartner.id == _to_uuid(bank_id)))
    bank = result.scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")
    if data.interest_rate is not None:
        bank.interest_rate = Decimal(str(data.interest_rate))
    await db.flush()
    audit = AuthService(db)
    await audit.log_audit(
        user_id=current_user["sub"],
        action="UPDATE_BANK_SETTINGS",
        resource="BankPartner",
        resource_id=bank_id,
        details=f"interest_rate={data.interest_rate}" if data.interest_rate is not None else None,
        ip=request.client.host if request.client else None,
    )
    return {
        "detail": "Bank settings updated",
        "interest_rate": float(bank.interest_rate) if bank.interest_rate is not None else None,
    }
