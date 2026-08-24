from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from uuid import UUID
from app.core.security import decode_token
from app.core.config import settings

bearer_scheme = HTTPBearer()
optional_bearer_scheme = HTTPBearer(auto_error=False)

BANK_ROLES = ("Bank Analyst", "Bank Administrator", "Loan Officer", "Risk Analyst")


class RBACException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
) -> dict | None:
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    return payload


def _to_uuid(val) -> UUID | None:
    if val is None or isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, TypeError):
        return None


def get_scope_bank_id(current_user: dict) -> UUID | None:
    """Bank-role users are scoped to their own institution; platform roles see everything."""
    role = current_user.get("role", "")
    if role in BANK_ROLES:
        return _to_uuid(current_user.get("bank_id"))
    return None


def require_roles(*roles: str):
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise RBACException()
        return current_user

    return role_checker
