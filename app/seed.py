import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.auth import Role, User
from app.models.bank import BankPartner
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.credit import CreditScoreRecord, RiskTier
from app.models.loan import LoanApplication, LoanStatus
from app.models.ops import (
    FarmerVerificationQueue,
    SupportTicket,
    CommandLog,
    SystemSetting,
    Notification,
    PipelineRun,
)
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
    {"bank_name": "AgriBank International", "interest_rate": Decimal("8.50"), "subscription_tier": "enterprise"},
    {"bank_name": "EcoLend Microfinance", "interest_rate": Decimal("10.25"), "subscription_tier": "standard"},
    {"bank_name": "Horizon Agro Credit", "interest_rate": Decimal("9.75"), "subscription_tier": "enterprise"},
    {"bank_name": "Savanna Farmers Co-op", "interest_rate": Decimal("12.00"), "subscription_tier": "standard"},
]

MOCK_FARMERS = [
    {
        "email": "amina.hassan@agrifarm.org",
        "full_name": "Amina Hassan",
        "phone_number": "+254711223344",
        "national_id": "ID-KEN-908124",
        "region": "Central Highlands",
        "crop": "Teff",
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
        "crop": "Coffee",
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
        "crop": "Teff",
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
        "crop": "Teff",
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
        "crop": "Coffee",
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
        "crop": "Teff",
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
        "crop": "Teff",
        "hectares": Decimal("2.80"),
        "gps": "-0.150000, 37.300000",
        "score": 660,
        "risk_tier": RiskTier.MEDIUM,
        "amount": Decimal("2800.00"),
        "purpose": "Certified Irish potato seed tubers & cold storage box",
        "status": LoanStatus.PENDING,
    },
    {
        "email": "zawadi.njoroge@agrifarm.org",
        "full_name": "Zawadi Njoroge",
        "phone_number": "+255713334455",
        "national_id": "ID-TZA-204871",
        "region": "Northern Rift",
        "crop": "Coffee",
        "hectares": Decimal("5.20"),
        "gps": "-3.366667, 36.683333",
        "score": 700,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("5800.00"),
        "purpose": "Sunflower oil press and threshing unit",
        "status": LoanStatus.APPROVED,
    },
    {
        "email": "beatrice.muthoni@agrifarm.org",
        "full_name": "Beatrice Muthoni",
        "phone_number": "+254766778899",
        "national_id": "ID-KEN-731122",
        "region": "Central Rift",
        "crop": "Teff",
        "hectares": Decimal("7.50"),
        "gps": "-1.100000, 36.783333",
        "score": 745,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("9200.00"),
        "purpose": "Avocado orchard irrigation and export crates",
        "status": LoanStatus.APPROVED,
    },
    {
        "email": "yusuf.abdi@agrifarm.org",
        "full_name": "Yusuf Abdi",
        "phone_number": "+254711998877",
        "national_id": "ID-KEN-990324",
        "region": "North Eastern",
        "crop": "Coffee",
        "hectares": Decimal("11.30"),
        "gps": "0.500000, 40.000000",
        "score": 610,
        "risk_tier": RiskTier.MEDIUM,
        "amount": Decimal("7400.00"),
        "purpose": "Drought-tolerant sorghum seed and drip lines",
        "status": LoanStatus.PENDING,
    },
    {
        "email": "naomi.chebet@agrifarm.org",
        "full_name": "Naomi Chebet",
        "phone_number": "+254722667788",
        "national_id": "ID-KEN-118877",
        "region": "Southern Rift",
        "crop": "Teff",
        "hectares": Decimal("9.80"),
        "gps": "-0.600000, 35.350000",
        "score": 728,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("8600.00"),
        "purpose": "Malting barley seed and fertilizer program",
        "status": LoanStatus.APPROVED,
    },
    {
        "email": "peter.otieno@agrifarm.org",
        "full_name": "Peter Otieno",
        "phone_number": "+254733889900",
        "national_id": "ID-KEN-667890",
        "region": "Lake Basin",
        "crop": "Teff",
        "hectares": Decimal("4.30"),
        "gps": "-0.280000, 34.750000",
        "score": 550,
        "risk_tier": RiskTier.HIGH,
        "amount": Decimal("4100.00"),
        "purpose": "Rice paddy water management tools",
        "status": LoanStatus.PENDING,
    },
    {
        "email": "halima.said@agrifarm.org",
        "full_name": "Halima Said",
        "phone_number": "+255712445566",
        "national_id": "ID-TZA-885512",
        "region": "Coastal Belt",
        "crop": "Coffee",
        "hectares": Decimal("13.60"),
        "gps": "-6.800000, 39.283333",
        "score": 790,
        "risk_tier": RiskTier.LOW,
        "amount": Decimal("14500.00"),
        "purpose": "Cashew processing and grading equipment",
        "status": LoanStatus.APPROVED,
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


async def seed_ops_data() -> None:
    """Seed operational records: verification queue, tickets, notifications,
    command logs, pipeline runs, and system settings."""
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)

        # Queue items from seeded farmers
        farmers_res = await session.execute(select(FarmerProfile))
        farmers = list(farmers_res.scalars().all())
        existing_queue_res = await session.execute(select(FarmerVerificationQueue.farmer_id))
        queued_ids = {q for q in existing_queue_res.scalars().all()}

        queue_config = [
            (0.7, "PENDING", "AgriLend Mobile App (v1.2)"),
            (0.25, "PENDING", "AgriLend Mobile App (v1.2)"),
            (0.45, "FLAGGED", "AgriLend Mobile App (v1.1)"),
            (0.85, "APPROVED", "Bank Analyst Portal"),
            (0.35, "PENDING", "AgriLend Mobile App (v1.2)"),
            (0.88, "APPROVED", "Bank Analyst Portal"),
            (0.76, "APPROVED", "Bank Analyst Portal"),
            (0.5, "PENDING", "AgriLend Mobile App (v1.3)"),
            (0.82, "APPROVED", "Bank Analyst Portal"),
            (0.9, "APPROVED", "Bank Analyst Portal"),
            (0.42, "PENDING", "AgriLend Mobile App (v1.2)"),
            (0.8, "APPROVED", "Bank Analyst Portal"),
            (0.33, "FLAGGED", "AgriLend Mobile App (v1.2)"),
            (0.87, "APPROVED", "Bank Analyst Portal"),
        ]
        for i, (frac, qstatus, via) in enumerate(queue_config):
            if not farmers:
                break
            farmer = farmers[i % len(farmers)]
            if farmer.id in queued_ids:
                continue
            session.add(
                FarmerVerificationQueue(
                    farmer_id=farmer.id,
                    status=qstatus,
                    submitted_via=via,
                    flag_reason="Telemetry variance detected (52% satellite match)" if qstatus == "FLAGGED" else None,
                    submitted_at=now,
                )
            )

        # Support tickets
        ticket_res = await session.execute(select(SupportTicket).limit(1))
        if not ticket_res.scalar_one_or_none():
            session.add_all([
                SupportTicket(title="Satellite Data Feed Latency in Rift Valley Cluster", category="Telemetry", priority="High", status="In Progress", description="Review node latency in Rift Valley region."),
                SupportTicket(title="M-Pesa Disbursement Gateway Timeout Error (HTTP 504)", category="Payment Gateway", priority="Critical", status="Open", description="Webhook timeout reported."),
                SupportTicket(title="KYC Identity Check Discrepancy for National ID #ID-94827", category="Verification", priority="Medium", status="Resolved"),
                SupportTicket(title="Credit Scoring ML Model Drift Alert Notification", category="AI Models", priority="Low", status="Resolved"),
            ])

        # Command log history
        log_res = await session.execute(select(CommandLog).limit(1))
        if not log_res.scalar_one_or_none():
            session.add_all([
                CommandLog(command="Sentinel-2 satellite orbit feed synchronize", status="SUCCESS", output="100% telemetry resolution.", executed_at=now),
                CommandLog(command="Credit Scoring ML batch inference trigger", status="SUCCESS", output="Batch inference queued for 420 applications.", executed_at=now),
                CommandLog(command="M-Pesa disbursement webhook retry", status="SUCCESS", output="Webhook returned 200 OK (14ms).", executed_at=now),
                CommandLog(command="Check Redis Cache Worker Node #03", status="WARN", output="High memory utilization (78%).", executed_at=now),
            ])

        # System settings
        settings_res = await session.execute(select(SystemSetting))
        existing_keys = {s.key for s in settings_res.scalars().all()}
        for key, value in {
            "site_name": "AgriLend Technical Command",
            "environment": "production",
            "currency": "USD",
        }.items():
            if key not in existing_keys:
                session.add(SystemSetting(key=key, value=value))

        # Notifications
        notification_res = await session.execute(select(Notification).limit(1))
        if not notification_res.scalar_one_or_none():
            session.add_all([
                Notification(role="bank", title="Regional Drought Risk Warning", message="North Ridge cluster NDVI biomass signal fell by 18%. Weather shock alert active.", type="alert", created_at=now),
                Notification(role="bank", title="New Loan Application Submitted", message="A farmer applied for a seasonal crop loan pending credit review.", type="application", created_at=now),
                Notification(role="bank", title="GEE Model Recalibration", message="Satellite telemetry recalibration completed for active farm parcels.", type="system", created_at=now),
                Notification(role="admin", title="FastAPI GEE Pipeline Health", message="Earth Engine microservice running at 99.8% uptime with 42ms median latency.", type="system", created_at=now),
                Notification(role="admin", title="Institutional Partner Webhook", message="Bank partner authenticated 14 new credit delivery webhooks.", type="partner", created_at=now),
                Notification(role="admin", title="National Farmer Identity Queue", message="NID verification queue cleared 85 farmer profile checks.", type="system", created_at=now, read=True),
            ])

        # Pipeline runs
        run_res = await session.execute(select(PipelineRun).limit(1))
        if not run_res.scalar_one_or_none():
            session.add_all([
                PipelineRun(pipeline_name="Satellite_HighRes", status="RUNNING", duration_seconds=872.0, started_at=now),
                PipelineRun(pipeline_name="Mobile_Money_Ingress", status="SUCCESS", duration_seconds=131.0, started_at=now),
                PipelineRun(pipeline_name="Cooperative_Harvest_Registry", status="FAILED", duration_seconds=45.0, started_at=now),
            ])

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
                    interest_rate=b["interest_rate"],
                    subscription_tier=b["subscription_tier"],
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
        # Farmers are distributed round-robin across partner institutions so each
        # bank account sees its own portfolio when scoped queries are enabled.

        for farmer_index, item in enumerate(MOCK_FARMERS):
            assigned_bank = bank_list[farmer_index % len(bank_list)] if bank_list else None
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
                    registered_by_bank_id=assigned_bank.id if assigned_bank else None,
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
            if assigned_bank:
                loan_res = await session.execute(select(LoanApplication).where(LoanApplication.farmer_id == profile.id))
                loan_rec = loan_res.scalar_one_or_none()
                if not loan_rec:
                    loan_rec = LoanApplication(
                        farmer_id=profile.id,
                        bank_id=assigned_bank.id,
                        requested_amount=item["amount"],
                        loan_purpose=item["purpose"],
                        credit_score_at_application=item["score"],
                        status=item["status"],
                    )
                    session.add(loan_rec)

        # Link the demo bank analyst account to its institution (banks are created above)
        bank_user_res = await session.execute(select(User).where(User.email == "bank@agrilend.com"))
        bank_user = bank_user_res.scalar_one_or_none()
        if bank_user and not bank_user.bank_id and bank_list:
            bank_user.bank_id = bank_list[0].id

        await session.commit()
