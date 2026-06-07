from __future__ import annotations

from uuid import UUID, uuid4
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import Base, TimestampMixin
from src.db.models.enums import Role, ResidencyStatus, StudentTier

if TYPE_CHECKING:
    from src.db.models.passes import Pass
    from src.db.models.logging import AccessLog

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    requested_passes: Mapped[List["Pass"]] = relationship(
        "Pass", back_populates="requester", foreign_keys="Pass.requester_id"
    )
    student_profile: Mapped[Optional["StudentProfile"]] = relationship(
        "StudentProfile", back_populates="user", uselist=False
    )
    access_logs: Mapped[List["AccessLog"]] = relationship(
        "AccessLog", back_populates="user"
    )

class Hostel(Base):
    __tablename__ = "hostels"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    tier: Mapped[StudentTier] = mapped_column(Enum(StudentTier), nullable=False)
    residency_status: Mapped[ResidencyStatus] = mapped_column(Enum(ResidencyStatus), nullable=False)
    hostel_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("hostels.id", ondelete="SET NULL"), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="student_profile")
    hostel: Mapped[Optional["Hostel"]] = relationship("Hostel")
