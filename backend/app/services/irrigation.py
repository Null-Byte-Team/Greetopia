"""Single entry point for every pump command (manual or automatic).

Guards enforced here (not in the UI): duration 1..15 s, no overlapping/pending command, cooldown,
daily runtime and command-count caps. A command is recorded as 'published' (handed to the broker),
never as 'executed'; the device state reconciler promotes it to 'confirmed' only when telemetry agrees.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import FIRMWARE_MAX_PUMP_S, settings
from app.db.database import db_session
from app.services import device_state
from app.services.mqtt_service import publish_water

_lock = threading.Lock()


class CommandRejected(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status


def _now():
    return datetime.now(timezone.utc)


def daily_usage(db, plant_id: str, now: datetime) -> tuple[int, int]:
    since = (now - timedelta(hours=24)).isoformat()
    row = db.execute(
        "SELECT COALESCE(SUM(duration_seconds),0) s, COUNT(*) c FROM irrigation_events WHERE plant_id=? AND created_at>=? "
        "AND source IN ('auto','manual') AND status NOT IN ('failed_publish','not_sent','rejected')", (plant_id, since)).fetchone()
    return int(row["s"]), int(row["c"])


def check_guards(db, plant_id: str, seconds: int, source: str, now: datetime) -> None:
    pending = db.execute("SELECT id FROM irrigation_events WHERE plant_id=? AND status IN ('published','queued','acknowledged','observed_watering') "
                         "AND created_at>=?", (plant_id, (now - timedelta(seconds=settings.confirm_timeout_seconds + 30)).isoformat())).fetchone()
    if pending:
        raise CommandRejected("pending_command", "A previous watering command is still pending or in progress.")
    dev = db.execute("SELECT pump_status,pump_observed_at FROM device_status WHERE plant_id=?", (plant_id,)).fetchone()
    if dev and dev["pump_status"] == "watering" and dev["pump_observed_at"]:
        if (now - datetime.fromisoformat(dev["pump_observed_at"])).total_seconds() < FIRMWARE_MAX_PUMP_S + 10:
            raise CommandRejected("pump_running", "The pump is currently running.")
    cooldown = settings.manual_cooldown_seconds if source == "manual" else settings.irrigation_cooldown_minutes * 60
    last = db.execute("SELECT created_at FROM irrigation_events WHERE plant_id=? AND source IN ('auto','manual') "
                      "AND status NOT IN ('failed_publish','not_sent','rejected') ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
    if last:
        wait = cooldown - (now - datetime.fromisoformat(last["created_at"])).total_seconds()
        if wait > 0:
            raise CommandRejected("cooldown", f"Cooldown active: wait {int(wait) + 1} more seconds.", 429)
    used_s, used_n = daily_usage(db, plant_id, now)
    if used_n >= settings.max_commands_per_day:
        raise CommandRejected("daily_command_limit", f"Daily command limit reached ({settings.max_commands_per_day}).", 429)
    if used_s + seconds > settings.max_daily_runtime_seconds:
        raise CommandRejected("daily_runtime_limit", f"Daily pump runtime limit reached ({settings.max_daily_runtime_seconds}s in 24h).", 429)


def request_watering(plant_id: str, seconds: int, source: str, requested_by: str, reason: str, decision_id: int | None = None) -> dict:
    if source not in ("auto", "manual"):
        raise ValueError("source must be 'auto' or 'manual'")
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= FIRMWARE_MAX_PUMP_S:
        raise CommandRejected("bad_duration", f"Duration must be 1..{FIRMWARE_MAX_PUMP_S} seconds.", 422)
    with _lock:  # serialize: two simultaneous requests must not both pass the guards
        now = _now()
        with db_session() as db:
            check_guards(db, plant_id, seconds, source, now)
        result = publish_water(plant_id, seconds)
        flow = settings.flow_ml_per_second
        estimated = round(seconds * flow, 1) if flow and result["published"] else None
        status = "published" if result["published"] else "failed_publish"
        command_id = str(uuid.uuid4())
        with db_session() as db:
            cur = db.execute(
                "INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,estimated_water_ml,command_id,status,requested_by,reason) "
                "VALUES(?,?,?,?,?,?,?,?,?)", (plant_id, now.isoformat(), source, seconds, estimated, command_id, status, requested_by[:60], (reason or "")[:300]))
            event_id = cur.lastrowid
            if not result["published"]:
                device_state.add_alert(db, plant_id, "command_not_sent", result["message"])
    return {"event_id": event_id, "command_id": command_id, "plant_id": plant_id, "duration_seconds": seconds, "status": status,
            "published": result["published"], "topic": result["topic"], "payload": result["payload"], "message": result["message"],
            "estimated_water_ml": estimated, "water_volume_note": "Estimated from a configured flow rate, not measured." if estimated is not None else "Volume unavailable: no calibrated flow rate configured."}
