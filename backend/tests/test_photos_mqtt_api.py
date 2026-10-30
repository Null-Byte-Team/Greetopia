import pytest

from tests.conftest import make_jpeg


def upload(client, body, device, plant="plant01", ctype="image/jpeg"):
    return client.post("/upload", content=body, headers={"X-Plant-Id": plant, "Content-Type": ctype, **device})


def test_upload_requires_device_token(client):
    assert upload(client, make_jpeg(), {}).status_code == 401
    assert upload(client, make_jpeg(), {"X-Device-Token": "wrong"}).status_code == 401


def test_upload_accepts_real_jpeg_and_reports_server_time(client, device):
    r = upload(client, make_jpeg(), device)
    assert r.status_code == 201 and r.json()["capture_time_source"] == "server_receive"


@pytest.mark.parametrize("body", [b"\xff\xd8\xff" + b"A" * 50, b"GIF89a....", b"", b"\x89PNG" + b"0" * 30])
def test_upload_rejects_fake_images(client, device, body):
    assert upload(client, body, device).status_code == 400


def test_upload_rejects_unknown_plant_bad_id_and_oversize(client, device, monkeypatch):
    from app.core.config import settings
    assert upload(client, make_jpeg(), device, plant="ghost").status_code == 404
    assert upload(client, make_jpeg(), device, plant="../../etc").status_code in (400, 404)
    monkeypatch.setattr(settings, "max_photo_bytes", 100)
    assert upload(client, make_jpeg(size=(400, 400)), device).status_code == 413


def test_retry_of_same_capture_is_deduplicated(client, device):
    body = make_jpeg()
    first, second = upload(client, body, device).json(), upload(client, body, device).json()
    assert first["status"] == "stored" and second["status"] == "duplicate" and second["capture_id"] == first["capture_id"]


def test_photo_urls_are_signed_and_expire(client, admin, device):
    upload(client, make_jpeg(), device)
    url = client.get("/api/v1/plants/plant01/photos/latest", headers=admin).json()["url"]
    assert client.get(url).status_code == 200
    assert client.get(url.split("?")[0]).status_code == 403
    assert client.get(url.split("&sig=")[0] + "&sig=" + "0" * 32).status_code == 403
    assert client.get("/api/v1/photos/plant01/..%2Fsecret.jpg?exp=9999999999&sig=x").status_code in (400, 403, 404)


def test_stored_key_is_relative_not_a_server_path(client, device, env):
    from app.db.database import db_session
    upload(client, make_jpeg(), device)
    with db_session() as db:
        key = db.execute("SELECT file_path FROM photos").fetchone()["file_path"]
    assert not key.startswith("/") and key.startswith("plant01/")


def test_analyze_never_changes_species(client, admin, device, monkeypatch):
    from app.api import routes
    upload(client, make_jpeg(), device)
    monkeypatch.setattr(routes, "analyze_plant_photo", lambda *a, **k: {"species_guess": "Basil", "confidence": 0.99, "analysis_status": "ok"})
    r = client.post("/api/v1/plants/plant01/photos/analyze", headers=admin)
    assert r.status_code == 200 and r.json()["species_updated"] is False
    assert client.get("/api/v1/plants", headers=admin).json()[0]["species"] in ("Unknown", "", None)


def test_chat_falls_back_to_grounded_rule_based_answer(client, admin):
    r = client.post("/api/v1/plants/plant01/chat", json={"question": "How is my plant?"}, headers=admin)
    assert r.status_code == 200 and r.json()["mode"] == "rule_based" and r.json()["llm_used"] is False


def test_vision_schema_normalization():
    from app.services.vision import normalize_vision
    out = normalize_vision({"species_guess": "Mint", "confidence": 7, "wilting": "yes", "notes": "x" * 999, "visible_observations": ["a", 3, None]})
    assert out["confidence"] == 1.0 and out["wilting"] is None and len(out["notes"]) == 400 and out["visible_observations"] == ["a"]
    assert out["schema_version"] == "1" and out["species_candidates"][0]["name"] == "Mint"


