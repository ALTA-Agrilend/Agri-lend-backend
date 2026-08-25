from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, or_
from typing import Optional
from sqlalchemy.orm import joinedload
from app.models.auth import User, Role
from app.models.audit import AuditLog
from app.schemas.auth import UserCreate, UserUpdate
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from uuid import UUID
from datetime import datetime, timezone


def to_uuid(val: str | UUID | None) -> UUID | None:
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, TypeError):
        return None


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_role(self, role_name: str) -> Role | None:
        result = await self.db.execute(select(Role).where(Role.name == role_name))
        return result.scalar_one_or_none()

    async def register_user(self, data: UserCreate) -> User:
        role = await self._get_role(data.role_name)
        if not role:
            raise ValueError(f"Role '{data.role_name}' not found")
        bank_id = to_uuid(getattr(data, "bank_id", None))
        if getattr(data, "bank_id", None) and not bank_id:
            raise ValueError("Invalid bank_id")
        user = User(
            email=data.email,
            phone_number=data.phone_number,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role_id=role.id,
            bank_id=bank_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str | None, password: str, phone_number: str | None = None) -> tuple[User, str, str] | None:
        stmt = select(User).options(joinedload(User.role))
        if email:
            stmt = stmt.where(User.email == (email or "").lower().strip())
        elif phone_number:
            stmt = stmt.where(User.phone_number == phone_number.strip())
        else:
            return None
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        access = create_access_token(str(user.id), user.role.name, bank_id=user.bank_id)
        refresh = create_refresh_token(str(user.id))
        return user, access, refresh

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str] | None:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None
        user = await self.get_user_by_id(payload["sub"])
        if not user or not user.is_active:
            return None
        access = create_access_token(str(user.id), user.role.name, bank_id=user.bank_id)
        return access, refresh_token

    async def get_user_by_id(self, user_id: str | UUID) -> User | None:
        target_id = to_uuid(user_id)
        if not target_id:
            return None
        result = await self.db.execute(select(User).options(joinedload(User.role)).where(User.id == target_id))
        return result.scalar_one_or_none()

    async def get_all_users(self, page: int = 1, page_size: int = 20, role: Optional[str] = None, search: Optional[str] = None) -> dict:
        query = select(User, Role.name).join(Role, User.role_id == Role.id)
        if role:
            query = query.where(Role.name == role)
        if search:
            query = query.where(
                or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )
        count_query = select(sa_func.count()).select_from(query.subquery())
        total_q = await self.db.execute(count_query)
        total = total_q.scalar() or 0
        query = query.order_by(User.created_at.desc())
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await self.db.execute(query)
        rows = result.all()
        items = [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role_name": role_name,
                "is_active": u.is_active,
                "locale": u.locale,
                "created_at": u.created_at,
            }
            for u, role_name in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": -(-total // page_size) if total > 0 else 0,
        }

    async def admin_create_user(self, data: UserCreate) -> User:
        return await self.register_user(data)

    async def assign_role(self, user_id: str | UUID, role_name: str) -> User | None:
        role = await self._get_role(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' not found")
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.role_id = role.id
        await self.db.flush()
        return user

    async def update_user(self, user_id: str | UUID, data: UserUpdate) -> User | None:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.phone_number is not None:
            user.phone_number = data.phone_number
        if data.locale is not None:
            user.locale = data.locale
        await self.db.flush()
        return user

    async def deactivate_user(self, user_id: str | UUID) -> User | None:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.is_active = False
        await self.db.flush()
        return user

    async def delete_user(self, user_id: str | UUID) -> bool:
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        await self.db.delete(user)
        await self.db.flush()
        return True

    async def log_audit(self, user_id: str | UUID, action: str, resource: str, resource_id: str, details: str | None = None, ip: str | None = None) -> None:
        target_user_id = to_uuid(user_id)
        log = AuditLog(
            user_id=target_user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=ip,
        )
        self.db.add(log)
        await self.db.flush()
