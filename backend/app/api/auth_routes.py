"""
Auth API routes
POST /api/v1/auth/signup         – Email + password sign-up
POST /api/v1/auth/signin         – Email + password sign-in
POST /api/v1/auth/google         – Google ID-token exchange → JWT
GET  /api/v1/auth/me             – Validate current JWT, return profile
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from app.db.database import db_session
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    verify_google_token,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

class SignUpRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class SignInRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=128)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=10)


class AuthResponse(BaseModel):
    token: str
    user: dict


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _ensure_users_table(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            name        TEXT    NOT NULL DEFAULT '',
            avatar_url  TEXT    NOT NULL DEFAULT '',
            provider    TEXT    NOT NULL DEFAULT 'email',
            password_hash TEXT  DEFAULT NULL,
            google_sub  TEXT    DEFAULT NULL,
            created_at  TEXT    NOT NULL,
            last_login  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)


def _get_user_by_email(db, email: str):
    return db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()


def _create_user(db, *, email: str, name: str, avatar_url: str = "",
                 provider: str = "email", password_hash: str = None,
                 google_sub: str = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO users (email, name, avatar_url, provider, password_hash, google_sub, created_at, last_login)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (email.lower(), name, avatar_url, provider, password_hash, google_sub, now, now),
    )
    row = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def _update_last_login(db, user_id: int):
    db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "avatar_url": row["avatar_url"],
        "provider": row["provider"],
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@auth_router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: SignUpRequest):
    with db_session() as db:
        _ensure_users_table(db)
        existing = _get_user_by_email(db, body.email)
        if existing:
            raise HTTPException(400, "An account with this email already exists.")
        try:
            pw_hash = hash_password(body.password)
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        user = _create_user(
            db,
            email=body.email,
            name=body.name,
            provider="email",
            password_hash=pw_hash,
        )

    try:
        token = create_access_token(user["id"], user["email"], user["name"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    return AuthResponse(token=token, user=_public_user(user))


@auth_router.post("/signin", response_model=AuthResponse)
def signin(body: SignInRequest):
    with db_session() as db:
        _ensure_users_table(db)
        row = _get_user_by_email(db, body.email)
        if not row:
            raise HTTPException(401, "Invalid email or password.")
        row = dict(row)
        if not row.get("password_hash"):
            raise HTTPException(400, "This account uses Google Sign-In. Please sign in with Google.")
        if not verify_password(body.password, row["password_hash"]):
            raise HTTPException(401, "Invalid email or password.")
        _update_last_login(db, row["id"])

    try:
        token = create_access_token(row["id"], row["email"], row["name"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    return AuthResponse(token=token, user=_public_user(row))


@auth_router.post("/google", response_model=AuthResponse)
def google_auth(body: GoogleAuthRequest):
    payload = verify_google_token(body.id_token)
    if not payload:
        raise HTTPException(401, "Google token verification failed. Please try again.")

    google_sub = payload.get("sub", "")
    email = payload.get("email", "")
    name = payload.get("name") or payload.get("given_name") or email.split("@")[0]
    avatar_url = payload.get("picture", "")

    if not email:
        raise HTTPException(400, "Could not read email from Google account.")

    with db_session() as db:
        _ensure_users_table(db)
        row = _get_user_by_email(db, email)
        if row:
            row = dict(row)
            # Update avatar and google_sub if missing
            db.execute(
                "UPDATE users SET avatar_url=?, google_sub=?, last_login=? WHERE id=?",
                (avatar_url, google_sub, datetime.now(timezone.utc).isoformat(), row["id"]),
            )
        else:
            row = _create_user(
                db,
                email=email,
                name=name,
                avatar_url=avatar_url,
                provider="google",
                google_sub=google_sub,
            )

    try:
        token = create_access_token(row["id"], row["email"], row["name"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    return AuthResponse(token=token, user=_public_user(row))


@auth_router.get("/me")
def me(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated.")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(401, "Session expired or invalid. Please sign in again.")

    with db_session() as db:
        _ensure_users_table(db)
        row = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
        if not row:
            email = payload.get("email")
            if email:
                row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
                if not row:
                    # Automatically heal user from cryptographically signed JWT if DB was recycled
                    now = datetime.now(timezone.utc).isoformat()
                    db.execute(
                        """INSERT INTO users (id, email, name, avatar_url, provider, created_at, last_login)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (int(payload["sub"]), email.lower(), payload.get("name", "User"), "", "session", now, now),
                    )
                    row = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if not row:
        raise HTTPException(401, "User not found.")
    return _public_user(dict(row))
