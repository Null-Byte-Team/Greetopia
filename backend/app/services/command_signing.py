"""Optional HMAC signing of pump commands (replay + spoofing protection even on a shared broker).

Wire format: ON:<seconds>:<counter>:<mac>   mac = first 16 hex chars of HMAC-SHA256(key, "<plant_id>|<seconds>|<counter>").
The counter is strictly increasing (persisted per plant, and never below the current unix time so a database reset cannot reuse
old numbers). The node remembers the last accepted counter and rejects anything not greater. A signature proves the command came
from the backend; it does NOT replace the node's own limits (15 s, rest, hourly budget), which still apply."""
from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import settings
from app.db.database import db_session


def enabled() -> bool:
    return bool(settings.command_signing_key)


def mac(plant_id: str, seconds: int, counter: int, key: str | None = None) -> str:
    k = (key or settings.command_signing_key).encode()
    return hmac.new(k, f"{plant_id}|{seconds}|{counter}".encode(), hashlib.sha256).hexdigest()[:16]


def next_counter(plant_id: str) -> int:
    with db_session() as db:
        row = db.execute("SELECT counter FROM command_counters WHERE plant_id=?", (plant_id,)).fetchone()
        value = max((row["counter"] if row else 0) + 1, int(time.time()))
        db.execute("INSERT INTO command_counters(plant_id,counter) VALUES(?,?) ON CONFLICT(plant_id) DO UPDATE SET counter=excluded.counter", (plant_id, value))
    return value


def build_payload(plant_id: str, seconds: int) -> str:
    if not enabled():
        return f"ON:{seconds}"
    c = next_counter(plant_id)
    return f"ON:{seconds}:{c}:{mac(plant_id, seconds, c)}"
