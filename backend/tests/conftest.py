import io
import os
import tempfile
from pathlib import Path

_boot = Path(tempfile.mkdtemp())
os.environ.update({
    "DATABASE_PATH": str(_boot / "boot.db"), "PHOTO_DIR": str(_boot / "photos"), "MQTT_ENABLED": "false",
    "JWT_SECRET": "unit-test-secret-unit-test-secret-1234567890", "DEVICE_UPLOAD_TOKEN": "device-secret-token",
    "APP_ENV": "development", "GEMINI_API_KEY": "", "OPENWEATHER_API_KEY": "",
})

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.db.database import init_db


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "t.db"))
    monkeypatch.setattr(settings, "photo_dir", str(tmp_path / "photos"))
    from app.services import auth
    auth.reset_rate_limits()
    init_db()
    yield tmp_path


@pytest.fixture()
def client(env):
    from app.main import app
    return TestClient(app)


def _signup(client, email, name="User"):
    r = client.post("/api/v1/auth/signup", json={"name": name, "email": email, "password": "correct-horse-1"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def admin(client):
    return _signup(client, "admin@example.com", "Admin")  # first account => admin


@pytest.fixture()
def viewer(client, admin):
    return _signup(client, "viewer@example.com", "Viewer")


@pytest.fixture()
def device():
    return {"X-Device-Token": "device-secret-token"}


def make_jpeg(size=(64, 48), color=(10, 120, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()
