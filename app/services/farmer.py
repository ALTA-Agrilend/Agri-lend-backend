from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, or_
from typing import Optional
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.loan import LoanApplication
from app.models.credit import CreditScoreRecord
from app.models.auth import User
from app.schemas.farmer import FarmerRegistrationHub, FarmParcelCreate
from app.core.security import hash_password
from datetime import datetime, timezone
from app.services.geospatial import GeospatialService


class FarmerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_hub(
        self,
        data: FarmerRegistrationHub,
        registered_by_bank_id=None,
    ) -> tuple[FarmerProfile, FarmParcel | None]:
        from app.models.auth import Role

        result = await self.db.execute(select(Role).where(Role.name == "Farmer"))
        role = result.scalar_one_or_none()
        if not role:
            raise ValueError("Farmer role not found")
        user = User(
            email=getattr(data, "email", None),
            phone_number=data.phone_number,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role_id=role.id,
        )
        self.db.add(user)
        await self.db.flush()

        profile = FarmerProfile(
            user_id=user.id,
            full_name=data.full_name,
            national_id=data.national_id,
            phone_number=data.phone_number,
            gps_coordinates=data.gps_coordinates,
            land_proof_document=data.land_proof_document,
            locale=data.locale,
            registered_by_bank_id=registered_by_bank_id,
        )
        self.db.add(profile)
        await self.db.flush()

        parcel = None
        if data.crop_type and data.farm_size_hectares and data.region:
            parcel = FarmParcel(
                farmer_id=profile.id,
                parcel_name=f"{data.full_name}'s Farm",
                size_hectares=data.farm_size_hectares,
                primary_crop=data.crop_type,
                region=data.region,
            )
            self.db.add(parcel)
            await self.db.flush()

        return profile, parcel

    async def list_farmers(self, page: int = 1, page_size: int = 20, region: Optional[str] = None) -> dict:
        query = (
            select(FarmerProfile, FarmParcel.region, FarmParcel.primary_crop)
            .join(FarmParcel, FarmParcel.farmer_id == FarmerProfile.id, isouter=True)
            .order_by(FarmerProfile.created_at.desc())
        )
        count_query = select(sa_func.count(FarmerProfile.id))
        if region:
            query = query.where(FarmParcel.region == region)
            count_query = count_query.select_from(FarmerProfile).join(
                FarmParcel, FarmParcel.farmer_id == FarmerProfile.id, isouter=True
            ).where(FarmParcel.region == region)
        total_q = await self.db.execute(count_query)
        total = total_q.scalar() or 0
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await self.db.execute(query)
        rows = result.all()
        items = [
            {
                "id": p.id,
                "full_name": p.full_name,
                "phone_number": p.phone_number,
                "region": region_val,
                "primary_crop": crop_val,
                "consent_status": p.consent_status,
                "locale": p.locale,
                "created_at": p.created_at,
            }
            for p, region_val, crop_val in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": -(-total // page_size),
        }

    async def search(self, q: str, region: Optional[str] = None, limit: int = 50, bank_id=None) -> list[dict]:
        latest_score = (
            select(CreditScoreRecord.score_value)
            .where(CreditScoreRecord.farmer_id == FarmerProfile.id)
            .order_by(CreditScoreRecord.calculated_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = (
            select(
                FarmerProfile,
                FarmParcel.region,
                FarmParcel.primary_crop,
                FarmParcel.size_hectares,
                latest_score,
            )
            .join(FarmParcel, FarmParcel.farmer_id == FarmerProfile.id, isouter=True)
            .outerjoin(User, FarmerProfile.user_id == User.id)
            .order_by(FarmerProfile.created_at.desc())
            .limit(limit)
        )
        if q:
            query = query.where(
                or_(
                    FarmerProfile.full_name.ilike(f"%{q}%"),
                    FarmerProfile.phone_number.ilike(f"%{q}%"),
                    FarmerProfile.national_id.ilike(f"%{q}%"),
                    User.email.ilike(f"%{q}%"),
                )
            )
        if region:
            query = query.where(FarmParcel.region == region)
        if bank_id is not None:
            loan_exists = (
                select(LoanApplication.id)
                .where(LoanApplication.farmer_id == FarmerProfile.id, LoanApplication.bank_id == bank_id)
                .exists()
            )
            query = query.where(or_(FarmerProfile.registered_by_bank_id == bank_id, loan_exists))
        result = await self.db.execute(query)
        return [
            {
                "id": p.id,
                "full_name": p.full_name,
                "phone_number": p.phone_number,
                "national_id": p.national_id,
                "region": region_val,
                "primary_crop": crop_val,
                "farm_size": float(size_val) if size_val is not None else None,
                "credit_score": int(score_val) if score_val is not None else None,
                "gps_coordinates": p.gps_coordinates,
                "land_proof_document": p.land_proof_document,
                "consent_status": p.consent_status,
            }
            for p, region_val, crop_val, size_val, score_val in result.all()
        ]

    async def set_consent(self, farmer_id: str, consent: bool) -> FarmerProfile | None:
        profile = await self.get_profile(farmer_id)
        if not profile:
            return None
        profile.consent_status = consent
        profile.consent_date = datetime.now(timezone.utc) if consent else None
        await self.db.flush()
        return profile

    async def get_profile(self, farmer_id: str) -> FarmerProfile | None:
        result = await self.db.execute(select(FarmerProfile).where(FarmerProfile.id == farmer_id))
        return result.scalar_one_or_none()

    async def get_profile_by_user(self, user_id: str) -> FarmerProfile | None:
        result = await self.db.execute(select(FarmerProfile).where(FarmerProfile.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_profile_by_email(self, email: str) -> FarmerProfile | None:
        result = await self.db.execute(
            select(FarmerProfile).join(User, FarmerProfile.user_id == User.id).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def add_parcel(self, data: FarmParcelCreate) -> FarmParcel:
        parcel = FarmParcel(**data.model_dump())
        self.db.add(parcel)
        await self.db.flush()
        return parcel

    async def get_parcels(self, farmer_id: str) -> list[FarmParcel]:
        result = await self.db.execute(select(FarmParcel).where(FarmParcel.farmer_id == farmer_id))
        return list(result.scalars().all())

    async def get_farm_status(self, farmer_id: str) -> dict:
        parcels = await self.get_parcels(farmer_id)
        ndvi_trend = []
        ndvi_current = None
        if parcels:
            geo = GeospatialService()
            try:
                ndvi_trend = await geo.get_ndvi_timeseries(str(parcels[0].id), days=90)
                ndvi_current = ndvi_trend[-1]["ndvi_value"] if ndvi_trend else None
            except Exception:
                ndvi_trend = []
        health_label = "Good"
        if ndvi_current is not None:
            if ndvi_current < 0.3:
                health_label = "Poor"
            elif ndvi_current < 0.5:
                health_label = "Fair"
        return {
            "farmer_id": farmer_id,
            "ndvi_current": ndvi_current,
            "ndvi_trend": ndvi_trend,
            "crop_health_label": health_label,
        }
