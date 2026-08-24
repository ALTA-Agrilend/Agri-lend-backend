import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class BankPartner(TimestampMixin, Base):
    __tablename__ = "bank_partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("12.00"))
    subscription_tier: Mapped[str] = mapped_column(String(50), default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
