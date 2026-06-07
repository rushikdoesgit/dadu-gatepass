from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
import uuid
from datetime import datetime, timezone

from src.db.session import get_db
from src.services import gate_service
from src.db.models.passes import Pass
from src.db.models.logging import AccessLog
from src.db.models.identity import User
from src.api.dependencies import RoleChecker
from src.services.qr_service import verify_qr_scan

router = APIRouter()




class VerifyRequestSchema(BaseModel):
    scanned_payload: str
    gate_id: str
    direction: str # e.g., "IN" or "OUT"

@router.post("/verify")
async def verify_pass(
    request: VerifyRequestSchema,
    current_user: User = Depends(RoleChecker(["GUARD"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced Guard Verification Endpoint.
    Validates dynamic TOTP, enforces approval/state rules, and detects late entry.
    """
    try:
        gate_uuid = uuid.UUID(request.gate_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid gate ID.")

    parts = request.scanned_payload.split(":")
    if len(parts) != 3:
        return {"status": "Access Denied", "reason": "Invalid payload format"}
    
    version, pass_id_str, token = parts
    
    try:
        pass_uuid = uuid.UUID(pass_id_str)
    except ValueError:
        return {"status": "Access Denied", "reason": "Invalid Pass ID in payload"}

    stmt = select(Pass).options(selectinload(Pass.requester)).where(Pass.id == pass_uuid)
    result = await db.execute(stmt)
    pass_obj = result.scalar_one_or_none()

    if not pass_obj:
        return {"status": "Access Denied", "reason": "Pass not found"}

    now = datetime.now(timezone.utc)
    direction = request.direction.upper()
    
    def create_log(access_status: str, reason: str = None, late_duration: int = None):
        return AccessLog(
            pass_id=pass_obj.id,
            user_id=pass_obj.requester_id,
            gate_id=gate_uuid,
            direction=direction,
            status=access_status,
            method="QR",
            denial_reason=reason,
            late_duration_seconds=late_duration
        )

    # State Machine & Status Rules
    if direction in ["OUT", "EXIT"]:
        if pass_obj.status == "PENDING":
            db.add(create_log("DENIED", "This pass has not been approved by the Warden yet."))
            await db.commit()
            return {"status": "Access Denied", "reason": "This pass has not been approved by the Warden yet."}
        
        if pass_obj.status == "ACTIVE":
            db.add(create_log("DENIED", "User is already out. Must scan IN to reset."))
            await db.commit()
            return {"status": "Access Denied", "reason": "User is already out. Must scan IN to reset."}

    if pass_obj.status not in ["APPROVED", "ACTIVE"]:
        db.add(create_log("DENIED", f"Pass status is {pass_obj.status}"))
        await db.commit()
        return {"status": "Access Denied", "reason": f"Pass status is {pass_obj.status}"}

    # Time validation & Late Detection
    late_seconds = None
    access_granted_status = "GRANTED"
    
    if now < pass_obj.valid_from:
        db.add(create_log("DENIED", "Pass not yet valid"))
        await db.commit()
        return {"status": "Access Denied", "reason": "Pass not yet valid"}

    if now > pass_obj.valid_until:
        if direction in ["IN", "ENTRY"]:
            late_seconds = int((now - pass_obj.valid_until).total_seconds())
            access_granted_status = "LATE_ENTRY"
        else:
            db.add(create_log("DENIED", "Pass expired"))
            await db.commit()
            return {"status": "Access Denied", "reason": "Pass expired"}

    # TOTP Validation
    if not verify_qr_scan(pass_obj.id, token, pass_obj.qr_secret_seed):
        db.add(create_log("DENIED", "Invalid or expired QR code"))
        await db.commit()
        return {"status": "Access Denied", "reason": "Invalid or expired QR code"}

    # Log Success (or Late)
    db.add(create_log(access_granted_status, late_duration=late_seconds))
    
    if direction in ["OUT", "EXIT"] and pass_obj.status == "APPROVED":
        pass_obj.status = "ACTIVE"
        pass_obj.has_exited = True
    elif direction in ["IN", "ENTRY"] and pass_obj.status == "ACTIVE":
        pass_obj.status = "USED"
        pass_obj.has_entered = True

    await db.commit()
    
    requester = pass_obj.requester
    
    return {
        "status": "Access Granted",
        "access_type": access_granted_status,
        "late_duration_seconds": late_seconds,
        "student_info": {
            "full_name": requester.name if requester else "Unknown",
            "photo_url": "https://via.placeholder.com/150"
        }
    }
