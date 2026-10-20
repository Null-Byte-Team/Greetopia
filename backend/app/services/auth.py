"""Authentication & authorization helpers.

- Passwords: PBKDF2-HMAC-SHA256 (600k iterations); legacy 100k hashes still verify and are upgraded on login.
- Sessions: HS256 JWT signed with JWT_SECRET (required in production; random per process in development).
- Roles (stored in the DB, so demotion takes effect immediately): viewer < operator < admin.
- Device endpoints use a shared X-Device-Token (constant-time compare).
- Photo URLs are short-lived HMAC-signed links because <img> tags cannot send Authorization headers.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request

from app.core.config import settings
from app.db.database import db_session

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
PBKDF2_ITERATIONS = 600_000
ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2}

_ephemeral_secret = secrets.token_urlsafe(48)


def jwt_secret() -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.is_production:
        raise RuntimeError("JWT_SECRET is required in production")
    return _ephemeral_secret  # development only: sessions reset on restart


# ---------------------------------------------------------------- passwords
def hash_password(plain: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), iterations)
    return f"pbkdf2:sha256:{iterations}${salt}${key.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or not hashed.startswith("pbkdf2:"):
        return False
    try:
        algo_part, salt, key_hex = hashed.split("$")
        iterations = int(algo_part.split(":")[2])
        key = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), iterations)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return int(hashed.split("$")[0].split(":")[2]) < PBKDF2_ITERATIONS
    except Exception:
        return True


# ---------------------------------------------------------------- tokens
def create_access_token(user_id: int, email: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id), "email": email, "name": name,
        "iat": now, "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_token(id_token: str) -> Optional[dict]:
    """Validate a Google ID token via Google's tokeninfo endpoint (audience, issuer, verified e-mail)."""
    try:
        import httpx

        resp = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("aud") != settings.google_client_id:
            logger.warning("Google token audience mismatch")
            return None
        if data.get("iss") not in GOOGLE_ISSUERS:
            logger.warning("Google token issuer mismatch")
            return None
        if str(data.get("email_verified")).lower() != "true":
            logger.warning("Google e-mail not verified")
            return None
        return data
    except Exception:
        logger.exception("Google token verification failed")
        return None


# ---------------------------------------------------------------- users / roles
def ensure_users_table(db) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL DEFAULT '',
            avatar_url TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'email',
            password_hash TEXT DEFAULT NULL,
            google_sub TEXT DEFAULT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            last_login TEXT NOT NULL
        );
        """
    )
    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'")


def effective_role(email: str, stored_role: str) -> str:
    email = (email or "").lower()
    role = stored_role if stored_role in ROLE_ORDER else "viewer"
    if email in settings.csv(settings.admin_emails):
        return "admin"
    if email in settings.csv(settings.operator_emails) and ROLE_ORDER[role] < ROLE_ORDER["operator"]:
        return "operator"
    return role


def initial_role(db, email: str) -> str:
    """First registered account bootstraps as admin; listed e-mails get their role; others are viewers."""
    n = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if n == 0:
        return "admin"
    return effective_role(email, "viewer")


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required.")
    return authorization.removeprefix("Bearer ").strip()


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    payload = decode_access_token(_bearer(authorization))
    if not payload:
        raise HTTPException(401, "Session expired or invalid. Please sign in again.")
    with db_session() as db:
        ensure_users_table(db)
        row = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if not row:
        raise HTTPException(401, "User not found.")
    user = dict(row)
    user["role"] = effective_role(user["email"], user.get("role", "viewer"))
    return user


def require_operator(user: dict = Depends(current_user)) -> dict:
    if ROLE_ORDER[user["role"]] < ROLE_ORDER["operator"]:
        raise HTTPException(403, "Your account is read-only. Ask an administrator for operator access.")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


# ---------------------------------------------------------------- device auth
def require_device(x_device_token: Optional[str] = Header(default=None, alias="X-Device-Token")) -> None:
    expected = settings.device_upload_token
    if not expected:
        if settings.allow_insecure_devices:
            return
        raise HTTPException(503, "Device authentication is not configured on the server.")
    if not x_device_token or not hmac.compare_digest(x_device_token.encode(), expected.encode()):
        raise HTTPException(401, "Invalid device token.")


# ---------------------------------------------------------------- rate limiting (in-memory, single process)
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def rate_limit(key: str, limit: int, window_s: int = 60) -> None:
    now = time.monotonic()
    with _hits_lock:
        recent = [t for t in _hits.get(key, []) if now - t < window_s]
        if len(recent) >= limit:
            _hits[key] = recent
            raise HTTPException(429, "Too many requests. Please wait and try again.")
        recent.append(now)
        _hits[key] = recent


def reset_rate_limits() -> None:
    with _hits_lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- signed photo URLs
def _sig(key: str, exp: int) -> str:
    return hmac.new(jwt_secret().encode(), f"{key}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def sign_photo(key: str) -> str:
    exp = int(time.time()) + settings.photo_url_ttl_s
    return f"exp={exp}&sig={_sig(key, exp)}"


def verify_photo_sig(key: str, exp: int, sig: str) -> bool:
    return exp >= int(time.time()) and hmac.compare_digest(_sig(key, exp), sig or "")
