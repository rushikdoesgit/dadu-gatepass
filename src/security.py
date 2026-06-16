"""
Shared security utilities.

- pwd_context  : bcrypt password hashing/verification (imported by auth.py and seed_db.py)
- create_access_token : issues a local HS256 JWT (for Swagger / test users)
- decode_local_token  : verifies a local HS256 JWT; returns claims or None
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from src.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Local JWT (HS256) — used for seeded test users / Swagger login
# ---------------------------------------------------------------------------
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed HS256 JWT containing ``data`` as payload claims.

    A ``exp`` claim is always added. Pass ``expires_delta`` to override
    the default expiry of 60 minutes.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.AES_ENCRYPTION_KEY, algorithm=_ALGORITHM)


def decode_local_token(token: str) -> Optional[dict]:
    """
    Attempt to decode a locally-issued HS256 JWT.

    Returns the claims dict on success, or ``None`` if the token is
    invalid / expired / not a local token (so the caller can fall back
    to the SWD RS256 path).
    """
    try:
        return jwt.decode(token, settings.AES_ENCRYPTION_KEY, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
