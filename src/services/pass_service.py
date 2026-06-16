from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models.passes import Pass

async def has_active_trip(db: AsyncSession, user_id: UUID) -> bool:
    """
    Checks if a user has an active trip (exited but not entered).
    Delegates to the model's class method.
    """
    return await Pass.check_active_trip_exists(db, user_id)

async def create_pass(
    db: AsyncSession, 
    user_id: UUID, 
    pass_type_name: str, 
    purpose: str, 
    valid_from, 
    valid_until
) -> Pass:
    from sqlalchemy import select
    from src.db.models.passes import PassType
    from src.db.models.enums import PassStatus
    from fastapi import HTTPException, status
    
    # 1. Fetch PassType
    stmt = select(PassType).where(PassType.name == pass_type_name)
    result = await db.execute(stmt)
    pass_type = result.scalar_one_or_none()
    
    if not pass_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid pass type: {pass_type_name}"
        )
        
    # 2. Determine Initial Status
    initial_status = PassStatus.PENDING if pass_type.requires_approval else PassStatus.APPROVED
    
    import pyotp

    # 3. Create Pass
    new_pass = Pass(
        pass_type_id=pass_type.id,
        requester_id=user_id,
        status=initial_status,
        valid_from=valid_from,
        valid_until=valid_until,
        purpose=purpose,
        qr_secret_seed=pyotp.random_base32()
    )
    
    
    db.add(new_pass)
    await db.commit()
    await db.refresh(new_pass)
    
    return new_pass

async def create_vehicle_pass(
    db: AsyncSession,
    user_id: UUID,
    vehicle_number: str,
    vehicle_model: str,
    rfid_tag_id: str,
    purpose: str,
    valid_until
) -> dict:
    """
    Business logic for requesting an RFID vehicle pass for Faculty.
    """
    from sqlalchemy import select
    from src.db.models.passes import Pass, PassVehicle, BlacklistedRFID, PassType
    from fastapi import HTTPException
    from datetime import datetime, timezone

    # 1. Check Blacklist
    blacklist_stmt = select(BlacklistedRFID).where(BlacklistedRFID.rfid_tag_id == rfid_tag_id)
    if (await db.execute(blacklist_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=403, detail="RFID tag is blacklisted.")

    # 2. Check for existing active pass with this RFID
    veh_stmt = select(PassVehicle).join(Pass).where(
        PassVehicle.rfid_tag_id == rfid_tag_id,
        Pass.status.in_(["PENDING", "APPROVED", "ACTIVE"])
    )
    if (await db.execute(veh_stmt)).first():
        raise HTTPException(status_code=409, detail="RFID tag is already linked to an active pass.")

    # 3. Fetch VEHICLE pass type
    type_stmt = select(PassType).where(PassType.name == "VEHICLE")
    pass_type = (await db.execute(type_stmt)).scalar_one_or_none()
    if not pass_type:
        raise HTTPException(status_code=500, detail="VEHICLE pass type not seeded")

    # 4. Create Pass
    new_pass = Pass(
        pass_type_id=pass_type.id,
        requester_id=user_id,
        status="PENDING",
        valid_from=datetime.now(timezone.utc),
        valid_until=valid_until,
        purpose=purpose
    )
    db.add(new_pass)
    await db.flush() # flush to get pass ID

    # 5. Create PassVehicle
    new_vehicle = PassVehicle(
        pass_id=new_pass.id,
        vehicle_number=vehicle_number,
        vehicle_model=vehicle_model,
        rfid_tag_id=rfid_tag_id,
        is_active=True
    )
    db.add(new_vehicle)
    await db.commit()

    return {"pass_id": str(new_pass.id), "status": new_pass.status}
