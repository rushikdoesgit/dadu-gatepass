import datetime
from uuid import UUID, uuid4
from typing import Optional, List # Added List
# pyrefly: ignore [missing-import]
from sqlalchemy import ForeignKey, String, DateTime, BigInteger
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db.models.base import Base

class Gate(Base):
    __tablename__ = "gates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False) # PEDESTRIAN, VEHICLE, MIXED

    logs: Mapped[List["AccessLog"]] = relationship(back_populates="gate")

class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pass_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("passes.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rfid_tag_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    gate_id: Mapped[UUID] = mapped_column(ForeignKey("gates.id"), nullable=False)
    
    direction: Mapped[str] = mapped_column(String(10), nullable=False) # IN, OUT
    status: Mapped[str] = mapped_column(String(20), nullable=False) # GRANTED, DENIED, LATE_ENTRY
    method: Mapped[str] = mapped_column(String(20), nullable=False) # QR, RFID, MANUAL
    
    denial_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    late_duration_seconds: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    logged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc), 
        nullable=False
    )

    gate: Mapped["Gate"] = relationship(back_populates="logs")
    
    # Updated to use back_populates for better audit querying
    pass_record: Mapped[Optional["Pass"]] = relationship(
        back_populates="logs", 
        foreign_keys=[pass_id]
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="access_logs", 
        foreign_keys=[user_id]
    )