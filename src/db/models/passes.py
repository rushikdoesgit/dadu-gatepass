import datetime
from uuid import UUID, uuid4
from typing import Optional, List

from sqlalchemy import ForeignKey, String, Boolean, DateTime, select, exists, and_
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession

# Note: Ensure these paths match your project structure
from src.db.models.base import Base, TimestampMixin
from src.db.models.enums import PassStatus

class PassBatch(Base):
    __tablename__ = "pass_batches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )

    passes: Mapped[List["Pass"]] = relationship(back_populates="batch")
    # host: Mapped["User"] = relationship(foreign_keys=[host_user_id]) # Requires User import

class PassType(Base):
    __tablename__ = "pass_types"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False) # e.g., DAY, OUTSTATION, VACATION
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    passes: Mapped[List["Pass"]] = relationship(back_populates="pass_type")

class Pass(Base, TimestampMixin):
    __tablename__ = "passes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("pass_batches.id", ondelete="SET NULL"), nullable=True)
    pass_type_id: Mapped[UUID] = mapped_column(ForeignKey("pass_types.id"), nullable=False)
    requester_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    
    # Core logic for tracking trips
    has_exited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_entered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    valid_from: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    
    qr_secret_seed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    batch: Mapped[Optional["PassBatch"]] = relationship(back_populates="passes")
    pass_type: Mapped["PassType"] = relationship(back_populates="passes")
    
    requester: Mapped["User"] = relationship(
        "User", back_populates="requested_passes", foreign_keys=[requester_id]
    )
    
    approvals: Mapped[List["PassApproval"]] = relationship(
        back_populates="pass_obj", cascade="all, delete-orphan"
    )
    otp: Mapped[Optional["PassOTP"]] = relationship(
        back_populates="pass_obj", uselist=False, cascade="all, delete-orphan"
    )
    vehicle: Mapped[Optional["PassVehicle"]] = relationship(
        back_populates="pass_obj", uselist=False, cascade="all, delete-orphan"
    )
    logs: Mapped[List["AccessLog"]] = relationship(
        back_populates="pass_record", cascade="all, delete-orphan"
    )

    @classmethod
    async def check_active_trip_exists(cls, session: AsyncSession, requester_id: UUID) -> bool:
        """Enforces the 'Strict Sequential Trip' rule.
        Returns True if the user is currently off-campus (exited but not returned)
        on a valid pass.
        """
        stmt = select(exists().where(
            and_(
                cls.requester_id == requester_id,
                cls.has_exited == True,
                cls.has_entered == False,
                # Ignore cancelled, expired, or rejected passes
                cls.status.in_(["APPROVED", "ACTIVE"]) 
            )
        ))
        return await session.scalar(stmt)

class PassOTP(Base):
    __tablename__ = "pass_otps"

    pass_id: Mapped[UUID] = mapped_column(
        ForeignKey("passes.id", ondelete="CASCADE"), primary_key=True
    )
    otp_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Renamed from 'pass' to avoid Python keyword conflict
    pass_obj: Mapped["Pass"] = relationship(back_populates="otp")

class PassVehicle(Base):
    __tablename__ = "pass_vehicles"

    pass_id: Mapped[UUID] = mapped_column(
        ForeignKey("passes.id", ondelete="CASCADE"), primary_key=True
    )
    vehicle_number: Mapped[str] = mapped_column(String(20), nullable=False)
    rfid_tag_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    vehicle_model: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Renamed from 'pass' to avoid Python keyword conflict
    pass_obj: Mapped["Pass"] = relationship(back_populates="vehicle")

class PassApproval(Base):
    __tablename__ = "pass_approvals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    pass_id: Mapped[UUID] = mapped_column(ForeignKey("passes.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False) # APPROVED, REJECTED
    comments: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )

    # Renamed from 'pass' to avoid Python keyword conflict
    pass_obj: Mapped["Pass"] = relationship(back_populates="approvals")

class BlacklistedRFID(Base):
    __tablename__ = "blacklisted_rfids"

    rfid_tag_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    blacklisted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )