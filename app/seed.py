import json
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.auth import Role, User
from app.models.bank import BankPartner
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.credit import CreditScoreRecord, RiskTier
from app.models.loan import LoanApplication, LoanStatus
from app.core.security import hash_password

ROLES = [
    "Farmer",
    "Bank Viewer",
    "Bank Analyst",
    "Bank Administrator",
    "Platform Admin",
    "Risk Analyst",
    "Loan Officer",
]

DEFAULT_USERS = [
    {
        "email": "admin@agrilend.com",
        "password": "Admin@123",
        "full_name": "System Administrator",
        "role_name": "Platform Admin",
    },
    {
        "email": "bank@agrilend.com",
        "password": "bank@123",
        "full_name": "Bank Analyst Officer",
        "role_name": "Bank Analyst",
    },
]

MOCK_BANKS = [
    {"bank_name": "AgriBank International", "subscription_tier": "enterprise", "api_key_hash": "hash_agribank_01"},
    {"bank_name": "EcoLend Microfinance", "subscription_tier": "standard", "api_key_hash": "hash_ecolend_02"},
    {"bank_name": "Horizon Agro Credit", "subscription_tier": "enterprise", "api_key_hash": "hash_horizon_03"},
    {"bank_name": "Savanna Farmers Co-op", "subscription_tier": "standard", "api_key_hash": "hash_savanna_04"},
]

MOCK_FARMERS = [
    {
        "email": "amina.hassan@agrifarm.org",
        "full_name": "Amina Hassan",
        "phone_number": "+254711223344",
        "national_id": "ID-KEN-908124",
        "region": "Central Highlands",
        "crop": "Maize",
        "hectares": Decimal("4.50"),
        "gps": "-1.286389, 36.817223",
        "score": 742,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("4500.00"),
        "purpose": "High-yield hybrid maize seeds and drip irrigation kit",
        "status": LoanStatus.PENDING,
    },
    {
        "email": "kofi.mensah@agrifarm.org",
        "full_name": "Kofi Mensah",
        "phone_number": "+233244556677",
        "national_id": "ID-GHA-771829",
        "region": "Ashanti Region",
        "crop": "Cocoa",
        "hectares": Decimal("12.00"),
        "gps": "6.688480, -1.624430",
        "score": 780,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("12500.00"),
        "purpose": "Solar-powered cocoa drying equipment & organic fertilizer",
        "status": LoanStatus.APPROVED,
    },
    {
        "email": "david.ochieng@agrifarm.org",
        "full_name": "David Ochieng",
        "phone_number": "+254722334455",
        "national_id": "ID-KEN-445129",
        "region": "Rift Valley",
        "crop": "Wheat",
        "hectares": Decimal("8.20"),
        "gps": "0.514277, 35.269779",
        "score": 690,
        "risk_tier": RiskTier.MEDIUM,
        "amount": Decimal("8000.00"),
        "purpose": "Tractor leasing and seasonal harvesting labor pool",
        "status": LoanStatus.DISBURSED,
    },
    {
        "email": "grace.wanjiku@agrifarm.org",
        "full_name": "Grace Wanjiku",
        "phone_number": "+254733445566",
        "national_id": "ID-KEN-881203",
        "region": "Eastern Slope",
        "crop": "Coffee",
        "hectares": Decimal("3.50"),
        "gps": "-0.416667, 36.950000",
        "score": 630,
        "risk_tier": RiskTier.MEDIUM,
        "amount": Decimal("3200.00"),
        "purpose": "Eco-friendly coffee pulping machine & storage shed",
        "status": LoanStatus.PENDING,
    },
    {
        "email": "emmanuel.boateng@agrifarm.org",
        "full_name": "Emmanuel Boateng",
        "phone_number": "+233200112233",
        "national_id": "ID-GHA-339102",
        "region": "Volta Basin",
        "crop": "Rice",
        "hectares": Decimal("15.00"),
        "gps": "6.125000, 0.050000",
        "score": 810,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("18000.00"),
        "purpose": "Flood control embankment & automated rice harvester",
        "status": LoanStatus.DISBURSED,
    },
    {
        "email": "jabari.kiptoo@agrifarm.org",
        "full_name": "Jabari Kiptoo",
        "phone_number": "+254744556677",
        "national_id": "ID-KEN-119283",
        "region": "North Plateau",
        "crop": "Tea",
        "hectares": Decimal("6.80"),
        "gps": "0.333333, 35.166667",
        "score": 590,
        "risk_tier": RiskTier.HIGH,
        "amount": Decimal("6500.00"),
        "purpose": "Pruning power tools and bio-pesticide application",
        "status": LoanStatus.REJECTED,
    },
    {
        "email": "fatima.bello@agrifarm.org",
        "full_name": "Fatima Bello",
        "phone_number": "+2348011223344",
        "national_id": "ID-NGA-662910",
        "region": "Savannah North",
        "crop": "Soybeans",
        "hectares": Decimal("9.40"),
        "gps": "10.516667, 7.433333",
        "score": 715,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("9500.00"),
        "purpose": "Grain storage silo & pest prevention technology",
        "status": LoanStatus.APPROVED,
    },
    {
        "email": "samuel.kamau@agrifarm.org",
        "full_name": "Samuel Kamau",
        "phone_number": "+254755667788",
        "national_id": "ID-KEN-554201",
        "region": "Mount Kenya",
        "crop": "Potatoes",
        "hectares": Decimal("2.80"),
        "gps": "-0.150000, 37.300000",
        "score": 660,
        "risk_tier": RiskTier.MEDIUM,
        "amount": Decimal("2800.00"),
        "purpose": "Certified Irish potato seed tubers & cold storage box",
        "status": LoanStatus.PENDING,
    },
]


