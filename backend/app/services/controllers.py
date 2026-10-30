"""Dispatches one control cycle per plant according to its ACTIVE experiment arm (default: the adaptive engine).

Baseline arms are deliberately simple and documented so comparisons are fair: both use the same irrigation controller, so the same
safety limits (15 s, cooldown, daily caps, pending-command block) apply to every arm. Nothing is sent unless `execute` is true."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import FIRMWARE_MAX_PUMP_S, settings
from app.db.database import db_session
from app.services import device_state, experiments, realtime
from app.services.decision_engine import Inputs, evaluate_plant, sensor_suspect
from app.services.irrigation import CommandRejected, request_watering
from app.services.telemetry import latest_readings


def schedule_due(now: datetime, reference: datetime, interval_hours: float) -> bool:
    return (now - reference).total_seconds() >= interval_hours * 3600


def _log(plant_id: str, source: str, action: str, seconds: int, reasons: list[str], inputs: dict, executed: bool, command_id: str | None) -> None:
    with db_session() as db:
        db.execute("INSERT INTO decisions(plant_id,created_at,source,decision,reason,readings_json,command_id,engine_version,duration_s,executed,inputs_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (plant_id, datetime.now(timezone.utc).isoformat(), source, action, " ".join(reasons), "{}", command_id, source, seconds, int(executed), json.dumps(inputs)))
    realtime.publish("decision", plant_id, {"decision": action, "source": source, "duration_seconds": seconds, "executed": executed})


def _try_water(plant_id, seconds, source_tag, reasons, execute):
    executed, command_id = False, None
    action = "water"
    if execute:
        try:
            ev = request_watering(plant_id, seconds, "auto", source_tag, " ".join(reasons)[:280])
            executed, command_id = bool(ev["published"]), ev["command_id"]
            reasons.append(ev["message"])
        except CommandRejected as exc:
            reasons.append(f"Command not sent: {exc.message}")
            action = "skip"
    return action, executed, command_id


def run_cycle(plant_id: str, execute: bool) -> dict:
    run = experiments.active_run(plant_id)
    if not run or run["arm"] == "adaptive":
        return evaluate_plant(plant_id, execute)
    with db_session() as db:
        plant = db.execute("SELECT mode FROM plants WHERE plant_id=?", (plant_id,)).fetchone()
    reasons: list[str] = [f"Experiment {run['key']}: control arm '{run['arm']}'."]
    inputs = {"arm": run["arm"], "params": run["params"], "experiment": run["key"]}
    device_state.sweep_unconfirmed()
    seconds = max(1, min(int(run["params"].get("seconds", 5)), FIRMWARE_MAX_PUMP_S))
    now = datetime.now(timezone.utc)
    action = "skip"
    executed, command_id = False, None
    if not plant or plant["mode"] != "auto":
        reasons.append("Plant is in Manual mode.")
    elif device_state.device_summary(plant_id)["state"] != "online":
        reasons.append("Node is not online; baseline waits so the pump can be observed.")
    elif run["arm"] == "fixed_schedule":
        with db_session() as db:
            last = db.execute("SELECT created_at FROM irrigation_events WHERE plant_id=? AND source IN ('auto','manual') AND status NOT IN ('failed_publish','not_sent','rejected') AND created_at>=? ORDER BY id DESC LIMIT 1",
                              (plant_id, run["started_at"])).fetchone()
        ref = datetime.fromisoformat(last["created_at"] if last else run["started_at"])
        if schedule_due(now, ref, float(run["params"].get("interval_hours", 12))):
            reasons.append(f"Fixed schedule due (every {run['params'].get('interval_hours', 12)} h): water {seconds}s regardless of soil moisture.")
            action, executed, command_id = _try_water(plant_id, seconds, f"fixed_schedule:{run['key']}", reasons, execute)
        else:
            reasons.append("Fixed schedule not due yet.")
    else:  # fixed_threshold
        r = latest_readings(plant_id)
        root = r.get("soil_root")
        suspect = sensor_suspect(Inputs(root=root["value"] if root else None, mid=r.get("soil_mid", {}).get("value"), surface=r.get("soil_surface", {}).get("value")))
        thr = float(run["params"].get("threshold_pct", 35.0))
        if not root or root["age_seconds"] > settings.decision_max_age_s:
            reasons.append("Root reading missing or stale; fail-safe skip.")
        elif suspect:
            reasons.append(f"Sensor check failed: {suspect}; skip.")
        elif root["value"] < thr:
            reasons.append(f"Root moisture {root['value']:.1f}% < fixed threshold {thr:.0f}%: water {seconds}s (no hysteresis, trend or weather).")
            action, executed, command_id = _try_water(plant_id, seconds, f"fixed_threshold:{run['key']}", reasons, execute)
        else:
            reasons.append(f"Root moisture {root['value']:.1f}% >= fixed threshold {thr:.0f}%.")
    _log(plant_id, run["arm"], action, seconds if action == "water" else 0, reasons, inputs, executed, command_id)
    return {"plant_id": plant_id, "decision": action, "reasons": reasons, "reason": " ".join(reasons), "executed": executed, "arm": run["arm"], "duration_seconds": seconds if action == "water" else 0}
