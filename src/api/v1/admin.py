from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from src.db.session import get_db
from src.db.models.identity import User
from src.db.models.passes import BlacklistedRFID, PassVehicle, Pass
from src.api.dependencies import RoleChecker

router = APIRouter()

class BlacklistRFIDSchema(BaseModel):
    rfid_tag_id: str
    reason: str

@router.post("/blacklist-rfid")
async def blacklist_rfid(
    request: BlacklistRFIDSchema,
    current_user: User = Depends(RoleChecker(["WARDEN"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Blacklist an RFID tag. WARDEN only.
    """
    # 1. Create BlacklistedRFID row
    blacklist_entry = BlacklistedRFID(
        rfid_tag_id=request.rfid_tag_id,
        reason=request.reason,
        blacklisted_by=current_user.id,
        created_at=datetime.now(timezone.utc)
    )
    db.add(blacklist_entry)
    
    # 2. Find all PassVehicle rows where rfid_tag_id matches
    veh_stmt = select(PassVehicle).where(PassVehicle.rfid_tag_id == request.rfid_tag_id)
    vehicles = (await db.execute(veh_stmt)).scalars().all()
    
    count = 0
    now = datetime.now(timezone.utc)
    for vehicle in vehicles:
        vehicle.is_active = False
        
        pass_stmt = select(Pass).where(Pass.id == vehicle.pass_id)
        pass_obj = (await db.execute(pass_stmt)).scalar_one_or_none()
        if pass_obj:
            pass_obj.status = "EXPIRED"
            pass_obj.revoked_at = now
            pass_obj.revoked_by = current_user.id
            count += 1
            
    await db.commit()
    
    return {"status": "success", "revoked_passes_count": count}
