from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserUpdate, UserResponse,
)
from app.services.auth import AuthService
from app.core.dependencies import get_current_user
from app.core.config import settings

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             summary="Register a new user",
             description="Creates a new user account with the specified role (Farmer, Bank Analyst, etc). Public endpoint — rate limited.",
             responses={400: {"description": "Validation error (e.g. role not found)"}})
@limiter.limit(lambda: f"{settings.rate_limit_auth_per_minute}/minute")
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    try:
        user = await service.register_user(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return user


@router.post("/login", response_model=TokenResponse,
             summary="Login with email and password",
             description="Authenticates a user and returns JWT access + refresh tokens. Public endpoint — rate limited.",
             responses={401: {"description": "Invalid credentials or account deactivated"}})
@limiter.limit(lambda: f"{settings.rate_limit_auth_per_minute}/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    result = await service.authenticate(
        data.email,
        data.password,
        phone_number=data.phone_number,
    )
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials or account deactivated")
    return TokenResponse(access_token=result[1], refresh_token=result[2])


@router.post("/refresh", response_model=TokenResponse,
             summary="Refresh access token",
             description="Exchange a valid refresh token for a new access token pair.",
             responses={401: {"description": "Invalid or expired refresh token"}})
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    result = await service.refresh_access_token(data.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return TokenResponse(access_token=result[0], refresh_token=result[1])


@router.get("/me", response_model=UserResponse,
            summary="Get current user profile",
            description="Returns the authenticated user's profile information.",
            responses={404: {"description": "User not found"}})
async def get_me(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    user = await service.get_user_by_id(current_user.get("sub"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    resp = UserResponse.model_validate(user)
    if user.role:
        resp.role_name = user.role.name
    resp.bank_id = user.bank_id
    resp.bank_name = user.bank.bank_name if user.bank else None
    resp.bank_interest_rate = (
        float(user.bank.interest_rate)
        if user.bank and user.bank.interest_rate is not None
        else None
    )
    return resp


@router.patch("/me", response_model=UserResponse,
              summary="Update current user profile",
              description="Update the authenticated user's profile fields (name, phone, locale).",
              responses={404: {"description": "User not found"}})
async def update_profile(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = AuthService(db)
    user = await service.update_user(current_user["sub"], data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    resp = UserResponse.model_validate(user)
    if user.role:
        resp.role_name = user.role.name
    resp.bank_id = user.bank_id
    resp.bank_name = user.bank.bank_name if user.bank else None
    resp.bank_interest_rate = (
        float(user.bank.interest_rate)
        if user.bank and user.bank.interest_rate is not None
        else None
    )
    return resp
