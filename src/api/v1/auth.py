from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.session import get_db
from src.db.models.identity import User
from src.security import pwd_context, create_access_token

router = APIRouter()


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password or not pwd_context.verify(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    # 3. Issue a local HS256 JWT with the user's email and role as claims
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
        }
    )

    return {"access_token": token, "token_type": "bearer"}

from pydantic import BaseModel
from src.services.auth_service import verify_swd_token
from src.db.models.enums import Role

class SWDLoginRequest(BaseModel):
    swd_token: str

@router.post("/swd-login")
async def swd_login(
    request: SWDLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Exchanges an SWD JWT for a local API JWT.
    Auto-provisions the user if they do not exist.
    """
    try:
        decoded = verify_swd_token(request.swd_token)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid SWD token")

    email = decoded.get("email")
    name = decoded.get("name")
    role_str = decoded.get("role", "STUDENT")

    if not email or not name:
        raise HTTPException(status_code=400, detail="SWD token missing email or name")

    stmt = select(User).where(User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    provisioned = False
    if not user:
        user = User(
            email=email,
            name=name,
            hashed_password=None,
            role=Role(role_str),
            is_active=True
        )
        db.add(user)
        provisioned = True
    else:
        if user.name != name:
            user.name = name

    await db.commit()
    await db.refresh(user)

    local_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
        }
    )

    return {
        "access_token": local_token, 
        "token_type": "bearer", 
        "provisioned": provisioned
    }
