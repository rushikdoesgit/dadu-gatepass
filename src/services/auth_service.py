import jwt
from fastapi import HTTPException, status
from src.config import settings

def verify_swd_token(token: str) -> dict:
    """
    Verifies the JWT token from SWD against the in-memory public key.
    Bypasses HTTP fetch to avoid self-referential deadlock.
    """
    try:
        # Import here to avoid circular imports at module load time
        from src.api.v1.swd import _public_key
        
        # Serialize public key to PEM for PyJWT
        from cryptography.hazmat.primitives import serialization
        public_pem = _public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        data = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            audience=settings.SWD_CLIENT_ID,
            issuer=settings.SWD_ISSUER
        )
        return data

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )