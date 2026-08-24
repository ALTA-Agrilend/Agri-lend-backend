from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.db.session import get_db
from app.schemas.ops import (
    QueueItemResponse,
    SupportTicketCreate,
    SupportTicketResponse,
    CommandExecuteRequest,
    CommandExecuteResponse,
    CommandLogEntry,
    SystemSettingsUpdate,
    SystemSettingsResponse,
    NotificationResponse,
    RiskSimulationRequest,
    RiskSimulationResponse,
    PortfolioSummary,
    YieldForecastResponse,
    PipelineRunResponse,
)
from app.services.ops import OpsService
from app.services.auth import AuthService
from app.core.dependencies import get_current_user, get_scope_bank_id, require_roles

router = APIRouter(tags=["Operations"])


# ─── Farmer Verification Queue ──────────────────────────────────

@router.get("/admin/farmers-queue", response_model=list[QueueItemResponse],
            summary="Farmer verification queue",
            description="Returns mobile-registered farmers awaiting KYC verification. Filters by status "
                        "(PENDING/APPROVED/FLAGGED). Bank users see only farmers tied to their institution; "
                        "verification decisions are made by the platform.",
            responses={403: {"description": "Insufficient permissions"}})
async def farmers_queue(
    status: str = Query("all", description="Filter by queue status"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = OpsService(db)
    return await service.list_queue(status, bank_id=get_scope_bank_id(current_user))


@router.post("/admin/farmers-queue/{queue_id}/approve",
             summary="Approve a farmer verification",
             description="Approves a pending farmer registration into the active registry. "
                         "Verification is performed exclusively by the platform (Platform Admin).",
             responses={403: {"description": "Insufficient permissions"},
                        404: {"description": "Queue item not found"}})
async def approve_queue_item(
    queue_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    item = await service.approve_queue_item(queue_id, current_user["sub"])
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    audit = AuthService(db)
    await audit.log_audit(
        user_id=current_user["sub"],
        action="APPROVE_FARMER",
        resource="FarmerVerificationQueue",
        resource_id=queue_id,
        ip=request.client.host if request.client else None,
    )
    return {"detail": "Farmer verification approved"}


@router.post("/admin/farmers-queue/{queue_id}/flag",
             summary="Flag a farmer verification",
             description="Flags a farmer registration for manual compliance audit. "
                         "Flagging is performed exclusively by the platform (Platform Admin).",
             responses={403: {"description": "Insufficient permissions"},
                        404: {"description": "Queue item not found"}})
async def flag_queue_item(
    queue_id: str,
    payload: dict = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    reason = (payload or {}).get("reason") if payload else None
    service = OpsService(db)
    item = await service.flag_queue_item(queue_id, current_user["sub"], reason)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    audit = AuthService(db)
    await audit.log_audit(
        user_id=current_user["sub"],
        action="FLAG_FARMER",
        resource="FarmerVerificationQueue",
        resource_id=queue_id,
        details=reason,
        ip=request.client.host if request.client else None,
    )
    return {"detail": "Farmer verification flagged for compliance audit"}


# ─── Support Tickets ─────────────────────────────────────────────

@router.get("/admin/support/tickets", response_model=list[SupportTicketResponse],
            summary="List support tickets",
            description="Returns all technical support tickets. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def list_tickets(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return await service.list_tickets()


@router.post("/admin/support/tickets", response_model=SupportTicketResponse, status_code=201,
             summary="Create support ticket",
             description="Creates a new technical support ticket. Requires Platform Admin.",
             responses={403: {"description": "Insufficient permissions"}})
async def create_ticket(
    data: SupportTicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return await service.create_ticket(data, current_user["sub"])


# ─── Command Center ──────────────────────────────────────────────

@router.post("/admin/command/execute", response_model=CommandExecuteResponse,
             summary="Execute admin command",
             description="Dispatches an operational command to the platform. Requires Platform Admin.",
             responses={403: {"description": "Insufficient permissions"}})
async def execute_command(
    data: CommandExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    log = await service.execute_command(data.command, current_user["sub"])
    return {"status": log.status, "output": log.output or data.command}


@router.get("/admin/command/logs", response_model=list[CommandLogEntry],
            summary="Command execution history",
            description="Returns recently executed admin commands. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def command_logs(
    limit: int = Query(50, ge=1, le=200, description="Number of log entries"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return await service.list_command_logs(limit)


# ─── System Settings ─────────────────────────────────────────────

@router.get("/admin/settings", response_model=SystemSettingsResponse,
            summary="Get system settings",
            description="Returns platform-wide system settings. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return {"settings": await service.get_settings()}


@router.put("/admin/settings", response_model=SystemSettingsResponse,
            summary="Update system settings",
            description="Updates platform system settings. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def update_settings(
    data: SystemSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    updates = data.model_dump(exclude_none=True)
    settings = await service.update_settings(updates, current_user["sub"])
    audit = AuthService(db)
    await audit.log_audit(
        user_id=current_user["sub"],
        action="UPDATE_SETTINGS",
        resource="SystemSetting",
        resource_id="platform",
        details=", ".join(updates.keys()),
        ip=request.client.host if request.client else None,
    )
    return {"settings": settings}


# ─── Notifications ───────────────────────────────────────────────

@router.get("/notifications", response_model=list[NotificationResponse],
            summary="List notifications",
            description="Returns role-scoped notifications for the authenticated channel (bank or admin).")
async def list_notifications(
    role: str = Query("bank", description="Notification channel: bank or admin"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    service = OpsService(db)
    return await service.list_notifications(role)


@router.post("/notifications/{notification_id}/read",
             summary="Mark notification read",
             description="Marks a single notification as read.",
             responses={404: {"description": "Notification not found"}})
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    service = OpsService(db)
    notification = await service.mark_notification_read(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"detail": "Notification marked as read"}


# ─── Risk Simulation ─────────────────────────────────────────────

@router.post("/loans/reports/heatmap/simulate", response_model=RiskSimulationResponse,
             summary="Risk heatmap simulation",
             description="Simulates the impact of a stress scenario (drought, locust, rates) on the pending loan portfolio.",
             responses={403: {"description": "Insufficient permissions"}})
async def simulate_risk(
    data: RiskSimulationRequest = RiskSimulationRequest(scenario="drought"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = OpsService(db)
    return await service.risk_simulation(data.scenario)


# ─── Portfolio ───────────────────────────────────────────────────

@router.get("/portfolio", response_model=PortfolioSummary,
            summary="Portfolio summary",
            description="Returns the loan portfolio summary including holdings, crop allocations, and regional exposure segments.",
            responses={403: {"description": "Insufficient permissions"}})
async def portfolio_summary(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Bank Analyst", "Bank Administrator", "Platform Admin")),
):
    service = OpsService(db)
    return await service.portfolio_summary()


# ─── ML Yield Forecast ───────────────────────────────────────────

@router.get("/admin/ml/yield-forecast", response_model=YieldForecastResponse,
            summary="Yield forecast telemetry",
            description="Returns predicted vs actual crop yield telemetry. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def yield_forecast(
    crop: str = Query("All", description="Filter by crop type"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return await service.yield_forecast(crop)


# ─── Data Pipeline Runs ──────────────────────────────────────────

@router.get("/admin/pipelines/runs", response_model=list[PipelineRunResponse],
            summary="Pipeline run history",
            description="Returns the execution history of data ingestion pipelines. Requires Platform Admin.",
            responses={403: {"description": "Insufficient permissions"}})
async def pipeline_runs(
    limit: int = Query(50, ge=1, le=200, description="Number of runs"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_roles("Platform Admin")),
):
    service = OpsService(db)
    return await service.list_pipeline_runs(limit)


@router.post("/admin/pipelines/trigger",
             summary="Trigger a data pipeline",
             description="Triggers a data ingestion pipeline run. Requires Platform Admin.",
             responses={403: {"description": "Insufficient permissions"}})
async def trigger_pipeline(
    payload: dict = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("Platform Admin")),
):
    pipeline_name = (payload or {}).get("pipeline_name") or "Unknown Pipeline"
    service = OpsService(db)
    await service.record_pipeline_run(pipeline_name, status="RUNNING", duration_seconds=0.0)
    audit = AuthService(db)
    await audit.log_audit(
        user_id=current_user["sub"],
        action="TRIGGER_PIPELINE",
        resource="PipelineRun",
        resource_id=pipeline_name,
        ip=None,
    )
    return {"detail": f"Pipeline '{pipeline_name}' triggered successfully"}