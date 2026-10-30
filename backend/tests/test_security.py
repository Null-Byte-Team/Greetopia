import jwt
import pytest

from tests.conftest import _signup

PROTECTED = [("get", "/api/v1/plants"), ("get", "/api/v1/plants/plant01/overview"), ("get", "/api/v1/plants/plant01/events"),
             ("post", "/api/v1/plants/plant01/water"), ("patch", "/api/v1/plants/plant01/mode"), ("post", "/api/v1/plants"),
             ("post", "/api/v1/plants/plant01/chat"), ("post", "/api/v1/plants/plant01/photos/analyze"),
             ("post", "/api/v1/plants/plant01/decision"), ("get", "/api/v1/health/details")]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_endpoints_require_authentication(client, method, path):
    assert getattr(client, method)(path, **({"json": {}} if method != "get" else {})).status_code == 401


def test_debug_endpoints_removed(client):
    assert client.get("/_debug").status_code == 404
    assert client.get("/api/v1/debug").status_code == 404


def test_public_health_leaks_nothing_sensitive(client):
    body = client.get("/api/v1/health").json()
    assert "last_error" not in str(body) and "database_path" not in str(body)


def test_first_user_is_admin_next_is_viewer(client, admin, viewer):
    assert client.get("/api/v1/auth/me", headers=admin).json()["role"] == "admin"
    assert client.get("/api/v1/auth/me", headers=viewer).json()["role"] == "viewer"


def test_viewer_cannot_control_pump_or_plants(client, viewer):
    assert client.post("/api/v1/plants/plant01/water", json={"duration_seconds": 5}, headers=viewer).status_code == 403
    assert client.patch("/api/v1/plants/plant01/mode", json={"mode": "manual"}, headers=viewer).status_code == 403
    assert client.post("/api/v1/plants", json={"plant_id": "x1", "name": "x"}, headers=viewer).status_code == 403
    assert client.get("/api/v1/plants", headers=viewer).status_code == 200


def test_admin_can_promote_viewer(client, admin, viewer):
    uid = client.get("/api/v1/auth/me", headers=viewer).json()["id"]
    assert client.patch(f"/api/v1/auth/users/{uid}/role", json={"role": "operator"}, headers=admin).json()["role"] == "operator"
    assert client.post("/api/v1/plants/plant01/water", json={"duration_seconds": 3}, headers=viewer).status_code != 403


def test_forged_tokens_rejected(client):
    old_default = "greetopia-stable-auth-secret-key-355615741600-permanent-v1"
    forged = jwt.encode({"sub": "1", "email": "a@b.c", "exp": 9999999999}, old_default, algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_alg = jwt.encode({"sub": "1", "exp": 9999999999}, "", algorithm="none")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_token_for_deleted_user_does_not_self_heal(client, admin):
    from app.db.database import db_session
    with db_session() as db:
        db.execute("DELETE FROM users")
    assert client.get("/api/v1/auth/me", headers=admin).status_code == 401


def test_signin_is_rate_limited(client, admin):
    codes = [client.post("/api/v1/auth/signin", json={"email": "admin@example.com", "password": "wrong-password"}).status_code for _ in range(10)]
    assert 429 in codes and codes[0] == 401


def test_password_hash_strength_and_legacy_upgrade():
    from app.services.auth import hash_password, needs_rehash, verify_password
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h) and not verify_password("nope", h) and not needs_rehash(h)
    legacy = hash_password("s3cret-pass", iterations=100_000)
    assert verify_password("s3cret-pass", legacy) and needs_rehash(legacy)
    assert not verify_password("x", "bcrypt$garbage")  # no NameError for unknown formats


def test_production_refuses_unsafe_config(monkeypatch):
    from app.core.config import settings, validate_settings
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret", "short")
    with pytest.raises(RuntimeError):
        validate_settings()
    monkeypatch.setattr(settings, "jwt_secret", "x" * 40)
    monkeypatch.setattr(settings, "device_upload_token", "")
    with pytest.raises(RuntimeError):
        validate_settings()


def test_device_endpoints_need_token(client, device):
    body = {"soil_root": 40}
    assert client.post("/api/v1/plants/plant01/telemetry", json=body).status_code == 401
    assert client.post("/api/v1/plants/plant01/telemetry", json=body, headers={"X-Device-Token": "bad"}).status_code == 401
    assert client.post("/api/v1/plants/plant01/telemetry", json=body, headers=device).status_code == 201