async def seed_roles() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Role))
        existing = {r.name for r in result.scalars().all()}
        for name in ROLES:
            if name not in existing:
                session.add(Role(name=name, description=f"{name} role"))
        await session.commit()


async def seed_default_users() -> None:
    async with async_session_factory() as session:
        for u in DEFAULT_USERS:
            res = await session.execute(select(User).where(User.email == u["email"]))
            if not res.scalar_one_or_none():
                role_res = await session.execute(select(Role).where(Role.name == u["role_name"]))
                role = role_res.scalar_one_or_none()
                if role:
                    user = User(
                        email=u["email"],
                        hashed_password=hash_password(u["password"]),
                        full_name=u["full_name"],
                        role_id=role.id,
                        is_active=True,
                    )
                    session.add(user)
        await session.commit()


async def seed_mock_data() -> None:
    async with async_session_factory() as session:
        # 1. Seed Bank Partners
        bank_list = []
        for b in MOCK_BANKS:
            res = await session.execute(select(BankPartner).where(BankPartner.bank_name == b["bank_name"]))
            existing_bank = res.scalar_one_or_none()
            if not existing_bank:
                new_bank = BankPartner(
                    bank_name=b["bank_name"],
                    subscription_tier=b["subscription_tier"],
                    api_key_hash=b["api_key_hash"],
                    is_active=True,
                )
                session.add(new_bank)
                await session.flush()
                bank_list.append(new_bank)
            else:
                bank_list.append(existing_bank)

        # Get Farmer Role
        farmer_role_res = await session.execute(select(Role).where(Role.name == "Farmer"))
        farmer_role = farmer_role_res.scalar_one_or_none()
        if not farmer_role:
            await session.commit()
            return

        # 2. Seed Farmers, Parcels, Scores, Loans
        primary_bank = bank_list[0] if bank_list else None

        for item in MOCK_FARMERS:
            # User account
            user_res = await session.execute(select(User).where(User.email == item["email"]))
            user = user_res.scalar_one_or_none()
            if not user:
                user = User(
                    email=item["email"],
                    hashed_password=hash_password("Farmer@123"),
                    full_name=item["full_name"],
                    phone_number=item["phone_number"],
                    role_id=farmer_role.id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()

            # Profile
            profile_res = await session.execute(select(FarmerProfile).where(FarmerProfile.user_id == user.id))
            profile = profile_res.scalar_one_or_none()
            if not profile:
                profile = FarmerProfile(
                    user_id=user.id,
                    full_name=item["full_name"],
                    national_id=item["national_id"],
                    phone_number=item["phone_number"],
                    gps_coordinates=item["gps"],
                    consent_status=True,
                )
                session.add(profile)
                await session.flush()

            # Farm Parcel
            parcel_res = await session.execute(select(FarmParcel).where(FarmParcel.farmer_id == profile.id))
            parcel = parcel_res.scalar_one_or_none()
            if not parcel:
                parcel = FarmParcel(
                    farmer_id=profile.id,
                    parcel_name=f"{item['full_name']}'s {item['crop']} Farm",
                    size_hectares=item["hectares"],
                    primary_crop=item["crop"],
                    region=item["region"],
                )
                session.add(parcel)
                await session.flush()

            # Credit Score
            score_res = await session.execute(select(CreditScoreRecord).where(CreditScoreRecord.farmer_id == profile.id))
            score_rec = score_res.scalar_one_or_none()
            if not score_rec:
                score_rec = CreditScoreRecord(
                    farmer_id=profile.id,
                    score_value=item["score"],
                    risk_tier=item["risk_tier"],
                    geospatial_score=Decimal("85.40"),
                    transactional_score=Decimal("78.50"),
                    alternative_score=Decimal("82.10"),
                    model_version="v2.4.1-crop-yield",
                    confidence_rating=Decimal("0.92"),
                    categorical_breakdown=json.dumps({"soil_quality": 88, "weather_risk": 72, "repayment": 85}),
                )
                session.add(score_rec)
                await session.flush()

            # Loan Application
            if primary_bank:
                loan_res = await session.execute(select(LoanApplication).where(LoanApplication.farmer_id == profile.id))
                loan_rec = loan_res.scalar_one_or_none()
                if not loan_rec:
                    loan_rec = LoanApplication(
                        farmer_id=profile.id,
                        bank_id=primary_bank.id,
                        requested_amount=item["amount"],
                        loan_purpose=item["purpose"],
                        credit_score_at_application=item["score"],
                        status=item["status"],
                    )
                    session.add(loan_rec)

        await session.commit()
