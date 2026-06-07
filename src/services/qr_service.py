"""
Dynamic QR TOTP Service

Generates and verifies time-based one-time passwords for gate passes
using pyotp. Tokens rotate every 45 seconds to prevent screenshot fraud.
"""

import time
from uuid import UUID

import pyotp

from src.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INTERVAL = settings.QR_STEP_INTERVAL_SECONDS  # 45 seconds
_PAYLOAD_VERSION = "v1"


def generate_qr_payload(pass_id: UUID, qr_secret_seed: str) -> str:
    """
    Generate a versioned, time-based QR payload for a given pass.

    Returns a string formatted as ``v1:{pass_id}:{totp_token}``.
    The token is derived from ``pyotp.TOTP`` with a 45-second interval,
    making screenshots useless after the window expires.
    """
    totp = pyotp.TOTP(qr_secret_seed, interval=_INTERVAL)
    token = totp.now()
    return f"{_PAYLOAD_VERSION}:{pass_id}:{token}"


def verify_qr_scan(pass_id: UUID, scanned_token: str, qr_secret_seed: str) -> bool:
    """
    Verify a scanned TOTP token against the stored seed.

    Accepts the current 45-second window **and** the immediately preceding
    window (``valid_window=1``) to tolerate minor network / scanning lag.

    Parameters
    ----------
    pass_id : UUID
        The UUID of the pass (reserved for future audit logging).
    scanned_token : str
        The 6-digit TOTP token extracted from the scanned QR payload.
    qr_secret_seed : str
        The base-32 secret stored on the ``Pass`` row.

    Returns
    -------
    bool
        ``True`` if the token is valid for the current or previous window.
    """
    totp = pyotp.TOTP(qr_secret_seed, interval=_INTERVAL)
    return totp.verify(scanned_token, valid_window=1)


def seconds_remaining() -> int:
    """Return the number of seconds left in the current TOTP window."""
    return _INTERVAL - (int(time.time()) % _INTERVAL)
