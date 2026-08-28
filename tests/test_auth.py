import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth import AuthService
from app.schemas.auth import UserCreate
from app.core.security import verify_password


class TestAuthService:
    async def test_register_user(self, session: AsyncSession, farmer_role):
        service = AuthService(session)
        data = UserCreate(
            email="newfarmer@test.com",
            password="securePass1!",
            full_name="New Farmer",
            role_name="Farmer",
            phone_number="+251911111111",
        )
        user = await service.register_user(data)
        assert user.email == "newfarmer@test.com"
        assert user.full_name == "New Farmer"
        assert user.is_active is True
        assert verify_password("securePass1!", user.hashed_password)

    async def test_register_duplicate_email(self, session: AsyncSession, farmer_role):
        from sqlalchemy.exc import IntegrityError
        service = AuthService(session)
        data = UserCreate(
            email="dup@test.com", password="pass123", full_name="Dup", role_name="Farmer"
        )
        await service.register_user(data)
        with pytest.raises(IntegrityError):
            await service.register_user(data)

    async def test_register_invalid_role(self, session: AsyncSession):
        service = AuthService(session)
        data = UserCreate(
            email="badrole@test.com", password="pass123", full_name="Bad", role_name="NonExistent"
        )
        with pytest.raises(ValueError, match="Role 'NonExistent' not found"):
            await service.register_user(data)

    async def test_authenticate_success(self, session: AsyncSession, farmer_user):
        service = AuthService(session)
        result = await service.authenticate("farmer@test.com", "password123")
        assert result is not None
        user, access, refresh = result
        assert user.email == "farmer@test.com"
        assert access is not None
        assert refresh is not None

    async def test_authenticate_wrong_password(self, session: AsyncSession, farmer_user):
        service = AuthService(session)
        result = await service.authenticate("farmer@test.com", "wrongpassword")
        assert result is None

    async def test_authenticate_inactive_user(self, session: AsyncSession, farmer_user):
        farmer_user.is_active = False
        await session.flush()
        service = AuthService(session)
        result = await service.authenticate("farmer@test.com", "password123")
        assert result is None

    async def test_authenticate_by_phone_normalized(self, session: AsyncSession, farmer_role):
        from app.schemas.auth import UserCreate
        service = AuthService(session)
        data = UserCreate(
            email="phonefarmer@test.com",
            password="SecurePass1!",
            full_name="Phone Farmer",
            role_name="Farmer",
            phone_number="+251 91 222 3333",
        )
        user = await service.register_user(data)
        assert user.phone_number == "+251912223333"
        for fmt in ("+251912223333", "251912223333", "0912223333", "912223333"):
            result = await service.authenticate(None, "SecurePass1!", phone_number=fmt)
            assert result is not None, f"phone login failed for format {fmt}"
        assert await service.authenticate(None, "wrongpass", phone_number="+251912223333") is None

    async def test_response_models_allow_null_email(self):
        from uuid import uuid4
        from datetime import datetime, timezone
        from app.schemas.auth import UserAdminResponse, UserResponse
        base = dict(
            id=uuid4(),
            email=None,
            full_name="Email-Free Farmer",
            is_active=True,
            locale="en",
            created_at=datetime.now(timezone.utc),
        )
        UserAdminResponse(**base, role_name="Farmer")
        UserResponse(**base, role_id=uuid4())
