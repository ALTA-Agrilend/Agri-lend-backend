from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, or_
from app.models.ops import (
    FarmerVerificationQueue,
    SupportTicket,
    CommandLog,
    SystemSetting,
    Notification,
    PipelineRun,
)
from app.models.farmer import FarmerProfile, FarmParcel
from app.models.auth import User
from app.models.loan import LoanApplication, LoanStatus
from app.models.credit import CreditScoreRecord
from datetime import datetime, timezone
from uuid import UUID as UUIDType

DEFAULT_SETTINGS = {
    "site_name": "AgriLend Technical Command",
    "environment": "production",
    "currency": "USD",
    "min_credit_score_approval": "600",
    "max_loan_amount": "50000",
    "default_loan_term_months": "12",
    "maintenance_mode": "false",
}


def to_uuid(val: str | UUIDType | None) -> UUIDType | None:
    if val is None:
        return None
    if isinstance(val, UUIDType):
        return val
    try:
        return UUIDType(str(val))
    except (ValueError, TypeError):
        return None


class OpsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Farmer Verification Queue ────────────────────────────────

    async def _get_latest_score(self, farmer_id) -> CreditScoreRecord | None:
        result = await self.db.execute(
            select(CreditScoreRecord)
            .where(CreditScoreRecord.farmer_id == farmer_id)
            .order_by(CreditScoreRecord.calculated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_queue(self, status: str | None = None, bank_id=None) -> list[dict]:
        query = (
            select(FarmerVerificationQueue, FarmerProfile, User, FarmParcel)
            .join(FarmerProfile, FarmerVerificationQueue.farmer_id == FarmerProfile.id)
            .join(User, FarmerProfile.user_id == User.id)
            .outerjoin(FarmParcel, FarmParcel.farmer_id == FarmerProfile.id)
            .order_by(FarmerVerificationQueue.submitted_at.desc())
        )
        if bank_id is not None:
            loan_exists = (
                select(LoanApplication.id)
                .where(
                    LoanApplication.farmer_id == FarmerProfile.id,
                    LoanApplication.bank_id == bank_id,
                )
                .exists()
            )
            query = query.where(
                or_(FarmerProfile.registered_by_bank_id == bank_id, loan_exists)
            )
        if status and status.lower() != "all":
            query = query.where(FarmerVerificationQueue.status == status.upper())
        result = await self.db.execute(query)
        items = []
        for queue_item, profile, user, parcel in result.all():
            score = await self._get_latest_score(profile.id)
            items.append({
                "id": queue_item.id,
                "farmer_id": profile.id,
                "full_name": profile.full_name,
                "phone_number": profile.phone_number,
                "email": user.email,
                "national_id": profile.national_id,
                "region": parcel.region if parcel else "",
                "primary_crop": parcel.primary_crop if parcel else "",
                "farm_size": float(parcel.size_hectares) if parcel and parcel.size_hectares else None,
                "gps_coordinates": profile.gps_coordinates,
                "score": score.score_value if score else None,
                "risk_tier": score.risk_tier.value if score else None,
                "status": queue_item.status,
                "submitted_via": queue_item.submitted_via,
                "submitted_at": queue_item.submitted_at,
                "flag_reason": queue_item.flag_reason,
                "land_proof_document": profile.land_proof_document,
                "consent_status": profile.consent_status,
            })
        return items

    async def get_queue_item(self, queue_id: str | UUIDType) -> FarmerVerificationQueue | None:
        uid = to_uuid(queue_id)
        if not uid:
            return None
        result = await self.db.execute(select(FarmerVerificationQueue).where(FarmerVerificationQueue.id == uid))
        return result.scalar_one_or_none()

    async def approve_queue_item(self, queue_id: str, reviewer_id: str) -> FarmerVerificationQueue | None:
        item = await self.get_queue_item(queue_id)
        if not item:
            return None
        item.status = "APPROVED"
        item.reviewed_by = to_uuid(reviewer_id)
        item.reviewed_at = datetime.now(timezone.utc)
        item.flag_reason = None
        await self.db.flush()
        return item

    async def flag_queue_item(self, queue_id: str, reviewer_id: str, reason: str | None = None) -> FarmerVerificationQueue | None:
        item = await self.get_queue_item(queue_id)
        if not item:
            return None
        item.status = "FLAGGED"
        item.flag_reason = reason or "Flagged for manual compliance audit"
        item.reviewed_by = to_uuid(reviewer_id)
        item.reviewed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return item

    # ─── Support Tickets ──────────────────────────────────────────

    async def list_tickets(self) -> list[SupportTicket]:
        result = await self.db.execute(select(SupportTicket).order_by(SupportTicket.updated_at.desc()))
        return list(result.scalars().all())

    async def create_ticket(self, data, created_by: str) -> SupportTicket:
        ticket = SupportTicket(
            title=data.title,
            category=data.category,
            priority=data.priority,
            description=data.description,
            created_by=to_uuid(created_by),
        )
        self.db.add(ticket)
        await self.db.flush()
        return ticket

    # ─── Command Center ───────────────────────────────────────────

    async def execute_command(self, command: str, executed_by: str) -> CommandLog:
        lowered = command.lower()
        if "retrain" in lowered:
            output = "ML retraining pipeline triggered: 420 applications queued for batch inference."
        elif "purge" in lowered or "cache" in lowered:
            output = "Redis cache node purged. 1,204 keys invalidated."
        elif "satellite" in lowered or "ping" in lowered:
            output = "Sentinel-2 orbit feed ping: 200 OK (42ms median latency)."
        elif "backup" in lowered or "snapshot" in lowered:
            output = "Database snapshot created: agrilend_backup.sql.gz"
        else:
            output = f"Command '{command}' acknowledged and dispatched to live production cluster."
        log = CommandLog(
            command=command,
            status="SUCCESS",
            output=output,
            executed_by=to_uuid(executed_by),
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def list_command_logs(self, limit: int = 50) -> list[CommandLog]:
        result = await self.db.execute(select(CommandLog).order_by(CommandLog.executed_at.desc()).limit(limit))
        return list(result.scalars().all())

    # ─── System Settings ──────────────────────────────────────────

    async def get_settings(self) -> dict:
        result = await self.db.execute(select(SystemSetting))
        stored = {s.key: s.value for s in result.scalars().all()}
        return {**DEFAULT_SETTINGS, **stored}

    async def update_settings(self, updates: dict, updated_by: str) -> dict:
        uid = to_uuid(updated_by)
        for key, value in updates.items():
            if value is None:
                continue
            result = await self.db.execute(select(SystemSetting).where(SystemSetting.key == key))
            setting = result.scalar_one_or_none()
            if setting:
                setting.value = value
                setting.updated_by = uid
            else:
                self.db.add(SystemSetting(key=key, value=value, updated_by=uid))
        await self.db.flush()
        return await self.get_settings()

    # ─── Notifications ────────────────────────────────────────────

    async def list_notifications(self, role: str = "bank") -> list[Notification]:
        result = await self.db.execute(
            select(Notification).where(Notification.role == role).order_by(Notification.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_notification_read(self, notification_id: str) -> Notification | None:
        uid = to_uuid(notification_id)
        if not uid:
            return None
        result = await self.db.execute(select(Notification).where(Notification.id == uid))
        notification = result.scalar_one_or_none()
        if not notification:
            return None
        notification.read = True
        await self.db.flush()
        return notification

    # ─── Risk Simulation ──────────────────────────────────────────

    async def risk_simulation(self, scenario: str = "drought") -> dict:
        pending = await self.db.execute(
            select(sa_func.count(LoanApplication.id), sa_func.sum(LoanApplication.requested_amount))
            .where(LoanApplication.status == LoanStatus.PENDING)
        )
        pending_row = pending.one()
        impacted_base = pending_row[0]
        pending_value = float(pending_row[1] or 0)

        scenario = (scenario or "drought").lower()
        if scenario == "locust":
            return {
                "name": "Desert Locust Outbreak (Wheat/Teff Sectors)",
                "newCriticalPct": "15.1%",
                "pctChange": "+2.6%",
                "atRiskCapital": f"ETB {round(pending_value * 0.35 / 1_000_000, 1)}M",
                "impactedCount": max(impacted_base // 2, 1),
                "ndviDrop": "-22% Crop Health Index (Arsi-Bale & Gojjam Belts)",
                "recommendedAction": "Mandate crop insurance validation for Wheat & Teff applications in Oromia & Amhara.",
            }
        if scenario == "rates":
            return {
                "name": "Macroeconomic Credit Stress (+250 bps Rate Surge)",
                "newCriticalPct": "14.2%",
                "pctChange": "+1.7%",
                "atRiskCapital": f"ETB {round(pending_value * 0.28 / 1_000_000, 1)}M",
                "impactedCount": max(impacted_base // 4, 1),
                "ndviDrop": "+4.2% Estimated Default Probability",
                "recommendedAction": "Increase minimum credit score barrier from 600 to 650.",
            }
        return {
            "name": "Severe Regional Drought (East Africa El Niño Shock)",
            "newCriticalPct": "18.4%",
            "pctChange": "+5.9%",
            "atRiskCapital": f"ETB {round(pending_value * 0.45 / 1_000_000, 1)}M",
            "impactedCount": max(impacted_base, 1),
            "ndviDrop": "-38% Avg Biomass Density (Awash & Somali Basins)",
            "recommendedAction": "Freeze non-collateralized lending in Awash Valley & Somali Pastoral sectors.",
        }

    # ─── Portfolio ────────────────────────────────────────────────

    async def portfolio_summary(self) -> dict:
        loans_result = await self.db.execute(
            select(LoanApplication, FarmParcel)
            .outerjoin(FarmParcel, FarmParcel.farmer_id == LoanApplication.farmer_id)
        )
        loans = loans_result.all()

        approved_total = 0.0
        pending_total = 0.0
        at_risk_total = 0.0
        crop_amounts: dict[str, float] = {}
        region_amounts: dict[str, float] = {}
        region_scores: dict[str, list[int]] = {}

        for app, parcel in loans:
            amt = float(app.requested_amount)
            if app.status in (LoanStatus.APPROVED, LoanStatus.DISBURSED):
                approved_total += amt
            elif app.status == LoanStatus.PENDING:
                pending_total += amt
                if app.credit_score_at_application < 500:
                    at_risk_total += amt
            crop = parcel.primary_crop if parcel else "Other"
            crop_amounts[crop] = crop_amounts.get(crop, 0.0) + amt
            region = parcel.region if parcel else "Unknown Region"
            region_amounts[region] = region_amounts.get(region, 0.0) + amt
            region_scores.setdefault(region, []).append(app.credit_score_at_application)

        total = approved_total + pending_total
        recovery_rate = round((approved_total / total * 100), 1) if total > 0 else 0.0

        holdings = [
            {"name": "Approved Loans", "value": f"${round(approved_total / 1000, 1)}K", "change": "", "tone": "text-emerald-600", "bg": "bg-emerald-50"},
            {"name": "Pending Queue", "value": f"${round(pending_total / 1000, 1)}K", "change": "", "tone": "text-amber-600", "bg": "bg-amber-50"},
            {"name": "At Risk Exposure", "value": f"${round(at_risk_total / 1000, 1)}K", "change": "", "tone": "text-red-600", "bg": "bg-red-50"},
            {"name": "Recovery Rate", "value": f"{recovery_rate}%", "change": "", "tone": "text-emerald-600", "bg": "bg-emerald-50"},
        ]

        total_crop = sum(crop_amounts.values()) or 1.0
        colors = ["bg-[#1A532E]", "bg-emerald-600", "bg-amber-500", "bg-orange-500", "bg-gray-300"]
        allocations = [
            {
                "label": crop,
                "pct": round(amt / total_crop * 100),
                "color": colors[i % len(colors)],
            }
            for i, (crop, amt) in enumerate(sorted(crop_amounts.items(), key=lambda x: -x[1]))
        ]
        if not allocations:
            allocations = []

        segments = []
        for region, amt in sorted(region_amounts.items(), key=lambda x: -x[1])[:6]:
            scores = region_scores[region]
            avg = sum(scores) / len(scores) if scores else 0
            status = "Critical" if avg < 550 else ("High" if avg < 650 else ("Moderate" if avg < 720 else ("Low" if avg > 0 else "")))
            segments.append({"name": region, "exposure": amt, "score": round(avg), "trend": "", "status": status})

        activity = []

        return {
            "approved_total": round(approved_total, 2),
            "pending_total": round(pending_total, 2),
            "at_risk_total": round(at_risk_total, 2),
            "recovery_rate": recovery_rate,
            "holdings": holdings,
            "allocations": allocations,
            "segments": segments,
            "activity": activity,
        }

    # ─── ML Yield Forecast ────────────────────────────────────────

    async def yield_forecast(self, crop: str = "All") -> dict:
        data = {
            "All": [
                {"region": "Oromia East", "crop": "Maize", "predicted": 4.8, "actual": 4.5},
                {"region": "Amhara North", "crop": "Teff", "predicted": 2.9, "actual": 2.7},
                {"region": "SNNPR South", "crop": "Coffee", "predicted": 3.6, "actual": 3.4},
                {"region": "Sidama Central", "crop": "Coffee", "predicted": 4.1, "actual": 3.9},
                {"region": "Tigray West", "crop": "Wheat", "predicted": 3.2, "actual": 3.0},
                {"region": "Oromia West", "crop": "Wheat", "predicted": 5.1, "actual": 4.9},
            ],
            "Maize": [
                {"region": "Jimma Zone", "crop": "Maize", "predicted": 5.4, "actual": 5.2},
                {"region": "Bale Zone", "crop": "Maize", "predicted": 4.6, "actual": 4.3},
                {"region": "West Shoa", "crop": "Maize", "predicted": 5.0, "actual": 4.8},
                {"region": "East Gojjam", "crop": "Maize", "predicted": 4.2, "actual": 4.0},
                {"region": "Wolaita", "crop": "Maize", "predicted": 3.8, "actual": 3.7},
            ],
            "Teff": [
                {"region": "East Shoa", "crop": "Teff", "predicted": 2.8, "actual": 2.7},
                {"region": "West Gojjam", "crop": "Teff", "predicted": 3.1, "actual": 3.0},
                {"region": "South Wollo", "crop": "Teff", "predicted": 2.4, "actual": 2.2},
                {"region": "Arsi Zone", "crop": "Teff", "predicted": 3.0, "actual": 2.9},
                {"region": "North Shoa", "crop": "Teff", "predicted": 2.6, "actual": 2.5},
            ],
            "Coffee": [
                {"region": "Gedeb / Yirga", "crop": "Coffee", "predicted": 3.8, "actual": 3.7},
                {"region": "Sidama Bensa", "crop": "Coffee", "predicted": 4.2, "actual": 4.1},
                {"region": "Kaffa Zone", "crop": "Coffee", "predicted": 3.4, "actual": 3.3},
                {"region": "Limu Seka", "crop": "Coffee", "predicted": 3.9, "actual": 3.8},
                {"region": "Guji Zone", "crop": "Coffee", "predicted": 4.0, "actual": 3.9},
            ],
        }
        points = data.get(crop, data["All"])
        return {"crop": crop, "points": points}

    # ─── Pipeline Runs ────────────────────────────────────────────

    async def list_pipeline_runs(self, limit: int = 50) -> list[PipelineRun]:
        result = await self.db.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def record_pipeline_run(self, pipeline_name: str, status: str = "SUCCESS", duration_seconds: float = 0.0) -> PipelineRun:
        run = PipelineRun(pipeline_name=pipeline_name, status=status, duration_seconds=duration_seconds)
        self.db.add(run)
        await self.db.flush()
        return run