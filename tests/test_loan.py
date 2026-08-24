import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid as uuid_lib
from app.services.loan import LoanService
from app.services.credit import CreditService
from app.models.loan import LoanApplication, LoanStatus
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.credit import CreditScoreRecord, RiskTier
from app.models.auth import User, Role
from decimal import Decimal
from app.core.security import hash_password


class TestLoanService:
    @pytest.fixture
    async def farmer_profile(self, session: AsyncSession) -> FarmerProfile:
        role_result = await session.execute(select(Role).where(Role.name == "Farmer"))
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name="Farmer", description="Farmer")
            session.add(role)
            await session.flush()
        user = User(
            email="loanfarmer@test.com",
            full_name="Loan Farmer",
            hashed_password=hash_password("pass123"),
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        profile = FarmerProfile(
            user_id=user.id,
            full_name="Loan Farmer",
            national_id="LN12345",
            phone_number="+251911111111",
        )
        session.add(profile)
        await session.flush()
        return profile

    @pytest.fixture
    async def credit_score(self, session: AsyncSession, farmer_profile: FarmerProfile) -> CreditScoreRecord:
        score = CreditScoreRecord(
            farmer_id=farmer_profile.id,
            score_value=620,
            risk_tier=RiskTier.MEDIUM,
            geospatial_score=Decimal("0.65"),
            transactional_score=Decimal("0.60"),
            alternative_score=Decimal("0.55"),
            model_version="v1.0.0",
            confidence_rating=Decimal("0.85"),
        )
        session.add(score)
        await session.flush()
        return score

    async def _create_test_bank(self, session: AsyncSession):
        from app.models.bank import BankPartner
        bank = BankPartner(bank_name="Test Bank")
        session.add(bank)
        await session.flush()
        return bank

    async def test_create_application(self, session: AsyncSession, farmer_profile):
        bank = await self._create_test_bank(session)
        service = LoanService(session)
        from app.schemas.loan import LoanApplicationCreate
        data = LoanApplicationCreate(
            farmer_id=farmer_profile.id,
            bank_id=bank.id,
            requested_amount=Decimal("50000"),
            loan_purpose="Buy seeds and fertilizer",
        )
        app = await service.create_application(data, 620)
        assert app.farmer_id == farmer_profile.id
        assert app.requested_amount == Decimal("50000")
        assert app.status == LoanStatus.PENDING
        assert app.credit_score_at_application == 620

    async def test_review_application_approve(self, session: AsyncSession, farmer_profile):
        bank = await self._create_test_bank(session)
        app = LoanApplication(
            farmer_id=farmer_profile.id,
            bank_id=bank.id,
            requested_amount=Decimal("50000"),
            loan_purpose="Seeds",
            credit_score_at_application=620,
            status=LoanStatus.PENDING,
        )
        session.add(app)
        await session.flush()
        reviewer_uuid = str(uuid_lib.uuid4())
        service = LoanService(session)
        result = await service.review_application(str(app.id), LoanStatus.APPROVED, reviewer_uuid)
        assert result is not None
        assert result.status == LoanStatus.APPROVED
        assert str(result.reviewed_by) == reviewer_uuid
        assert result.reviewed_at is not None

    async def test_review_application_not_found(self, session: AsyncSession):
        service = LoanService(session)
        result = await service.review_application(str(uuid_lib.uuid4()), LoanStatus.APPROVED, "reviewer-id")
        assert result is None

    async def test_high_risk_warning_threshold(self, session: AsyncSession, farmer_profile):
        bank = await self._create_test_bank(session)
        app_low = LoanApplication(
            farmer_id=farmer_profile.id, bank_id=bank.id,
            requested_amount=Decimal("30000"), loan_purpose="Test",
            credit_score_at_application=450, status=LoanStatus.PENDING,
        )
        app_high = LoanApplication(
            farmer_id=farmer_profile.id, bank_id=bank.id,
            requested_amount=Decimal("30000"), loan_purpose="Test",
            credit_score_at_application=650, status=LoanStatus.PENDING,
        )
        session.add_all([app_low, app_high])
        await session.flush()
        service = LoanService(session)
        warnings = await service.get_high_risk_warnings()
        assert len(warnings) == 1
        assert warnings[0]["score"] < 500
        assert warnings[0]["risk_tier"] == "HIGH"
