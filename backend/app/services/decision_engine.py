"""Deterministic irrigation decision engine.

`decide()` is a pure function (no I/O) so every rule is unit-testable and every decision can be reconstructed
from the inputs stored in `decisions.inputs_json`. `evaluate_plant()` gathers inputs, logs the decision and,
only when asked and allowed, sends ONE command through the irrigation controller.

Priority order (first blocking rule wins):
  1 sensor freshness/quality -> 2 Auto mode -> 3 safety (running pump, pending command, cooldown, daily caps)
  -> 4 root-zone moisture vs the plant's own profile with hysteresis -> 5 trend -> 6 weather
  -> 7 ML (not available: no trained model exists) -> 8 vision (secondary evidence only)
  -> 9 decide -> 10 bounded duration -> 11 final safety clamp.
The engine NEVER repeats a command because acknowledgement is missing.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import FIRMWARE_MAX_PUMP_S, settings
from app.db.database import db_session
from app.services import device_state
from app.services.irrigation import CommandRejected, daily_usage, request_watering
from app.services.telemetry import latest_readings, root_trend_pct_per_hour
from app.services.vpd import calculate_vpd, vpd_band
from app.services.weather import get_weather

ENGINE_VERSION = "2.0"


@dataclass
class Params:
    cooldown_s: int = 1800
    max_daily_runtime_s: int = 60
    max_commands_per_day: int = 6
    hysteresis_pct: float = 5.0
    rain_skip_probability: float = 0.65
    rain_critical_margin_pct: float = 10.0
    min_water_s: int = 3
    seconds_per_deficit_pct: float = 0.4
    max_age_s: int = 90
    trend_horizon_min: int = 60
    max_command_s: int = FIRMWARE_MAX_PUMP_S


@dataclass
class Inputs:
    mode: str = "auto"
    low_pct: float = 28.0  # trigger: plant profile ideal_moisture_min
    target_pct: float = 65.0  # satisfied level: ideal_moisture_max
    root: float | None = None
    root_age_s: float | None = None
    mid: float | None = None
    surface: float | None = None
    vpd_kpa: float | None = None
    pump_status: str | None = None
    pump_status_age_s: float | None = None
    pending_command: bool = False
    seconds_since_last_command: float | None = None
    runtime_24h_s: int = 0
    commands_24h: int = 0
    trend_pct_per_hour: float | None = None
    rain_probability: float | None = None  # None = forecast unavailable (NOT zero)
    vision_wilting: bool | None = None
    vision_confidence: float | None = None
    ml_stress_probability: float | None = None  # no validated model exists yet


@dataclass
class Decision:
    action: str = "skip"  # water | skip
    code: str = ""
    duration_s: int = 0
    reasons: list[str] = field(default_factory=list)


def sensor_suspect(i: Inputs) -> str | None:
    """Physically inconsistent depth profiles usually mean a disconnected/shorted probe, not a dry root zone."""
    if i.root is None:
        return None
    others = [v for v in (i.mid, i.surface) if v is not None]
    if i.root <= 1 and others and max(others) >= 30:
        return "root probe reads ~0% while shallower probes are wet (possible disconnected probe)"
    if i.root >= 99 and others and max(others) <= 15:
        return "root probe reads ~100% while shallower probes are dry (possible short circuit)"
    return None


def decide(i: Inputs, p: Params) -> Decision:
    d = Decision()
    band_top = min(i.low_pct + p.hysteresis_pct, i.target_pct)

    # 1. freshness & quality ------------------------------------------------------------------
    if i.root is None or i.root_age_s is None:
        d.code = "no_root_reading"
        d.reasons.append("No root-zone reading is available; fail-safe skip.")
        return d
    if i.root_age_s > p.max_age_s:
        d.code = "stale_root_reading"
        d.reasons.append(f"Root-zone reading is {int(i.root_age_s)}s old (limit {p.max_age_s}s); fail-safe skip.")
        return d
    problem = sensor_suspect(i)
    if problem:
        d.code = "sensor_suspect"
        d.reasons.append(f"Sensor check failed: {problem}. Watering skipped; inspect the probe.")
        return d
    # 2. mode ---------------------------------------------------------------------------------
    if i.mode != "auto":
        d.code = "manual_mode"
        d.reasons.append("Plant is in Manual mode; automatic watering is disabled.")
        return d
    # 3. safety -------------------------------------------------------------------------------
    if i.pump_status == "watering" and (i.pump_status_age_s is None or i.pump_status_age_s < p.max_command_s + 10):
        d.code = "pump_running"
        d.reasons.append("The pump is currently running.")
        return d
    if i.pending_command:
        d.code = "pending_command"
        d.reasons.append("A previous command is still pending or unconfirmed; not sending another.")
        return d
    if i.seconds_since_last_command is not None and i.seconds_since_last_command < p.cooldown_s:
        d.code = "cooldown"
        d.reasons.append(f"Cooldown active ({int(p.cooldown_s - i.seconds_since_last_command)}s left); water needs time to reach the root zone.")
        return d
    if i.commands_24h >= p.max_commands_per_day:
        d.code = "daily_command_limit"
        d.reasons.append(f"Daily command limit reached ({p.max_commands_per_day}).")
        return d
    remaining = p.max_daily_runtime_s - i.runtime_24h_s
    if remaining < p.min_water_s:
        d.code = "daily_runtime_limit"
        d.reasons.append(f"Daily pump runtime budget exhausted ({i.runtime_24h_s}/{p.max_daily_runtime_s}s).")
        return d
    # 4. moisture vs profile with hysteresis ---------------------------------------------------
    if i.root >= band_top:
        d.code = "moisture_ok"
        d.reasons.append(f"Root-zone moisture {i.root:.1f}% is above the profile band ({i.low_pct:.0f}-{band_top:.0f}%).")
        return d
    below = i.root < i.low_pct
    if below:
        d.reasons.append(f"Root-zone moisture {i.root:.1f}% is below the profile minimum {i.low_pct:.0f}%.")
    else:
        d.reasons.append(f"Root-zone moisture {i.root:.1f}% is inside the hysteresis band ({i.low_pct:.0f}-{band_top:.0f}%).")
    # 5. trend --------------------------------------------------------------------------------
    trend_tip = False
    if i.trend_pct_per_hour is None:
        d.reasons.append("Moisture trend unavailable (not enough history); none assumed.")
    else:
        projected = i.root + i.trend_pct_per_hour * (p.trend_horizon_min / 60)
        d.reasons.append(f"Root moisture trend {i.trend_pct_per_hour:+.1f}%/h (projected {projected:.0f}% in {p.trend_horizon_min} min).")
        trend_tip = i.trend_pct_per_hour < 0 and projected < i.low_pct
    # 7/8. secondary evidence (ML unavailable; vision is only a tie-breaker) ------------------------
    ml_tip = i.ml_stress_probability is not None and i.ml_stress_probability >= 0.7
    if i.ml_stress_probability is None:
        d.reasons.append("ML stress predictor unavailable (no validated model); not used.")
    vision_tip = bool(i.vision_wilting) and (i.vision_confidence or 0) >= 0.7
    if vision_tip:
        d.reasons.append("Recent photo analysis suggests wilting (secondary evidence only).")
    if not below:
        if not (trend_tip and (ml_tip or vision_tip)):
            d.code = "within_hysteresis"
            d.reasons.append("Inside the hysteresis band without corroborating evidence; waiting.")
            return d
        d.reasons.append("Falling trend plus corroborating evidence justify pre-emptive watering.")
    # 6. weather ------------------------------------------------------------------------------
    if i.rain_probability is None:
        d.reasons.append("Weather forecast unavailable; no weather adjustment applied (not treated as 'no rain').")
    elif i.rain_probability >= p.rain_skip_probability:
        if i.root >= i.low_pct - p.rain_critical_margin_pct:
            d.code = "rain_expected"
            d.reasons.append(f"Rain probability {i.rain_probability * 100:.0f}% is high and moisture is not critical; waiting.")
            return d
        d.reasons.append("Rain is likely but moisture is critically low; watering anyway.")
    # 9/10/11. decide + bounded duration ---------------------------------------------------------
    deficit = max(0.0, band_top - i.root)
    seconds = round(p.min_water_s + deficit * p.seconds_per_deficit_pct)
    seconds = max(p.min_water_s, min(seconds, p.max_command_s, remaining))
    d.action, d.code, d.duration_s = "water", "water", int(seconds)
    d.reasons.append(f"Watering for {d.duration_s}s (bounded by the {p.max_command_s}s firmware limit and the daily budget).")
    return d


# ------------------------------------------------------------------------------ I/O wrapper
def params_from_settings() -> Params:
    return Params(cooldown_s=settings.irrigation_cooldown_minutes * 60, max_daily_runtime_s=settings.max_daily_runtime_seconds,
                  max_commands_per_day=settings.max_commands_per_day, hysteresis_pct=settings.hysteresis_pct,
                  rain_skip_probability=settings.rain_skip_probability, rain_critical_margin_pct=settings.rain_critical_margin_pct,
                  min_water_s=settings.min_water_seconds, seconds_per_deficit_pct=settings.seconds_per_deficit_pct,
                  max_age_s=settings.decision_max_age_s, trend_horizon_min=settings.trend_horizon_minutes)


def gather_inputs(plant_id: str, plant: dict, now: datetime) -> tuple[Inputs, dict, dict]:
    readings = latest_readings(plant_id)
    root, mid, surf = readings.get("soil_root"), readings.get("soil_mid"), readings.get("soil_surface")
    temp, hum = readings.get("temperature_c"), readings.get("humidity_pct")
    low = plant.get("ideal_moisture_min")
    high = plant.get("ideal_moisture_max")
    if low is None or high is None or low >= high:
        low, high = settings.root_moisture_threshold, 65.0
    weather = get_weather(plant_id)
    with db_session() as db:
        dev = db.execute("SELECT pump_status,pump_observed_at FROM device_status WHERE plant_id=?", (plant_id,)).fetchone()
        pending = db.execute("SELECT 1 FROM irrigation_events WHERE plant_id=? AND status IN ('published','queued','acknowledged','observed_watering','unconfirmed') "
                             "AND created_at>=?", (plant_id, (now - timedelta(hours=1)).isoformat())).fetchone()
        last = db.execute("SELECT created_at FROM irrigation_events WHERE plant_id=? AND source IN ('auto','manual') "
                          "AND status NOT IN ('failed_publish','not_sent','rejected') ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
        used_s, used_n = daily_usage(db, plant_id, now)
        vis = db.execute("SELECT vision_json,received_at FROM photos WHERE plant_id=? AND vision_json IS NOT NULL ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
    wilting = conf = None
    if vis:
        try:
            age_h = (now - datetime.fromisoformat(vis["received_at"])).total_seconds() / 3600
            v = json.loads(vis["vision_json"])
            if age_h <= 24:
                wilting, conf = v.get("wilting"), v.get("confidence")
        except Exception:
            pass
    pump_age = None
    if dev and dev["pump_observed_at"]:
        pump_age = (now - datetime.fromisoformat(dev["pump_observed_at"])).total_seconds()
    return Inputs(
        mode=plant["mode"], low_pct=float(low), target_pct=float(high),
        root=root["value"] if root else None, root_age_s=root["age_seconds"] if root else None,
        mid=mid["value"] if mid and mid["fresh"] else None, surface=surf["value"] if surf and surf["fresh"] else None,
        vpd_kpa=calculate_vpd(temp["value"] if temp and temp["fresh"] else None, hum["value"] if hum and hum["fresh"] else None),
        pump_status=dev["pump_status"] if dev else None, pump_status_age_s=pump_age, pending_command=bool(pending),
        seconds_since_last_command=(now - datetime.fromisoformat(last["created_at"])).total_seconds() if last else None,
        runtime_24h_s=used_s, commands_24h=used_n, trend_pct_per_hour=root_trend_pct_per_hour(plant_id),
        rain_probability=weather.get("rain_probability") if weather.get("available") else None,
        vision_wilting=wilting if isinstance(wilting, bool) else None, vision_confidence=conf if isinstance(conf, (int, float)) else None,
    ), weather, readings


def evaluate_plant(plant_id: str, execute: bool = False, requested_by: str = "engine"):
    now = datetime.now(timezone.utc)
    with db_session() as db:
        plant = db.execute("SELECT * FROM plants WHERE plant_id=?", (plant_id,)).fetchone()
    if not plant:
        return {"plant_id": plant_id, "decision": "skip", "reason": "Plant is not registered.", "readings": {}}
    device_state.sweep_unconfirmed(now)
    inputs, weather, readings = gather_inputs(plant_id, dict(plant), now)
    decision = decide(inputs, params_from_settings())
    event = None
    reasons = list(decision.reasons)
    executed = False
    if execute and decision.action == "water":
        try:
            event = request_watering(plant_id, decision.duration_s, "auto", requested_by, " ".join(reasons)[:280])
            executed = bool(event["published"])
            reasons.append(event["message"])
        except CommandRejected as exc:
            reasons.append(f"Command not sent: {exc.message}")
            decision.action = "skip"
            decision.code = exc.code
    with db_session() as db:
        db.execute("INSERT INTO decisions(plant_id,created_at,source,decision,reason,readings_json,vpd_kpa,weather_json,vision_json,command_id,engine_version,duration_s,executed,inputs_json) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (plant_id, now.isoformat(), "auto", decision.action, " ".join(reasons), json.dumps(readings), inputs.vpd_kpa,
                    json.dumps(weather), None, event["command_id"] if event else None, ENGINE_VERSION, decision.duration_s,
                    int(executed), json.dumps(asdict(inputs))))
    return {"plant_id": plant_id, "created_at": now.isoformat(), "decision": decision.action, "code": decision.code,
            "should_water": decision.action == "water", "duration_seconds": decision.duration_s, "executed": executed,
            "command_published": executed, "reason": " ".join(reasons), "reasons": reasons, "readings": readings,
            "vpd_kpa": inputs.vpd_kpa, "vpd_band": vpd_band(inputs.vpd_kpa), "weather": weather, "engine_version": ENGINE_VERSION}
