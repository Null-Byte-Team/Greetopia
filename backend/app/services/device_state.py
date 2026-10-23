"""Device state derived from telemetry + reconciliation of irrigation commands with observed pump status.

The sensor-node firmware has no command IDs. A requested command is therefore recorded separately
from what the device later reports ("watering" / "idle"). Outcomes that cannot be confirmed stay
"unconfirmed" and are NEVER retried automatically (a retry could water the plant twice).

Event status lifecycle (irrigation_events.status):
  published -> acknowledged (optional, new firmware) -> observed_watering -> confirmed
  side states: failed_publish | rejected | unconfirmed | unconfirmed_end | unrequested
  legacy values from earlier versions: queued (= published), not_sent (= failed_publish)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.database import db_session

PENDING = ("published", "queued", "acknowledged")
FAILED = ("failed_publish", "not_sent", "rejected")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None):
    if not ts:
        return None
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_alert(db, plant_id: str | None, kind: str, message: str, severity: str = "warning") -> None:
    recent = db.execute(
        "SELECT id FROM alerts WHERE plant_id IS ? AND kind=? AND resolved_at IS NULL AND created_at > ?",
        (plant_id, kind, (_now() - timedelta(minutes=30)).isoformat())).fetchone()
    if recent:  # de-duplicate alert storms
        return
    db.execute("INSERT INTO alerts(plant_id,kind,severity,message,created_at) VALUES(?,?,?,?,?)",
               (plant_id, kind, severity, message[:300], _now().isoformat()))


def touch(db, plant_id: str, now: datetime) -> None:
    db.execute("INSERT INTO device_status(plant_id,last_message_at) VALUES(?,?) "
               "ON CONFLICT(plant_id) DO UPDATE SET last_message_at=excluded.last_message_at", (plant_id, now.isoformat()))


def record_status(plant_id: str, status: str, now: datetime | None = None) -> dict:
    """Handle plants/{id}/status ("watering" | "idle") and reconcile with the newest command."""
    now = now or _now()
    result = {"reconciled": None}
    with db_session() as db:
        prev = db.execute("SELECT pump_status FROM device_status WHERE plant_id=?", (plant_id,)).fetchone()
        prev_status = prev["pump_status"] if prev else None
        db.execute("INSERT INTO device_status(plant_id,pump_status,pump_observed_at,last_message_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(plant_id) DO UPDATE SET pump_status=excluded.pump_status,"
                   "pump_observed_at=excluded.pump_observed_at,last_message_at=excluded.last_message_at",
                   (plant_id, status, now.isoformat(), now.isoformat()))
        if status == "watering":
            if prev_status == "watering":
                return result  # duplicate delivery
            window = (now - timedelta(seconds=settings.confirm_timeout_seconds)).isoformat()
            ev = db.execute(
                "SELECT id FROM irrigation_events WHERE plant_id=? AND status IN ('published','queued','acknowledged') "
                "AND created_at>=? ORDER BY id DESC LIMIT 1", (plant_id, window)).fetchone()
            if ev:
                db.execute("UPDATE irrigation_events SET status='observed_watering',observed_start_at=? WHERE id=?",
                           (now.isoformat(), ev["id"]))
                result["reconciled"] = ev["id"]
            else:
                cur = db.execute(
                    "INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,command_id,status,observed_start_at,reason) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (plant_id, now.isoformat(), "unrequested", 0, "none", "unrequested", now.isoformat(),
                     "Pump reported 'watering' without a matching backend command"))
                result["reconciled"] = cur.lastrowid
                add_alert(db, plant_id, "unrequested_watering",
                          "The pump reported watering but no command was issued by this system. Check MQTT broker access control.",
                          "critical")
        elif status == "idle":
            ev = db.execute("SELECT id FROM irrigation_events WHERE plant_id=? AND status IN ('observed_watering','unrequested') "
                            "AND observed_end_at IS NULL ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
            if ev:
                db.execute("UPDATE irrigation_events SET observed_end_at=?,status=CASE status WHEN 'unrequested' THEN 'unrequested' ELSE 'confirmed' END WHERE id=?",
                           (now.isoformat(), ev["id"]))
                result["reconciled"] = ev["id"]
    return result


def record_ack(plant_id: str, payload: str, now: datetime | None = None) -> None:
    """Optional acknowledgement from newer firmware: 'accepted:<s>' | 'rejected:<reason>'."""
    now = now or _now()
    with db_session() as db:
        db.execute("INSERT INTO device_status(plant_id,last_ack,last_ack_at,last_message_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(plant_id) DO UPDATE SET last_ack=excluded.last_ack,last_ack_at=excluded.last_ack_at,"
                   "last_message_at=excluded.last_message_at", (plant_id, payload, now.isoformat(), now.isoformat()))
        ev = db.execute("SELECT id FROM irrigation_events WHERE plant_id=? AND status IN ('published','queued') "
                        "ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
        if not ev:
            return
        if payload.startswith("accepted"):
            db.execute("UPDATE irrigation_events SET status='acknowledged' WHERE id=?", (ev["id"],))
        elif payload.startswith("rejected"):
            db.execute("UPDATE irrigation_events SET status='rejected',reason=COALESCE(reason,'')||' [device: '||?||']' WHERE id=?",
                       (payload, ev["id"]))
            add_alert(db, plant_id, "command_rejected", f"Device rejected the watering command ({payload}).")


def record_availability(plant_id: str, value: str, now: datetime | None = None) -> None:
    now = now or _now()
    with db_session() as db:
        db.execute("INSERT INTO device_status(plant_id,availability,availability_at,last_message_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(plant_id) DO UPDATE SET availability=excluded.availability,availability_at=excluded.availability_at,"
                   "last_message_at=excluded.last_message_at", (plant_id, value, now.isoformat(), now.isoformat()))
        if value == "offline":
            add_alert(db, plant_id, "device_offline", "The sensor node went offline (broker last-will).")


def record_fault(plant_id: str, payload: str, now: datetime | None = None) -> None:
    now = now or _now()
    with db_session() as db:
        db.execute("INSERT INTO device_status(plant_id,last_fault,last_fault_at,last_message_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(plant_id) DO UPDATE SET last_fault=excluded.last_fault,last_fault_at=excluded.last_fault_at,"
                   "last_message_at=excluded.last_message_at", (plant_id, payload, now.isoformat(), now.isoformat()))
        add_alert(db, plant_id, "sensor_fault", f"Sensor fault reported by the device: {payload}")


def sweep_unconfirmed(now: datetime | None = None) -> int:
    """Mark commands that never produced an observed status as 'unconfirmed'. Never re-sends."""
    now = now or _now()
    cutoff = (now - timedelta(seconds=settings.confirm_timeout_seconds)).isoformat()
    open_cutoff = (now - timedelta(seconds=settings.confirm_timeout_seconds + 30)).isoformat()
    n = 0
    with db_session() as db:
        for ev in db.execute("SELECT id,plant_id FROM irrigation_events WHERE status IN ('published','queued','acknowledged') AND created_at<?", (cutoff,)).fetchall():
            db.execute("UPDATE irrigation_events SET status='unconfirmed' WHERE id=?", (ev["id"],))
            add_alert(db, ev["plant_id"], "command_unconfirmed",
                      "A watering command was published but the device never reported 'watering'. It was NOT repeated.")
            n += 1
        for ev in db.execute("SELECT id,plant_id FROM irrigation_events WHERE status='observed_watering' AND observed_start_at<?", (open_cutoff,)).fetchall():
            db.execute("UPDATE irrigation_events SET status='unconfirmed_end' WHERE id=?", (ev["id"],))
            add_alert(db, ev["plant_id"], "pump_end_unconfirmed",
                      "The pump reported 'watering' but never reported 'idle'. Check the pump and relay.", "critical")
            n += 1
    return n


def device_summary(plant_id: str, now: datetime | None = None) -> dict:
    """online / stale / offline derived from the last valid message (thresholds are configuration, not firmware guarantees)."""
    now = now or _now()
    with db_session() as db:
        row = db.execute("SELECT * FROM device_status WHERE plant_id=?", (plant_id,)).fetchone()
    if not row or not row["last_message_at"]:
        return {"state": "offline", "age_seconds": None, "pump_status": None, "last_message_at": None, "basis": "no telemetry received"}
    last = _parse(row["last_message_at"])
    age = max(0, int((now - last).total_seconds()))
    if row["availability"] == "offline" and (_parse(row["availability_at"]) or last) >= last - timedelta(seconds=1):
        state = "offline"
    elif age <= settings.device_online_max_age_s:
        state = "online"
    elif age <= settings.device_stale_max_age_s:
        state = "stale"
    else:
        state = "offline"
    return {"state": state, "age_seconds": age, "pump_status": row["pump_status"], "pump_observed_at": row["pump_observed_at"],
            "last_message_at": row["last_message_at"], "last_fault": row["last_fault"], "last_ack": row["last_ack"],
            "basis": "derived from last valid telemetry message"}
