import math
import re
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.database import db_session
from app.services import device_state

NUMERIC_METRICS = {"soil_surface", "soil_mid", "soil_root", "temperature_c", "humidity_pct", "leaf_wetness_pct"}
PERCENT_METRICS = {"soil_surface", "soil_mid", "soil_root", "humidity_pct", "leaf_wetness_pct"}

# MQTT topic suffix -> internal metric. "temp"/"humidity" are the exact firmware topics.
ALLOWED_METRICS = {
    "soil/surface": "soil_surface", "soil/mid": "soil_mid", "soil/root": "soil_root",
    "temp": "temperature_c", "humidity": "humidity_pct", "leaf_wetness": "leaf_wetness_pct",
    "status": "device_status", "availability": "device_availability", "ack": "device_ack", "fault": "device_fault",
}
PLANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
NUMBER_RE = re.compile(r"^-?\d{1,4}(\.\d{1,3})?$")
MAX_PAYLOAD_BYTES = 48
DUPLICATE_WINDOW_S = 1.0


class IngestError(ValueError):
    """A message that must be rejected/quarantined. `reason` is a short machine-friendly code."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


def utcnow():
    return datetime.now(timezone.utc)


def validate_number(metric: str, value: float) -> float:
    if not math.isfinite(value):
        raise IngestError("not_finite", "Reading must be a finite number")
    if metric in PERCENT_METRICS and not 0 <= value <= 100:
        raise IngestError("out_of_range", "Percent reading must be 0..100")
    if metric == "temperature_c" and not -40 <= value <= 85:
        raise IngestError("out_of_range", "Temperature out of range (-40..85 C)")
    return value


def parse_payload(metric: str, payload: str):
    text = payload.strip()
    if metric == "device_status":
        value = text.lower()
        if value not in {"idle", "watering"}:
            raise IngestError("bad_status", "Invalid status")
        return value
    if metric == "device_availability":
        value = text.lower()
        if value not in {"online", "offline"}:
            raise IngestError("bad_availability", "Invalid availability")
        return value
    if metric == "device_ack":
        if not re.fullmatch(r"(accepted:\d{1,2}|rejected:[a-z_]{1,20})", text.lower()):
            raise IngestError("bad_ack", "Invalid acknowledgement")
        return text.lower()
    if metric == "device_fault":
        if not re.fullmatch(r"[a-z_]{1,24}:[a-z_]{1,24}", text.lower()):
            raise IngestError("bad_fault", "Invalid fault code")
        return text.lower()
    if not NUMBER_RE.fullmatch(text):
        raise IngestError("bad_number", "Payload is not a plain decimal number")
    return validate_number(metric, float(text))


def plant_exists(db, plant_id: str) -> bool:
    return db.execute("SELECT 1 FROM plants WHERE plant_id=?", (plant_id,)).fetchone() is not None


def record_reading(plant_id: str, metric: str, value, topic: str, received_at=None):
    """Persist one numeric reading (history is never overwritten) and refresh the latest snapshot."""
    if metric not in NUMERIC_METRICS:
        raise IngestError("bad_metric", f"Unsupported metric {metric}")
    value = validate_number(metric, float(value))
    now = received_at or utcnow()
    stamp = now.isoformat()
    with db_session() as db:
        if not plant_exists(db, plant_id):
            raise IngestError("unknown_plant", "Plant is not registered")
        last = db.execute("SELECT value,received_at FROM latest_readings WHERE plant_id=? AND metric=?", (plant_id, metric)).fetchone()
        if last and last["value"] == value and (now - datetime.fromisoformat(last["received_at"])).total_seconds() < DUPLICATE_WINDOW_S:
            return {"plant_id": plant_id, "metric": metric, "value": value, "received_at": last["received_at"], "topic": topic, "duplicate": True}
        db.execute("INSERT INTO readings(plant_id,metric,value,received_at,topic) VALUES(?,?,?,?,?)", (plant_id, metric, value, stamp, topic))
        db.execute("INSERT INTO latest_readings(plant_id,metric,value,received_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(plant_id,metric) DO UPDATE SET value=excluded.value,received_at=excluded.received_at",
                   (plant_id, metric, value, stamp))
        device_state.touch(db, plant_id, now)
    return {"plant_id": plant_id, "metric": metric, "value": value, "received_at": stamp, "topic": topic}


def split_topic(topic: str):
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "plants":
        raise IngestError("bad_topic", "Unexpected topic")
    plant_id, suffix = parts[1], "/".join(parts[2:])
    if not PLANT_ID_RE.fullmatch(plant_id):
        raise IngestError("bad_plant_id", "Invalid plant id")
    metric = ALLOWED_METRICS.get(suffix)
    if not metric:
        raise IngestError("unsupported_topic", f"Unsupported topic: {suffix}")
    return plant_id, metric


def ingest_mqtt(topic: str, payload: bytes | str):
    if len(topic) > 120:
        raise IngestError("bad_topic", "Topic too long")
    plant_id, metric = split_topic(topic)
    raw = payload if isinstance(payload, bytes) else str(payload).encode()
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise IngestError("payload_too_long", "Payload too long")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError("bad_encoding", "Payload is not UTF-8") from exc
    value = parse_payload(metric, text)
    if metric in NUMERIC_METRICS:
        return record_reading(plant_id, metric, value, topic)
    with db_session() as db:
        if not plant_exists(db, plant_id):
            raise IngestError("unknown_plant", "Plant is not registered")
    if metric == "device_status":
        device_state.record_status(plant_id, value)
    elif metric == "device_availability":
        device_state.record_availability(plant_id, value)
    elif metric == "device_ack":
        device_state.record_ack(plant_id, value)
    elif metric == "device_fault":
        device_state.record_fault(plant_id, value)
    return {"plant_id": plant_id, "metric": metric, "value": value, "topic": topic}


def quarantine(topic: str, payload: bytes, reason: str, keep: int = 500) -> None:
    preview = payload[:40].decode("utf-8", "replace")
    with db_session() as db:
        db.execute("INSERT INTO quarantine_messages(topic,payload_preview,reason,received_at) VALUES(?,?,?,?)",
                   (topic[:200], preview, reason[:80], utcnow().isoformat()))
        db.execute("DELETE FROM quarantine_messages WHERE id NOT IN (SELECT id FROM quarantine_messages ORDER BY id DESC LIMIT ?)", (keep,))


def prune_old_readings() -> int:
    """Age-based retention (default 90 days; 0 keeps everything). Never count-based truncation."""
    if settings.readings_retention_days <= 0:
        return 0
    cutoff = (utcnow() - timedelta(days=settings.readings_retention_days)).isoformat()
    with db_session() as db:
        return db.execute("DELETE FROM readings WHERE received_at<?", (cutoff,)).rowcount


def latest_readings(plant_id: str):
    with db_session() as db:
        rows = db.execute("SELECT * FROM latest_readings WHERE plant_id=?", (plant_id,)).fetchall()
    now = utcnow()
    result = {}
    for r in rows:
        age = (now - datetime.fromisoformat(r["received_at"])).total_seconds()
        result[r["metric"]] = {"value": r["value"], "received_at": r["received_at"], "age_seconds": max(0, round(age)),
                               "fresh": age <= settings.sensor_stale_minutes * 60}
    return result


def history(plant_id: str, metric: str | None = None, limit: int = 200, start: str | None = None, end: str | None = None):
    q, args = "SELECT metric,value,received_at FROM readings WHERE plant_id=?", [plant_id]
    if metric:
        q += " AND metric=?"
        args.append(metric)
    if start:
        q += " AND received_at>=?"
        args.append(start)
    if end:
        q += " AND received_at<=?"
        args.append(end)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with db_session() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in reversed(rows)]


def root_trend_pct_per_hour(plant_id: str, window_min: int | None = None):
    """Least-squares slope of root-zone moisture over the window; None if there is not enough real data."""
    window_min = window_min or settings.trend_window_minutes
    since = (utcnow() - timedelta(minutes=window_min)).isoformat()
    with db_session() as db:
        rows = db.execute("SELECT value,received_at FROM readings WHERE plant_id=? AND metric='soil_root' AND received_at>=? ORDER BY id",
                          (plant_id, since)).fetchall()
    if len(rows) < 6:
        return None
    t0 = datetime.fromisoformat(rows[0]["received_at"])
    xs = [(datetime.fromisoformat(r["received_at"]) - t0).total_seconds() / 3600 for r in rows]
    ys = [r["value"] for r in rows]
    if xs[-1] - xs[0] < (window_min / 60) / 3:  # need at least a third of the window covered
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 3)
