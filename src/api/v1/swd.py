import base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from fastapi import APIRouter
import jwt
from src.config import settings

router = APIRouter()

# 1. RSA key pair generation on startup
_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
_public_key = _private_key.public_key()

def _int_to_base64url(val: int) -> str:
    """Converts an integer to a base64url encoded string without padding."""
    val_bytes = val.to_bytes((val.bit_length() + 7) // 8, byteorder='big')
    return base64.urlsafe_b64encode(val_bytes).decode('ascii').rstrip('=')

# Extract numbers for JWKS
public_numbers = _public_key.public_numbers()
_n_b64 = _int_to_base64url(public_numbers.n)
_e_b64 = _int_to_base64url(public_numbers.e)

@router.get("/.well-known/jwks.json")
async def get_jwks():
    """
    Returns the public key formatted as a valid JWKS JSON response.
    """
    return {
        "keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": "mock-swd-key-1",
            "n": _n_b64,
            "e": _e_b64
        }]
    }

@router.get("/token")
async def get_mock_token(student_id: str, name: str, email: str, role: str = "STUDENT"):
    """
    Generates and returns a signed RS256 JWT for the mock SWD.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "email": email,
        "name": name,
        "role": role,
        "student_id": student_id,
        "tier": "UNDERGRAD",
        "residency_status": "ON_CAMPUS",
        "iss": settings.SWD_ISSUER,
        "aud": settings.SWD_CLIENT_ID,
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "iat": int(now.timestamp())
    }
    
    # Serialize private key to PEM for PyJWT
    private_pem = _private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    token = jwt.encode(
        payload,
        private_pem,
        algorithm="RS256",
        headers={"kid": "mock-swd-key-1"}
    )
    
    return {"access_token": token, "token_type": "bearer"}