# ---------------- MQTT adapter
def test_mqtt_retained_telemetry_ignored_but_availability_kept(env):
    from app.services.mqtt_service import process_message
    from app.services.telemetry import latest_readings
    process_message("plants/plant01/soil/root", b"33", retain=True)
    assert "soil_root" not in latest_readings("plant01")
    process_message("plants/plant01/availability", b"offline", retain=True)
    from app.services import device_state
    assert device_state.device_summary("plant01")["state"] == "offline"


@pytest.mark.parametrize("bad", [0, 16, -3, "5", 5.0, None, True])
def test_publish_water_rejects_invalid_durations(bad):
    from app.services.mqtt_service import publish_water
    assert publish_water("plant01", bad)["published"] is False


def test_publish_strict_payload_format(monkeypatch):
    from app.core.config import settings
    from app.services import mqtt_service as m
    calls = []

    class Info:
        rc = 0
        def wait_for_publish(self, timeout=None): pass
        def is_published(self): return True

    class Fake:
        def is_connected(self): return True
        def publish(self, topic, payload=None, qos=0, retain=False):
            calls.append((topic, payload, qos, retain)); return Info()

    monkeypatch.setattr(m, "_client", Fake())
    monkeypatch.setattr(settings, "mqtt_enabled", True)
    assert m.publish_water("plant01", 15)["published"] is True
    assert calls == [("plants/plant01/water", "ON:15", 1, False)]


def test_public_broker_refused_unless_dev_flag(monkeypatch):
    from app.core.config import settings
    from app.services import mqtt_service as m
    monkeypatch.setattr(settings, "mqtt_enabled", True)
    monkeypatch.setattr(settings, "mqtt_host", "broker.hivemq.com")
    monkeypatch.setattr(settings, "mqtt_dev_public_broker", False)
    assert m.start_mqtt() is None and "public broker" in m.mqtt_status(True)["last_error"]


def test_queue_overflow_is_counted_not_silent(monkeypatch):
    import queue
    from app.services import mqtt_service as m
    q = queue.Queue(maxsize=1)
    q.put_nowait(("a", b"1", False))
    with pytest.raises(queue.Full):
        q.put_nowait(("b", b"2", False))
    assert "dropped_queue_full" in m._stats


def test_manual_water_api_guards(client, admin, monkeypatch):
    from app.services import irrigation
    monkeypatch.setattr(irrigation, "publish_water", lambda p, s: {"published": True, "topic": "t", "payload": f"ON:{s}", "message": "ok"})
    assert client.post("/api/v1/plants/plant01/water", json={"duration_seconds": 16}, headers=admin).status_code == 422
    ok = client.post("/api/v1/plants/plant01/water", json={"duration_seconds": 5}, headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "published"
    again = client.post("/api/v1/plants/plant01/water", json={"duration_seconds": 5}, headers=admin)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "pending_command"


def test_profile_validation_and_history_limits(client, admin):
    assert client.post("/api/v1/plants", json={"plant_id": "p2", "name": "x", "ideal_moisture_min": 70, "ideal_moisture_max": 40}, headers=admin).status_code == 422
    assert client.get("/api/v1/plants/plant01/readings/history?limit=99999", headers=admin).status_code == 422
    assert client.get("/api/v1/plants/plant01/readings/history?start=garbage", headers=admin).status_code == 422


def test_vpd_and_knowledge_catalog(client, admin):
    from app.services.vpd import calculate_vpd, vpd_band
    assert round(calculate_vpd(25, 50), 2) == 1.58 and calculate_vpd(None, 50) is None and calculate_vpd(20, 150) is None
    assert vpd_band(None) == "unavailable"
    assert client.get("/api/v1/plant-knowledge?q=tomato", headers=admin).json()["count"] >= 1
