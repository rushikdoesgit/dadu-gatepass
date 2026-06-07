import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from src.db.models.passes import Pass, PassVehicle, BlacklistedRFID
from src.db.models.identity import User, StudentProfile
from src.db.models.enums import ResidencyStatus, PassStatus
from src.db.models.logging import AccessLog
from src.services.qr_service import verify_qr_scan

async def verify_rfid_access(tag_id: str, session: AsyncSession, gate_id: uuid.UUID = None, direction: str = "UNKNOWN") -> dict:
    """
    Verifies an RFID tag scan for gate access.
    """
    from datetime import datetime, timezone
    
    if not gate_id:
        gate_id = uuid.UUID(int=0)
        
    # Check Blacklist
    blacklist_stmt = select(BlacklistedRFID).where(BlacklistedRFID.rfid_tag_id == tag_id)
    if (await session.execute(blacklist_stmt)).scalar_one_or_none():
        log = AccessLog(gate_id=gate_id, direction=direction, status="DENIED", method="RFID", denial_reason="BLACKLISTED")
        session.add(log)
        await session.commit()
        return {"success": False, "denial_reason": "BLACKLISTED"}

    # Join PassVehicle and Pass
    veh_stmt = select(PassVehicle, Pass).join(Pass).where(PassVehicle.rfid_tag_id == tag_id)
    result = await session.execute(veh_stmt)
    row = result.first()

    if not row:
        log = AccessLog(gate_id=gate_id, direction=direction, status="DENIED", method="RFID", denial_reason="NOT_FOUND")
        session.add(log)
        await session.commit()
        return {"success": False, "denial_reason": "NOT_FOUND"}

    vehicle, pass_obj = row
    now = datetime.now(timezone.utc)

    # Check status
    if pass_obj.status != "APPROVED":
        log = AccessLog(gate_id=gate_id, user_id=pass_obj.requester_id, pass_id=pass_obj.id, direction=direction, status="DENIED", method="RFID", denial_reason="NOT_APPROVED")
        session.add(log)
        await session.commit()
        return {"success": False, "denial_reason": "NOT_APPROVED"}

    # Check dates
    if not (pass_obj.valid_from <= now <= pass_obj.valid_until):
        log = AccessLog(gate_id=gate_id, user_id=pass_obj.requester_id, pass_id=pass_obj.id, direction=direction, status="DENIED", method="RFID", denial_reason="EXPIRED")
        session.add(log)
        await session.commit()
        return {"success": False, "denial_reason": "EXPIRED"}

    # Success
    log = AccessLog(gate_id=gate_id, user_id=pass_obj.requester_id, pass_id=pass_obj.id, direction=direction, status="SUCCESS", method="RFID")
    session.add(log)
    await session.commit()

    return {"success": True, "user_id": pass_obj.requester_id, "pass_id": pass_obj.id}

async def process_scan(
    db: AsyncSession,
    gate_id: uuid.UUID,
    direction: str,  # "ENTRY" or "EXIT"
    qr_payload: Optional[str] = None,
    rfid_tag_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processes a gate scan (either QR or RFID).
    Handles standard pass logic and resident bypass rules.
    """
    if not qr_payload and not rfid_tag_id:
        raise HTTPException(status_code=400, detail="Must provide either QR payload or RFID tag.")

    user_id = None
    pass_obj = None

    # --- RFID Processing (Including Blacklist & Resident Bypass) ---
    if rfid_tag_id:
        rfid_res = await verify_rfid_access(rfid_tag_id, db, gate_id, direction)
        if not rfid_res["success"]:
            raise HTTPException(status_code=403, detail=f"RFID Access Denied: {rfid_res['denial_reason']}")
        user_id = rfid_res["user_id"]
        
        pass_stmt = select(Pass).where(Pass.id == rfid_res["pass_id"])
        pass_obj = (await db.execute(pass_stmt)).scalar_one_or_none()

    # --- QR Processing ---
    elif qr_payload:
        try:
            # Parse the versioned payload: "v1:{pass_id}:{token}"
            parts = qr_payload.split(":")
            if len(parts) == 3 and parts[0] == "v1":
                pass_uuid = uuid.UUID(parts[1])
                scanned_token = parts[2]
            elif len(parts) == 2:
                # Legacy fallback: "{pass_id}:{token}"
                pass_uuid = uuid.UUID(parts[0])
                scanned_token = parts[1]
            else:
                raise ValueError("Unexpected payload structure")
        except ValueError:
            raise HTTPException(status_code=400, detail="Malformed QR payload.")

        pass_stmt = select(Pass).where(Pass.id == pass_uuid)
        pass_obj = (await db.execute(pass_stmt)).scalar_one_or_none()

        if not pass_obj or not pass_obj.qr_secret_seed:
            raise HTTPException(status_code=404, detail="Pass not found or invalid.")

        if not verify_qr_scan(pass_obj.id, scanned_token, pass_obj.qr_secret_seed):
            raise HTTPException(status_code=401, detail="QR Code expired or invalid. Please refresh.")
        
        user_id = pass_obj.requester_id

    # --- Resident Bypass Logic (For Commuters/Faculty) ---
    # In a full system, you'd lookup the User directly if RFID was bound to User instead of PassVehicle.
    # For now, if we have a user_id, we can check their residency status.
    is_bypass_allowed = False
    if user_id:
        profile_stmt = select(StudentProfile).where(StudentProfile.user_id == user_id)
        profile = (await db.execute(profile_stmt)).scalar_one_or_none()
        if profile and profile.residency_status == ResidencyStatus.OFF_CAMPUS_COMMUTER:
            is_bypass_allowed = True

    # --- Standard Pass Validation ---
    if not is_bypass_allowed:
        if not pass_obj:
            raise HTTPException(status_code=404, detail="No active pass found for this scan.")
            
        if pass_obj.status not in [PassStatus.APPROVED, PassStatus.ACTIVE]:
            raise HTTPException(status_code=403, detail=f"Pass is not valid for travel. Status: {pass_obj.status}")

        if direction == "EXIT":
            if pass_obj.has_exited:
                raise HTTPException(status_code=409, detail="Anti-Passback: User has already exited campus.")
            pass_obj.status = PassStatus.ACTIVE
            pass_obj.has_exited = True

        elif direction == "ENTRY":
            if not pass_obj.has_exited:
                raise HTTPException(status_code=409, detail="Anti-Passback: Cannot enter without exiting first.")
            if pass_obj.has_entered:
                raise HTTPException(status_code=409, detail="Anti-Passback: User has already entered campus.")
            pass_obj.status = PassStatus.USED
            pass_obj.has_entered = True

    # --- Log the Access ---
    access_log = AccessLog(
        gate_id=gate_id,
        user_id=user_id,
        pass_id=pass_obj.id if pass_obj else None,
        direction=direction,
        scan_type="RFID" if rfid_tag_id else "QR",
        status="SUCCESS"
    )
    db.add(access_log)
    await db.commit()

    return {
        "status": "success",
        "message": f"Successfully processed {direction} scan.",
        "bypass_used": is_bypass_allowed
    }
