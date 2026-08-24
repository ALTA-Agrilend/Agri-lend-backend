import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Numeric, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class FarmerProfile(TimestampMixin, Base):
    __tablename__ = "farmer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    national_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    mobile_money_id: Mapped[str | None] = mapped_column(String(100))
    gps_coordinates: Mapped[str | None] = mapped_column(String(100))
    land_proof_document: Mapped[str | None] = mapped_column(String(500))
    consent_status: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(String(10), default="en")
    registered_by_bank_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_partners.id"), nullable=True)

    parcels: Mapped[list["FarmParcel"]] = relationship("FarmParcel", back_populates="farmer")
    credit_scores: Mapped[list["CreditScoreRecord"]] = relationship("CreditScoreRecord", back_populates="farmer")
    loan_applications: Mapped[list["LoanApplication"]] = relationship("LoanApplication", back_populates="farmer")


class FarmParcel(TimestampMixin, Base):
    __tablename__ = "farm_parcels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmer_profiles.id"), nullable=False)
    parcel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_polygon: Mapped[str | None] = mapped_column(Text)
    size_hectares: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    primary_crop: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)

    farmer: Mapped["FarmerProfile"] = relationship("FarmerProfile", back_populates="parcels")
    observations: Mapped[list["SatelliteObservation"]] = relationship("SatelliteObservation", back_populates="parcel")
