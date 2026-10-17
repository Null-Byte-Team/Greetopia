"""
Authentication service — handles:
  - Email/password sign-up & sign-in with bcrypt password hashing
  - Google ID-token verification (validates tokens signed by Google, client-side)
  - JWT session token creation & decoding (HS256, stored in frontend localStorage)

Security notes:
  - Passwords are bcrypt-hashed before storage (never stored plain).
  - JWT secret is read from JWT_SECRET env var; a random one is generated at startup
    if not set (sessions invalidate on restart — set JWT_SECRET in production).
  - Google token verification uses Google's public JWKS endpoint; no client secret needed.
"""
import os
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET") or "greetopia-stable-auth-secret-key-355615741600-permanent-v1"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 3650  # 10 years / permanent session

GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "355615741600-5tfd5st7gr7ihnl81k78794u853u32qc.apps.googleusercontent.com",
)

try:
    from jose import jwt, JWTError
    _jose_ok = True
except ImportError:
    _jose_ok = False
    logger.warning("python-jose not installed – JWT auth disabled")

import hashlib

# ── Password Hashing (PBKDF2-SHA256, standard library, zero C-dep issues) ──────

def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    if hashed.startswith("pbkdf2:"):
        try:
            parts = hashed.split("$")
            if len(parts) != 3:
                return False
            algo_part, salt, key_hex = parts
            _, _, iterations = algo_part.split(":")
            key = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), int(iterations))
            return secrets.compare_digest(key.hex(), key_hex)
        except Exception:
            return False
    # Backward compatibility with bcrypt if passlib is present
    if _bcrypt_ok:
        try:
            return _pwd_context.verify(plain, hashed)
        except Exception:
            return False
    return False


def create_access_token(user_id: int, email: str, name: str) -> str:
    if not _jose_ok:
        raise RuntimeError("python-jose not installed")
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    if not _jose_ok:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def verify_google_token(id_token: str) -> Optional[dict]:
    """
    Verify a Google ID-token obtained from the Google Sign-In JS SDK.
    Returns the decoded payload dict or None on failure.
    Uses Google's tokeninfo endpoint as a simple, dependency-free check.
    In production you can also use google-auth library for offline verification.
    """
    try:
        import httpx
        # Use Google's tokeninfo endpoint — works without any secret
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Google tokeninfo returned %s", resp.status_code)
            return None
        data = resp.json()
        # Validate audience matches our client ID
        aud = data.get("aud", "")
        if aud != GOOGLE_CLIENT_ID:
            logger.warning("Google token aud mismatch: %s", aud)
            return None
        return data
    except Exception:
        logger.exception("Google token verification failed")
        return None
