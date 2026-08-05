from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func as sa_func
from app.models.loan import LoanApplication, LoanStatus
from app.models.farmer import FarmerProfile, FarmParcel
from app.schemas.loan import LoanApplicationCreate, LoanListFilter
from datetime import datetime, timezone
from uuid import UUID as UUIDType


def to_uuid(val: str | UUIDType | None) -> UUIDType | None:
    if val is None:
        return None
    if isinstance(val, UUIDType):
        return val
    try:
        return UUIDType(str(val))
    except (ValueError, TypeError):
        return None


class LoanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_application(self, data: LoanApplicationCreate, score: int) -> LoanApplication:
        app = LoanApplication(
            farmer_id=to_uuid(data.farmer_id),
            bank_id=to_uuid(data.bank_id),
            requested_amount=data.requested_amount,
            loan_purpose=data.loan_purpose,
            credit_score_at_application=score,
        )
        self.db.add(app)
        await self.db.flush()
        return app

    async def get_by_id(self, app_id: str | UUIDType) -> LoanApplication | None:
        uid = to_uuid(app_id)
        if not uid:
            return None
        result = await self.db.execute(select(LoanApplication).where(LoanApplication.id == uid))
        return result.scalar_one_or_none()

    async def get_applications(self, farmer_id: str | None = None, status: LoanStatus | None = None) -> list[LoanApplication]:
        query = select(LoanApplication).order_by(desc(LoanApplication.submitted_at))
        if farmer_id:
            query = query.where(LoanApplication.farmer_id == to_uuid(farmer_id))
        if status:
            query = query.where(LoanApplication.status == status)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_filtered_applications(self, filters: LoanListFilter) -> dict:
        base_query = (
            select(
                LoanApplication, FarmerProfile.full_name, FarmerProfile.phone_number,
                FarmParcel.region, FarmParcel.primary_crop, FarmParcel.size_hectares,
            )
            .join(FarmerProfile, LoanApplication.farmer_id == FarmerProfile.id)
            .join(FarmParcel, FarmParcel.farmer_id == FarmerProfile.id, isouter=True)
        )
        count_query = select(sa_func.count(LoanApplication.id)).select_from(LoanApplication).join(
            FarmerProfile, LoanApplication.farmer_id == FarmerProfile.id
        ).join(FarmParcel, FarmParcel.farmer_id == FarmerProfile.id, isouter=True)

        if filters.status:
            base_query = base_query.where(LoanApplication.status == filters.status)
            count_query = count_query.where(LoanApplication.status == filters.status)
        if filters.region:
            base_query = base_query.where(FarmParcel.region == filters.region)
            count_query = count_query.where(FarmParcel.region == filters.region)
        if filters.crop_type:
            base_query = base_query.where(FarmParcel.primary_crop == filters.crop_type)
            count_query = count_query.where(FarmParcel.primary_crop == filters.crop_type)
        if filters.min_amount is not None:
            base_query = base_query.where(LoanApplication.requested_amount >= filters.min_amount)
            count_query = count_query.where(LoanApplication.requested_amount >= filters.min_amount)
        if filters.max_amount is not None:
            base_query = base_query.where(LoanApplication.requested_amount <= filters.max_amount)
            count_query = count_query.where(LoanApplication.requested_amount <= filters.max_amount)

        total_res = await self.db.execute(count_query)
        total = total_res.scalar() or 0

        base_query = base_query.order_by(desc(LoanApplication.submitted_at))
        offset = (filters.page - 1) * filters.page_size
        base_query = base_query.offset(offset).limit(filters.page_size)

        result = await self.db.execute(base_query)
        rows = result.all()

        items = [
            {
                "id": str(app.id),
                "farmer_id": str(app.farmer_id),
                "bank_id": str(app.bank_id),
                "requested_amount": float(app.requested_amount),
                "amount_requested": float(app.requested_amount),
                "loan_purpose": app.loan_purpose,
                "credit_score_at_application": app.credit_score_at_application,
                "credit_score_snapshot": app.credit_score_at_application,
                "status": app.status.value,
                "submitted_at": app.submitted_at,
                "reviewed_at": app.reviewed_at,
                "farmer_name": full_name,
                "farmer_phone": phone_number,
                "region": region,
                "crop_type": primary_crop,
                "farm_size": float(size_hectares) if size_hectares else 0.0,
            }
            for app, full_name, phone_number, region, primary_crop, size_hectares in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": filters.page,
            "page_size": filters.page_size,
            "total_pages": -(-total // filters.page_size) if total > 0 else 0,
        }

    async def get_applicant_detail(self, app_id: str | UUIDType) -> dict | None:
        uid = to_uuid(app_id)
        if not uid:
            return None
        result = await self.db.execute(
            select(LoanApplication).where(LoanApplication.id == uid)
        )
        app = result.scalar_one_or_none()
        if not app:
            return None
        profile_result = await self.db.execute(
            select(FarmerProfile).where(FarmerProfile.id == app.farmer_id)
        )
        profile = profile_result.scalar_one_or_none()
        parcel_result = await self.db.execute(
            select(FarmParcel).where(FarmParcel.farmer_id == app.farmer_id).limit(1)
        )
        parcel = parcel_result.scalar_one_or_none()
        from app.models.credit import CreditScoreRecord
        score_result = await self.db.execute(
            select(CreditScoreRecord)
            .where(CreditScoreRecord.farmer_id == app.farmer_id)
            .order_by(desc(CreditScoreRecord.calculated_at))
            .limit(5)
        )
        scores = score_result.scalars().all()

        current_score = scores[0] if scores else None
        score_trend = "stable"
        if scores and len(scores) >= 2:
            if scores[0].score_value > scores[-1].score_value:
                score_trend = "improving"
            elif scores[0].score_value < scores[-1].score_value:
                score_trend = "declining"

        return {
            "application_id": str(app.id),
            "farmer_id": str(app.farmer_id),
            "farmer_name": profile.full_name if profile else "",
            "farmer_phone": profile.phone_number if profile else "",
            "farmer_region": parcel.region if parcel else "",
            "farmer_crop": parcel.primary_crop if parcel else "",
            "farm_size_hectares": float(parcel.size_hectares) if parcel and parcel.size_hectares else None,
            "requested_amount": float(app.requested_amount),
            "amount_requested": float(app.requested_amount),
            "loan_purpose": app.loan_purpose,
            "status": app.status.value,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "credit_score_at_application": app.credit_score_at_application,
            "credit_score_snapshot": app.credit_score_at_application,
            "credit_score_current": current_score.score_value if current_score else None,
            "risk_tier": current_score.risk_tier.value if current_score else None,
            "score_trend": score_trend,
            "confidence_rating": float(current_score.confidence_rating) if current_score else None,
            "consent_status": profile.consent_status if profile else False,
            "land_verified": bool(profile.land_proof_document) if profile else False,
        }

    async def get_dashboard_report(self) -> dict:
        total_q = await self.db.execute(sa_func.count(LoanApplication.id).select())
        total = total_q.scalar() or 0
        counts = {}
        for status in LoanStatus:
            result = await self.db.execute(
                select(sa_func.count(LoanApplication.id)).where(LoanApplication.status == status)
            )
            counts[status.value] = result.scalar() or 0
        return {
            "total": total,
            "approved": counts.get("APPROVED", 0),
            "rejected": counts.get("REJECTED", 0),
            "pending": counts.get("PENDING", 0),
            "disbursed": counts.get("DISBURSED", 0),
        }

    async def get_high_risk_warnings(self) -> list[dict]:
        query = (
            select(LoanApplication, FarmerProfile.full_name)
            .join(FarmerProfile, LoanApplication.farmer_id == FarmerProfile.id)
            .where(
                LoanApplication.status == LoanStatus.PENDING,
                LoanApplication.credit_score_at_application < 500,
            )
            .order_by(LoanApplication.credit_score_at_application.asc())
            .limit(20)
        )
        result = await self.db.execute(query)
        rows = result.all()
        return [
            {
                "application_id": str(app.id),
                "farmer_name": full_name,
                "amount": float(app.requested_amount),
                "score": app.credit_score_at_application,
                "risk_tier": "HIGH",
                "reason": f"Credit score {app.credit_score_at_application} is below 500 threshold",
            }
            for app, full_name in rows
        ]

    async def review_application(self, app_id: str | UUIDType, status: LoanStatus, reviewer_id: str) -> LoanApplication | None:
        app = await self.get_by_id(app_id)
        if not app:
            return None
        app.status = status
        app.reviewed_by = to_uuid(reviewer_id)
        app.reviewed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return app
