"""
POST /api/v1/auth/signup  - e-mail + password sign-up (first account becomes admin, later ones are read-only viewers)
POST /api/v1/auth/signin  - e-mail + password sign-in (rate limited)
POST /api/v1/auth/google  - Google ID-token exchange (audience, issuer and verified e-mail are checked)
GET  /api/v1/auth/me      - current user + role
GET/PATCH /api/v1/auth/users - admin: list users / change roles
"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.database import db_session
from app.services.auth import (create_access_token, current_user, effective_role, ensure_users_table, hash_password,
                               initial_role, needs_rehash, rate_limit, client_ip, require_admin, verify_google_token,
                               verify_password)
from app.core.config import settings

auth_router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SignUpRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class SignInRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=128)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=10, max_length=4096)


class RoleUpdate(BaseModel):
    role: Literal["viewer", "operator", "admin"]


class AuthResponse(BaseModel):
    token: str
    user: dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_user(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "avatar_url": row["avatar_url"],
            "provider": row["provider"], "role": effective_role(row["email"], row.get("role", "viewer"))}


def _create_user(db, *, email, name, avatar_url="", provider="email", password_hash=None, google_sub=None) -> dict:
    role = initial_role(db, email)
    now = _now()
    cur = db.execute("INSERT INTO users (email,name,avatar_url,provider,password_hash,google_sub,role,created_at,last_login) VALUES (?,?,?,?,?,?,?,?,?)",
                     (email.lower(), name, avatar_url, provider, password_hash, google_sub, role, now, now))
    return dict(db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


@auth_router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: SignUpRequest, request: Request):
    rate_limit(f"signup:{client_ip(request)}", 10, 3600)
    with db_session() as db:
        ensure_users_table(db)
        if db.execute("SELECT 1 FROM users WHERE email = ?", (body.email.lower(),)).fetchone():
            raise HTTPException(400, "An account with this email already exists.")
        user = _create_user(db, email=body.email, name=body.name.strip(), password_hash=hash_password(body.password))
    return AuthResponse(token=create_access_token(user["id"], user["email"], user["name"]), user=_public_user(user))


@auth_router.post("/signin", response_model=AuthResponse)
def signin(body: SignInRequest, request: Request):
    rate_limit(f"signin-ip:{client_ip(request)}", 20, 300)
    rate_limit(f"signin-user:{body.email.lower()}", 8, 300)
    with db_session() as db:
        ensure_users_table(db)
        row = db.execute("SELECT * FROM users WHERE email = ?", (body.email.lower(),)).fetchone()
        if not row or not row["password_hash"] or not verify_password(body.password, row["password_hash"]):
            if row and not row["password_hash"]:
                raise HTTPException(400, "This account uses Google Sign-In. Please sign in with Google.")
            raise HTTPException(401, "Invalid email or password.")
        row = dict(row)
        if needs_rehash(row["password_hash"]):
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.password), row["id"]))
        db.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), row["id"]))
    return AuthResponse(token=create_access_token(row["id"], row["email"], row["name"]), user=_public_user(row))


@auth_router.post("/google", response_model=AuthResponse)
def google_auth(body: GoogleAuthRequest, request: Request):
    rate_limit(f"google:{client_ip(request)}", 20, 300)
    payload = verify_google_token(body.id_token)
    if not payload:
        raise HTTPException(401, "Google token verification failed. Please try again.")
    email = payload.get("email", "")
    if not email:
        raise HTTPException(400, "Could not read email from Google account.")
    name = payload.get("name") or payload.get("given_name") or email.split("@")[0]
    with db_session() as db:
        ensure_users_table(db)
        row = db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row:
            row = dict(row)
            db.execute("UPDATE users SET avatar_url=?, google_sub=COALESCE(google_sub,?), last_login=? WHERE id=?",
                       (payload.get("picture", ""), payload.get("sub", ""), _now(), row["id"]))
        else:
            row = _create_user(db, email=email, name=name, avatar_url=payload.get("picture", ""), provider="google", google_sub=payload.get("sub", ""))
    return AuthResponse(token=create_access_token(row["id"], row["email"], row["name"]), user=_public_user(row))


@auth_router.get("/me")
def me(user: dict = Depends(current_user)):
    return _public_user(user)


@auth_router.get("/users")
def list_users(_: dict = Depends(require_admin)):
    with db_session() as db:
        ensure_users_table(db)
        rows = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_public_user(dict(r)) for r in rows]


@auth_router.patch("/users/{user_id}/role")
def set_role(user_id: int, body: RoleUpdate, admin: dict = Depends(require_admin)):
    if user_id == admin["id"] and body.role != "admin":
        raise HTTPException(400, "You cannot remove your own administrator role.")
    with db_session() as db:
        ensure_users_table(db)
        if not db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "User not found.")
        db.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
        row = dict(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    return _public_user(row)
