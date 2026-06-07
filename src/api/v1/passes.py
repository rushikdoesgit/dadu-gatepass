import io
import uuid
import random
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, RoleChecker
from src.config import settings
from src.db.models.identity import User
from src.db.models.passes import Pass, PassType
from src.db.session import get_db
from src.services import pass_service
from src.services.qr_service import generate_qr_payload, seconds_remaining

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PassRequestSchema(BaseModel):
    pass_type: str
    purpose: str
    valid_from: datetime
    valid_until: datetime

    @model_validator(mode='after')
    def check_dates(self) -> 'PassRequestSchema':
        if self.valid_until <= self.valid_from:
            raise ValueError('valid_until must be chronologically after valid_from')
        return self


class VehicleRequestSchema(BaseModel):
    vehicle_number: str
    vehicle_model: str
    rfid_tag_id: str
    purpose: str
    valid_until: datetime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_authorized_pass(
    pass_id: str,
    current_user: User,
    db: AsyncSession,
) -> Pass:
    """
    Shared logic: validate pass_id, fetch the Pass row, enforce ownership /
    guard access, and ensure the pass is in an actionable state.
    """
    try:
        pass_uuid = uuid.UUID(pass_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pass ID format.")

    stmt = select(Pass).where(Pass.id == pass_uuid)
    result = await db.execute(stmt)
    pass_obj = result.scalar_one_or_none()

    if not pass_obj:
        raise HTTPException(status_code=404, detail="Pass not found.")

    is_owner = pass_obj.requester_id == current_user.id
    is_security = (
        getattr(current_user, "role", None) is not None
        and current_user.role.name == "GUARD"
    )
    if not is_owner and not is_security:
        raise HTTPException(status_code=403, detail="Not authorized to view this pass.")

    if pass_obj.status not in ["APPROVED", "ACTIVE"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate QR code. Pass status is {pass_obj.status}.",
        )

    if not pass_obj.qr_secret_seed:
        raise HTTPException(status_code=500, detail="Pass is missing QR secret seed.")

    return pass_obj


def _build_qr_png(payload: str) -> bytes:
    """Render *payload* as a QR code and return raw PNG bytes."""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_pass(
    pass_request: PassRequestSchema,
    current_user: User = Depends(RoleChecker(["STUDENT"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply for a new pass.
    Enforces 'Strict Sequential Trip' validation via dependency or service hook.
    """
    if await pass_service.has_active_trip(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot apply for a new pass while a current trip is in progress.",
        )

    new_pass = await pass_service.create_pass(
        db=db,
        user_id=current_user.id,
        pass_type_name=pass_request.pass_type,
        purpose=pass_request.purpose,
        valid_from=pass_request.valid_from,
        valid_until=pass_request.valid_until,
    )

    return {
        "status": "success",
        "message": "Pass requested successfully",
        "pass_id": str(new_pass.id),
        "pass_status": new_pass.status,
    }

@router.post("/vehicle-request", status_code=status.HTTP_201_CREATED)
async def request_vehicle_pass(
    request: VehicleRequestSchema,
    current_user: User = Depends(RoleChecker(["FACULTY"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Request a vehicle pass using an RFID tag.
    Restricted to FACULTY.
    """
    result = await pass_service.create_vehicle_pass(
        db=db,
        user_id=current_user.id,
        vehicle_number=request.vehicle_number,
        vehicle_model=request.vehicle_model,
        rfid_tag_id=request.rfid_tag_id,
        purpose=request.purpose,
        valid_until=request.valid_until
    )
    return result

class WardenApprovalSchema(BaseModel):
    status: str
    warden_comment: Optional[str] = None

@router.patch("/{pass_id}/status")
async def update_pass_status(
    pass_id: str,
    payload: WardenApprovalSchema,
    current_user: User = Depends(RoleChecker(["WARDEN"])),
    db: AsyncSession = Depends(get_db)
):
    try:
        pass_uuid = uuid.UUID(pass_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pass ID.")

    stmt = select(Pass).where(Pass.id == pass_uuid)
    result = await db.execute(stmt)
    pass_obj = result.scalar_one_or_none()

    if not pass_obj:
        raise HTTPException(status_code=404, detail="Pass not found.")
        
    if pass_obj.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Pass is already {pass_obj.status}.")
        
    if payload.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status must be APPROVED or REJECTED.")

    pass_obj.status = payload.status
    
    from src.db.models.passes import PassApproval
    approval = PassApproval(
        pass_id=pass_obj.id,
        approver_id=current_user.id,
        decision=payload.status,
        comments=payload.warden_comment
    )
    db.add(approval)
    await db.commit()
    
    return {"message": f"Pass {payload.status.lower()} successfully."}

class PassResponseSchema(BaseModel):
    id: str
    pass_type: str
    status: str
    valid_from: datetime
    valid_until: datetime
    purpose: str

@router.get("/", response_model=list[PassResponseSchema])
async def get_passes(
    status: Optional[str] = None,
    student_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List passes based on user role and optional filters."""
    stmt = select(Pass, PassType.name.label("pass_type_name")).join(PassType, Pass.pass_type_id == PassType.id)
    
    # Normalize the role name to a string
    user_role = current_user.role
    if hasattr(user_role, "name"):
        user_role = user_role.name

    # Apply Role-Based Scoping
    if user_role == "STUDENT":
        # Strictly filter by their own ID, ignoring any student_id query param
        stmt = stmt.where(Pass.requester_id == current_user.id)
    elif user_role in ["WARDEN", "GUARD"]:
        # Allow them to filter by a specific student if requested
        if student_id:
            try:
                student_uuid = uuid.UUID(student_id)
                stmt = stmt.where(Pass.requester_id == student_uuid)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid student_id format.")
        
        # NOTE: Jurisdiction logic for WARDEN (e.g. by hostel) would go here 
        # once Warden jurisdictions are modeled in the database.
        
    # Apply optional status filter for anyone
    if status:
        stmt = stmt.where(Pass.status == status.upper())
        
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        {
            "id": str(row.Pass.id),
            "pass_type": row.pass_type_name,
            "status": row.Pass.status,
            "valid_from": row.Pass.valid_from,
            "valid_until": row.Pass.valid_until,
            "purpose": row.Pass.purpose
        }
        for row in rows
    ]

@router.post("/{pass_id}/revoke")
async def revoke_pass(
    pass_id: str,
    current_user: User = Depends(RoleChecker(["WARDEN"])),
    db: AsyncSession = Depends(get_db)
):
    try:
        pass_uuid = uuid.UUID(pass_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pass ID.")

    stmt = select(Pass).where(Pass.id == pass_uuid)
    result = await db.execute(stmt)
    pass_obj = result.scalar_one_or_none()

    if not pass_obj:
        raise HTTPException(status_code=404, detail="Pass not found.")
        
    import datetime as dt
    pass_obj.status = "EXPIRED"
    pass_obj.revoked_at = dt.datetime.now(dt.timezone.utc)
    pass_obj.revoked_by = current_user.id
    
    await db.commit()
    
    return {"message": "Pass revoked successfully."}


@router.get("/{pass_id}/qr", response_class=Response)
async def get_pass_qr(
    pass_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the time-based dynamic QR code as a **PNG image**.

    The image encodes a ``v1:{pass_id}:{totp_token}`` payload that rotates
    every 45 seconds, preventing screenshot fraud.

    Response headers:
    - ``X-QR-Expires-In``: seconds remaining in the current TOTP window
    - ``X-QR-Refresh-Interval``: window size in seconds (always 45)
    """
    pass_obj = await _get_authorized_pass(pass_id, current_user, db)
    qr_payload = generate_qr_payload(pass_obj.id, pass_obj.qr_secret_seed)
    png_bytes = _build_qr_png(qr_payload)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-QR-Expires-In": str(seconds_remaining()),
            "X-QR-Refresh-Interval": str(settings.QR_STEP_INTERVAL_SECONDS),
        },
    )


@router.get("/{pass_id}/qr/view", response_class=Response)
async def view_pass_qr(
    pass_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    **Debug / browser endpoint** — open this URL in a new tab to see the QR
    code rendered directly.

    Identical to ``GET /{pass_id}/qr`` but sets
    ``Content-Disposition: inline`` so browsers display it instead of
    downloading it.
    """
    pass_obj = await _get_authorized_pass(pass_id, current_user, db)
    qr_payload = generate_qr_payload(pass_obj.id, pass_obj.qr_secret_seed)
    png_bytes = _build_qr_png(qr_payload)

    expires = seconds_remaining()
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": "inline",
            "X-QR-Expires-In": str(expires),
            "X-QR-Refresh-Interval": str(settings.QR_STEP_INTERVAL_SECONDS),
        },
    )

@router.post("/{pass_id}/send-otp")
async def send_visitor_otp(
    pass_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        pass_uuid = uuid.UUID(pass_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pass ID.")

    stmt = select(Pass).where(Pass.id == pass_uuid)
    result = await db.execute(stmt)
    pass_obj = result.scalar_one_or_none()

    if not pass_obj:
        raise HTTPException(status_code=404, detail="Pass not found.")

    otp_code = str(random.randint(100000, 999999))
    hashed_otp = hashlib.sha256(otp_code.encode()).hexdigest()

    from src.db.models.passes import PassOTP
    # Clear existing OTP if any
    otp_stmt = select(PassOTP).where(PassOTP.pass_id == pass_uuid)
    otp_result = await db.execute(otp_stmt)
    existing_otp = otp_result.scalar_one_or_none()
    
    if existing_otp:
        await db.delete(existing_otp)
        await db.flush()

    new_otp = PassOTP(
        pass_id=pass_uuid,
        otp_hash=hashed_otp,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(new_otp)
    await db.commit()

    print(f"\n[SMS SIMULATION] OTP for Pass {pass_id}: {otp_code}\n")
    return {"message": "OTP generated and sent successfully (simulated)."}

class VerifyOTPSchema(BaseModel):
    otp_code: str

@router.post("/{pass_id}/verify-otp")
async def verify_visitor_otp(
    pass_id: str,
    payload: VerifyOTPSchema,
    current_user: User = Depends(RoleChecker(["GUARD"])), # Usually guard verifies visitor OTP
    db: AsyncSession = Depends(get_db)
):
    try:
        pass_uuid = uuid.UUID(pass_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pass ID.")

    from src.db.models.passes import PassOTP
    otp_stmt = select(PassOTP).where(PassOTP.pass_id == pass_uuid)
    otp_result = await db.execute(otp_stmt)
    otp_obj = otp_result.scalar_one_or_none()

    if not otp_obj:
        raise HTTPException(status_code=404, detail="No OTP found for this pass.")
        
    if otp_obj.verified_at:
        raise HTTPException(status_code=400, detail="OTP has already been used.")

    if datetime.now(timezone.utc) > otp_obj.expires_at:
        raise HTTPException(status_code=400, detail="OTP has expired.")

    hashed_input = hashlib.sha256(payload.otp_code.encode()).hexdigest()
    if hashed_input != otp_obj.otp_hash:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    otp_obj.verified_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "OTP verified successfully. Access can be granted."}
