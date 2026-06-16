from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.db.models.passes import Pass
from src.db.models.identity import User
from src.api.dependencies import RoleChecker

router = APIRouter()

@router.get("/pending")
async def get_pending_passes(
    current_user: User = Depends(RoleChecker(["WARDEN"])),
    db: AsyncSession = Depends(get_db)
):
    """
    List all pending passes for the warden to review.
    """
    stmt = select(Pass).options(selectinload(Pass.requester)).where(Pass.status == "PENDING")
    result = await db.execute(stmt)
    passes = result.scalars().all()
    
    return [
        {
            "id": str(p.id),
            "requester_name": p.requester.name if getattr(p, "requester", None) else "Unknown",
            "purpose": p.purpose,
            "valid_from": p.valid_from,
            "valid_until": p.valid_until,
            "status": p.status
        }
        for p in passes
    ]
