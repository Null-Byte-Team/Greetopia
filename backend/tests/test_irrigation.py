from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.database import db_session
from app.services import device_state, irrigation
from app.services.irrigation import CommandRejected, request_watering
from app.services.telemetry import ingest_mqtt


@pytest.fixture()
def broker(monkeypatch):
    sent = []

    def fake(plant_id, seconds):
        if not isinstance(seconds, int) or not 1 <= seconds <= 15:
            return {"published": False, "topic": "t", "payload": None, "message": "bad"}
        sent.append((plant_id, seconds))
        return {"published": True, "topic": f"plants/{plant_id}/water", "payload": f"ON:{seconds}", "message": "ok"}

    monkeypatch.setattr(irrigation, "publish_water", fake)
    return sent


def age_events(minutes):
    with db_session() as db:
        db.execute("UPDATE irrigation_events SET created_at=?", ((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(),))


def status(plant="plant01"):
    with db_session() as db:
        return [dict(r) for r in db.execute("SELECT * FROM irrigation_events ORDER BY id").fetchall()]


@pytest.mark.parametrize("bad", [0, 16, -1, 99, True, "5", 2.5])
def test_duration_bounds_enforced(env, broker, bad):
    with pytest.raises(CommandRejected):
        request_watering("plant01", bad, "manual", "u", "r")
    assert broker == []


def test_manual_command_recorded_as_published_not_executed(env, broker):
    r = request_watering("plant01", 5, "manual", "alice@example.com", "dry leaf")
    ev = status()[0]
    assert r["status"] == "published" and ev["status"] == "published" and ev["requested_by"] == "alice@example.com"
    assert ev["estimated_water_ml"] is None and ev["measured_water_ml"] is None  # no calibrated flow, no sensor


def test_estimated_volume_only_with_calibration(env, broker, monkeypatch):
    monkeypatch.setattr(settings, "flow_ml_per_second", 20.0)
    assert request_watering("plant01", 5, "manual", "u", "r")["estimated_water_ml"] == 100.0


def test_pending_command_blocks_duplicate(env, broker):
    request_watering("plant01", 5, "manual", "u", "r")
    with pytest.raises(CommandRejected) as e:
        request_watering("plant01", 5, "manual", "u", "r")
    assert e.value.code == "pending_command" and len(broker) == 1


def test_cooldown_and_daily_caps(env, broker, monkeypatch):
    request_watering("plant01", 10, "manual", "u", "r")
    ingest_mqtt("plants/plant01/status", b"watering")
    ingest_mqtt("plants/plant01/status", b"idle")
    with pytest.raises(CommandRejected) as e:
        request_watering("plant01", 5, "manual", "u", "r")
    assert e.value.code == "cooldown"
    age_events(5)
    request_watering("plant01", 10, "manual", "u", "r")
    ingest_mqtt("plants/plant01/status", b"watering")
    ingest_mqtt("plants/plant01/status", b"idle")
    age_events(5)
    monkeypatch.setattr(settings, "max_daily_runtime_seconds", 25)
    with pytest.raises(CommandRejected) as e:
        request_watering("plant01", 10, "manual", "u", "r")
    assert e.value.code == "daily_runtime_limit"


def test_reconciliation_published_to_confirmed(env, broker):
    request_watering("plant01", 5, "auto", "engine", "r")
    ingest_mqtt("plants/plant01/status", b"watering")
    assert status()[0]["status"] == "observed_watering" and status()[0]["observed_start_at"]
    ingest_mqtt("plants/plant01/status", b"idle")
    ev = status()[0]
    assert ev["status"] == "confirmed" and ev["observed_end_at"]


def test_unconfirmed_is_marked_and_never_retried(env, broker):
    request_watering("plant01", 5, "auto", "engine", "r")
    n = device_state.sweep_unconfirmed(datetime.now(timezone.utc) + timedelta(seconds=settings.confirm_timeout_seconds + 5))
    assert n == 1 and status()[0]["status"] == "unconfirmed" and len(broker) == 1
    with db_session() as db:
        assert db.execute("SELECT 1 FROM alerts WHERE kind='command_unconfirmed'").fetchone()


def test_watering_without_command_raises_critical_alert(env):
    ingest_mqtt("plants/plant01/status", b"watering")
    ev = status()[0]
    assert ev["source"] == "unrequested"
    with db_session() as db:
        assert db.execute("SELECT severity FROM alerts WHERE kind='unrequested_watering'").fetchone()["severity"] == "critical"


def test_duplicate_watering_status_is_idempotent(env, broker):
    request_watering("plant01", 5, "auto", "engine", "r")
    ingest_mqtt("plants/plant01/status", b"watering")
    ingest_mqtt("plants/plant01/status", b"watering")
    assert len(status()) == 1


def test_device_ack_and_rejection(env, broker):
    request_watering("plant01", 5, "auto", "engine", "r")
    ingest_mqtt("plants/plant01/ack", b"accepted:5")
    assert status()[0]["status"] == "acknowledged"
    ingest_mqtt("plants/plant01/status", b"watering")
    assert status()[0]["status"] == "observed_watering"


def test_failed_publish_is_recorded_and_does_not_consume_cooldown(env, monkeypatch):
    monkeypatch.setattr(irrigation, "publish_water", lambda p, s: {"published": False, "topic": "t", "payload": "ON:5", "message": "MQTT disabled"})
    r = request_watering("plant01", 5, "manual", "u", "r")
    assert r["status"] == "failed_publish" and r["published"] is False
    request_watering("plant01", 5, "manual", "u", "r")  # allowed again: nothing was sent


def test_availability_lastwill_and_fault_alerts(env):
    ingest_mqtt("plants/plant01/soil/root", b"40")
    ingest_mqtt("plants/plant01/availability", b"offline")
    assert device_state.device_summary("plant01")["state"] == "offline"
    ingest_mqtt("plants/plant01/fault", b"soil_root:disconnected")
    with db_session() as db:
        assert db.execute("SELECT 1 FROM alerts WHERE kind='sensor_fault'").fetchone()


def test_auto_execution_end_to_end(env, broker, monkeypatch):
    from app.services.decision_engine import evaluate_plant
    from app.services.telemetry import record_reading
    record_reading("plant01", "soil_root", 10.0, "t")
    res = evaluate_plant("plant01", execute=True, requested_by="engine")
    assert res["executed"] and broker == [("plant01", res["duration_seconds"])]
    assert evaluate_plant("plant01", execute=True)["executed"] is False  # pending/cooldown blocks a second command
    assert len(broker) == 1
