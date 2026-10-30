import pytest

from app.db.database import db_session
from app.services.telemetry import IngestError, ingest_mqtt, latest_readings, prune_old_readings, record_reading, root_trend_pct_per_hour


@pytest.mark.parametrize("topic,payload", [
    ("plants/plant01/temp", b"500"), ("plants/plant01/temp", b"nan"), ("plants/plant01/temp", b"inf"),
    ("plants/plant01/humidity", b"500"), ("plants/plant01/humidity", b"-20"), ("plants/plant01/soil/root", b"120"),
    ("plants/plant01/soil/root", b"1e1"), ("plants/plant01/soil/root", b""), ("plants/plant01/soil/root", b"abc"),
    ("plants/plant01/soil/root", b"\xff\xfe"), ("plants/plant01/soil/root", b"4" * 100), ("plants/plant01/status", b"exploding"),
    ("plants/plant01/water", b"ON:15"), ("plants/plant01/soil/deep", b"10"), ("other/plant01/temp", b"20"),
    ("plants/bad id!/temp", b"20"), ("plants/ghost/soil/root", b"40"),
])
def test_invalid_messages_rejected(env, topic, payload):
    with pytest.raises(IngestError):
        ingest_mqtt(topic, payload)


def test_valid_firmware_topics_and_payload_shapes(env):
    for topic, payload in [("plants/plant01/soil/surface", b"41"), ("plants/plant01/soil/mid", b"42"), ("plants/plant01/soil/root", b"43"),
                           ("plants/plant01/temp", b"24.50"), ("plants/plant01/humidity", b"55.20")]:
        ingest_mqtt(topic, payload)
    r = latest_readings("plant01")
    assert r["soil_root"]["value"] == 43 and r["temperature_c"]["value"] == 24.5 and r["humidity_pct"]["value"] == 55.2


def test_duplicate_delivery_is_ignored_but_changes_are_kept(env):
    assert not ingest_mqtt("plants/plant01/soil/root", b"40").get("duplicate")
    assert ingest_mqtt("plants/plant01/soil/root", b"40")["duplicate"] is True
    assert not ingest_mqtt("plants/plant01/soil/root", b"41").get("duplicate")
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) c FROM readings WHERE metric='soil_root'").fetchone()["c"] == 2


def test_history_is_not_truncated_by_count(env):
    from datetime import datetime, timedelta, timezone
    base = datetime.now(timezone.utc) - timedelta(hours=20)
    for i in range(5200):
        record_reading("plant01", "soil_root", float(i % 90), "t", received_at=base + timedelta(seconds=i * 10))
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) c FROM readings WHERE metric='soil_root'").fetchone()["c"] >= 5000


def test_retention_is_age_based(env, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings
    monkeypatch.setattr(settings, "readings_retention_days", 30)
    record_reading("plant01", "soil_root", 40.0, "t", received_at=datetime.now(timezone.utc) - timedelta(days=45))
    record_reading("plant01", "soil_root", 41.0, "t")
    assert prune_old_readings() == 1


def test_status_is_not_stored_as_reading(env):
    ingest_mqtt("plants/plant01/status", b"watering")
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) c FROM readings WHERE metric='device_status'").fetchone()["c"] == 0
        assert db.execute("SELECT pump_status FROM device_status WHERE plant_id='plant01'").fetchone()["pump_status"] == "watering"


def test_quarantine_records_reason_and_is_bounded(env):
    from app.services.mqtt_service import process_message
    for i in range(520):
        process_message("plants/plant01/temp", b"999")
    with db_session() as db:
        n = db.execute("SELECT COUNT(*) c FROM quarantine_messages").fetchone()["c"]
        reason = db.execute("SELECT reason FROM quarantine_messages LIMIT 1").fetchone()["reason"]
    assert n == 500 and reason == "out_of_range"


def test_trend_unavailable_without_history_and_correct_with_it(env):
    from datetime import datetime, timedelta, timezone
    assert root_trend_pct_per_hour("plant01") is None
    now = datetime.now(timezone.utc)
    for i in range(10):  # -6 %/h over 45 minutes
        record_reading("plant01", "soil_root", 50 - i * 0.5, "t", received_at=now - timedelta(minutes=45 - i * 5))
    assert abs(root_trend_pct_per_hour("plant01") - (-6.0)) < 0.5


def test_freshness_states(env):
    from datetime import datetime, timedelta, timezone
    from app.services import device_state
    assert device_state.device_summary("plant01")["state"] == "offline"
    record_reading("plant01", "soil_root", 40.0, "t")
    assert device_state.device_summary("plant01")["state"] == "online"
    later = datetime.now(timezone.utc) + timedelta(seconds=120)
    assert device_state.device_summary("plant01", now=later)["state"] == "stale"
    assert device_state.device_summary("plant01", now=later + timedelta(seconds=400))["state"] == "offline"
