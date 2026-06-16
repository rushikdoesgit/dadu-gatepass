from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.session import get_db
from src.db.models.identity import User, StudentProfile
from src.db.models.enums import Role, ResidencyStatus, StudentTier
from src.services.auth_service import verify_swd_token
from src.security import decode_local_token
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Decodes the JWT token and fetches the User from the DB.

    Tries a locally-issued HS256 token first (Swagger / seeded test users),
    then falls back to the external SWD RS256 token path.
    If the user does not exist on the SWD path, performs Auto-Provisioning.
    """
    # --- Path 1: Local HS256 token (issued by /api/v1/auth/login) ---
    local_claims = decode_local_token(token)
    if local_claims:
        user_id_str = local_claims.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim."
            )
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 'sub' claim format (expected UUID)."
            )
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found."
            )
        return user

    # --- Path 2: External SWD RS256 token ---
    claims = verify_swd_token(token)

    # We assume SWD token claims include:
    # 'sub' (User UUID), 'email', 'name', 'role', 'student_id', 'tier', 'residency_status'
    user_id_str = claims.get("sub")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim."
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 'sub' claim format (expected UUID)."
        )

    # Fetch User
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        return user
        
    # Auto-Provisioning logic for Students
    role_str = claims.get("role", "STUDENT")
    if role_str == "STUDENT":
        try:
            new_user = User(
                id=user_id,
                email=claims.get("email"),
                name=claims.get("name"),
                role=Role.STUDENT,
                is_active=True
            )
            db.add(new_user)
            
            # Map claims to enums safely
            tier_claim = claims.get("tier", "UNDERGRAD")
            residency_claim = claims.get("residency_status", "ON_CAMPUS")
            
            student_profile = StudentProfile(
                user_id=user_id,
                student_id=claims.get("student_id", "UNKNOWN"),
                tier=StudentTier[tier_claim] if tier_claim in StudentTier.__members__ else StudentTier.UNDERGRAD,
                residency_status=ResidencyStatus[residency_claim] if residency_claim in ResidencyStatus.__members__ else ResidencyStatus.ON_CAMPUS
            )
            db.add(student_profile)
            
            await db.commit()
            await db.refresh(new_user)
            return new_user
            
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Auto-provisioning failed: {str(e)}"
            )
    else:
        # Non-student auto-provisioning (e.g., Faculty/Guard) can be added here
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Auto-provisioning is currently only supported for students."
        )

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if not hasattr(current_user, "role") or current_user.role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User role not found or not loaded."
            )
            
        if current_user.role.name not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Allowed roles: {', '.join(self.allowed_roles)}"
            )
            
        return current_user
