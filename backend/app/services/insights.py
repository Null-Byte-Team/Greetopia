"""Insights derived ONLY from data the hardware already sends (3 soil depths, air temp, humidity, pump status, photos).

Every result is labelled `derived`, carries its window and sample count, and returns `available: False` with a reason when
the minimum data rule is not met. Nothing here sends pump commands or changes safety limits; suggestions are advisory.
No flow, light, leaf-wetness or true water-volume data exists, so nothing here pretends to know them.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.config import settings
from app.db.database import db_session
from app.services import device_state
from app.services.vpd import calculate_vpd

MAX_GAP_S = 120          # a gap longer than this is "unknown", never filled with an invented value
MAX_POINTS = 120_000
HEAT_C, VPD_LOW, VPD_HIGH = 35.0, 0.4, 1.6   # documented configurable defaults, not agronomic universals
FUNGAL_RH, FUNGAL_T_MIN, FUNGAL_T_MAX = 85.0, 15.0, 28.0
SAT_PCT = 95.0
DEPTHS = {"surface": "soil_surface", "mid": "soil_mid", "root": "soil_root"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unavailable(reason: str, **extra) -> dict:
    return {"available": False, "reason": reason, "label": "derived", **extra}


# ------------------------------------------------------------------------------ data access
def series(plant_id: str, metric: str, since: datetime, until: datetime | None = None) -> list[tuple[datetime, float]]:
    q, args = "SELECT received_at,value FROM readings WHERE plant_id=? AND metric=? AND received_at>=?", [plant_id, metric, since.isoformat()]
    if until:
        q += " AND received_at<=?"
        args.append(until.isoformat())
    q += " ORDER BY received_at LIMIT ?"
    args.append(MAX_POINTS)
    with db_session() as db:
        rows = db.execute(q, args).fetchall()
    return [(datetime.fromisoformat(r["received_at"]), float(r["value"])) for r in rows]


def plant_profile(plant_id: str) -> dict:
    with db_session() as db:
        row = db.execute("SELECT ideal_moisture_min,ideal_moisture_max FROM plants WHERE plant_id=?", (plant_id,)).fetchone()
    low, high = (row["ideal_moisture_min"], row["ideal_moisture_max"]) if row else (None, None)
    if low is None or high is None or low >= high:
        low, high = settings.root_moisture_threshold, 65.0
    return {"low": float(low), "high": float(high)}


def confirmed_events(plant_id: str, since: datetime, limit: int = 200) -> list[dict]:
    with db_session() as db:
        rows = db.execute("SELECT * FROM irrigation_events WHERE plant_id=? AND status='confirmed' AND observed_start_at>=? "
                          "ORDER BY observed_start_at LIMIT ?", (plant_id, since.isoformat(), limit)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------------------ 3. stress-time KPIs
def kpis_from_points(points, low: float, high: float, max_gap_s: float = MAX_GAP_S) -> dict:
    """Time-weighted KPIs. A sample's value holds until the next sample, but never across a gap > max_gap_s."""
    if len(points) < 2:
        return _unavailable("fewer than 2 samples")
    covered = in_range = below = above = sat = 0.0
    stress_integral = 0.0  # percentage-points x hours below the profile minimum
    for (t0, v0), (t1, _) in zip(points, points[1:]):
        dt = (t1 - t0).total_seconds()
        if dt <= 0 or dt > max_gap_s:
            continue
        covered += dt
        if v0 < low:
            below += dt
            stress_integral += (low - v0) * dt / 3600
        elif v0 > high:
            above += dt
        else:
            in_range += dt
        if v0 >= SAT_PCT:
            sat += dt
    if covered < 3600:
        return _unavailable("less than 1 hour of continuous coverage", covered_hours=round(covered / 3600, 2))
    values = [v for _, v in points]
    q1, q3 = np.percentile(values, [25, 75])
    return {"available": True, "label": "derived", "covered_hours": round(covered / 3600, 2), "samples": len(points),
            "time_in_range_pct": round(100 * in_range / covered, 1), "below_min_hours": round(below / 3600, 2),
            "above_max_hours": round(above / 3600, 2), "saturation_hours": round(sat / 3600, 2),
            "stress_integral_pct_hours": round(stress_integral, 2), "std": round(float(np.std(values)), 2), "iqr": round(float(q3 - q1), 2),
            "profile_min": low, "profile_max": high}


def stress_kpis(plant_id: str, days: int = 7) -> dict:
    since = _now() - timedelta(days=days)
    prof = plant_profile(plant_id)
    per_depth = {name: kpis_from_points(series(plant_id, metric, since), prof["low"], prof["high"]) for name, metric in DEPTHS.items()}
    with db_session() as db:
        ev = db.execute("SELECT COUNT(*) n, COALESCE(SUM(duration_seconds),0) s FROM irrigation_events WHERE plant_id=? AND created_at>=? "
                        "AND source IN ('auto','manual') AND status NOT IN ('failed_publish','not_sent','rejected')", (plant_id, since.isoformat())).fetchone()
        obs = db.execute("SELECT observed_start_at a, observed_end_at b FROM irrigation_events WHERE plant_id=? AND status='confirmed' AND created_at>=?",
                         (plant_id, since.isoformat())).fetchall()
    observed_s = sum((datetime.fromisoformat(r["b"]) - datetime.fromisoformat(r["a"])).total_seconds() for r in obs if r["a"] and r["b"])
    return {"window_days": days, "label": "derived", "depths": per_depth,
            "irrigation": {"commands": ev["n"], "requested_seconds": ev["s"], "observed_seconds": round(observed_s, 1), "confirmed_events": len(obs),
                           "note": "Observed time comes from pump status transitions; there is no flow sensor, so no water volume is derived."}}


# ------------------------------------------------------------------------------ 1. irrigation response fingerprint
def response_for_event(start: datetime, depth_series: dict, pre_s: int = 300, post_s: int = 5400, rise: float = 2.0) -> dict:
    out = {}
    for depth, pts in depth_series.items():
        pre = [v for t, v in pts if start - timedelta(seconds=pre_s) <= t < start]
        post = [(t, v) for t, v in pts if start <= t <= start + timedelta(seconds=post_s)]
        if len(pre) < 2 or len(post) < 3:
            out[depth] = {"available": False, "reason": "not enough samples around the event"}
            continue
        base = statistics.median(pre)
        peak_t, peak_v = max(post, key=lambda p: p[1])
        first = [t for t, v in post if v >= base + rise]
        out[depth] = {"available": True, "baseline": round(base, 1), "gain": round(peak_v - base, 1), "responded": (peak_v - base) >= rise,
                      "delay_s": int((first[0] - start).total_seconds()) if first else None,
                      "time_to_peak_s": int((peak_t - start).total_seconds())}
    return out


def _med(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def response_fingerprint(plant_id: str, days: int = 30, min_events: int = 3) -> dict:
    since = _now() - timedelta(days=days)
    events = confirmed_events(plant_id, since)
    rows = []
    for ev in events:
        start = datetime.fromisoformat(ev["observed_start_at"])
        data = {d: series(plant_id, m, start - timedelta(seconds=300), start + timedelta(seconds=5400)) for d, m in DEPTHS.items()}
        rows.append({"event_id": ev["id"], "started_at": ev["observed_start_at"], "requested_seconds": ev["duration_seconds"],
                     "depths": response_for_event(start, data)})
    usable = [r for r in rows if all(r["depths"][d]["available"] for d in DEPTHS)]
    if len(usable) < min_events:
        return _unavailable(f"needs >= {min_events} confirmed watering events with full sensor coverage (found {len(usable)})", events=rows[-10:], window_days=days)
    agg, hypotheses = {}, []
    for d in DEPTHS:
        vals = [r["depths"][d] for r in usable]
        agg[d] = {"response_rate": round(sum(v["responded"] for v in vals) / len(vals), 2), "median_gain": _med([v["gain"] for v in vals]),
                  "median_delay_s": _med([v["delay_s"] for v in vals]), "median_time_to_peak_s": _med([v["time_to_peak_s"] for v in vals])}
    if all(agg[d]["response_rate"] == 0 for d in DEPTHS):
        hypotheses.append("No probe responded after watering. Possible causes: no water delivered (empty tank, clogged line, disconnected pump) or probes not in contact with soil.")
    elif agg["root"]["response_rate"] == 0 and agg["surface"]["response_rate"] > 0:
        hypotheses.append("The surface probe responds but the root probe does not: water may not be reaching the root zone (short runs, poor infiltration or hydrophobic soil).")
    if len(usable) >= 6:
        half = len(usable) // 2
        old, new = _med([r["depths"]["root"]["gain"] for r in usable[:half]]), _med([r["depths"]["root"]["gain"] for r in usable[half:]])
        if old and new is not None and old > 0 and new <= 0.5 * old:
            hypotheses.append(f"Root-zone gain per watering fell from {old} to {new} points: possible blockage, compaction or a drifting probe.")
    return {"available": True, "label": "derived", "window_days": days, "events_used": len(usable), "aggregate": agg,
            "hypotheses": hypotheses, "events": rows[-10:], "note": "Hypotheses are prompts for inspection, not diagnoses. Duration suggestions are never applied automatically."}


# ------------------------------------------------------------------------------ 4. microclimate
def microclimate(plant_id: str, days: int = 7) -> dict:
    since = _now() - timedelta(days=days)
    temp, hum = series(plant_id, "temperature_c", since), series(plant_id, "humidity_pct", since)
    surface = series(plant_id, "soil_surface", since)
    if len(temp) < 100 or len(hum) < 100:
        return _unavailable("needs >= 100 temperature and humidity samples", temperature_samples=len(temp), humidity_samples=len(hum))
    t_times = [t for t, _ in temp]
    import bisect
    covered = heat = vpd_low = vpd_high = fungal = 0.0
    by_hour: dict[int, list[float]] = {h: [] for h in range(24)}
    for (t0, rh), (t1, _) in zip(hum, hum[1:]):
        dt = (t1 - t0).total_seconds()
        if dt <= 0 or dt > MAX_GAP_S:
            continue
        i = bisect.bisect_right(t_times, t0) - 1
        if i < 0 or (t0 - t_times[i]).total_seconds() > MAX_GAP_S:
            continue
        tc = temp[i][1]
        vpd = calculate_vpd(tc, rh)
        covered += dt
        if tc > HEAT_C:
            heat += dt
        if vpd is not None:
            by_hour[t0.hour].append(vpd)
            if vpd < VPD_LOW:
                vpd_low += dt
            elif vpd > VPD_HIGH:
                vpd_high += dt
        if rh >= FUNGAL_RH and FUNGAL_T_MIN <= tc <= FUNGAL_T_MAX:
            fungal += dt
    if covered < 3600:
        return _unavailable("less than 1 hour of paired temperature/humidity coverage")
    return {"available": True, "label": "derived", "window_days": days, "covered_hours": round(covered / 3600, 2),
            "heat_stress_hours": round(heat / 3600, 2), "low_vpd_hours": round(vpd_low / 3600, 2), "high_vpd_hours": round(vpd_high / 3600, 2),
            "fungal_risk_hours": round(fungal / 3600, 2), "fungal_risk_index": round(100 * fungal / covered, 1),
            "vpd_mean_by_utc_hour": {h: (round(float(np.mean(v)), 2) if v else None) for h, v in by_hour.items()},
            "thresholds": {"heat_c": HEAT_C, "vpd_low": VPD_LOW, "vpd_high": VPD_HIGH, "fungal_rh": FUNGAL_RH, "fungal_temp_range": [FUNGAL_T_MIN, FUNGAL_T_MAX]},
            "note": "Risk indicator from configurable default thresholds, not a disease diagnosis. Leaf wetness is not measured."}


# ------------------------------------------------------------------------------ 5. telemetry integrity & connectivity
def probe_health(points, hours: float, other_ranges: list[float]) -> dict:
    if len(points) < 50:
        return _unavailable("fewer than 50 samples", samples=len(points))
    values = [v for _, v in points]
    diffs = [abs(b - a) for a, b in zip(values, values[1:])]
    spikes = sum(d >= 25 for d in diffs)
    noise = statistics.median(diffs) if diffs else 0.0
    expected = max(1.0, hours * 360)
    coverage = min(1.0, len(points) / expected)
    rng = max(values) - min(values)
    stuck = len(points) >= 200 and rng == 0 and any(r >= 2 for r in other_ranges)
    score = 100 - (40 if stuck else 0) - min(30, spikes * 5) - min(20, noise * 4) - (1 - coverage) * 30
    reasons = []
    if stuck:
        reasons.append("value never changed while other probes did (possibly frozen/disconnected)")
    if spikes:
        reasons.append(f"{spikes} implausible jumps of >= 25 points between consecutive samples")
    if coverage < 0.8:
        reasons.append(f"only {round(coverage * 100)}% of the expected samples arrived")
    return {"available": True, "label": "derived", "samples": len(points), "score": int(max(0, min(100, round(score)))), "stuck": stuck,
            "spikes": spikes, "median_step": round(noise, 2), "coverage": round(coverage, 2), "reasons": reasons}


def connectivity(points) -> dict:
    if len(points) < 20:
        return _unavailable("fewer than 20 samples")
    gaps = [(b - a).total_seconds() for (a, _), (b, _) in zip(points, points[1:])]
    p95 = float(np.percentile(gaps, 95))
    long_gaps = sum(g > MAX_GAP_S for g in gaps)
    score = 100 - min(60, long_gaps * 6) - min(30, max(0.0, p95 - 15))
    return {"available": True, "label": "derived", "median_interval_s": round(statistics.median(gaps), 1), "p95_interval_s": round(p95, 1),
            "gaps_over_120s": long_gaps, "score": int(max(0, round(score)))}


def integrity(plant_id: str, hours: int = 24) -> dict:
    since = _now() - timedelta(hours=hours)
    data = {d: series(plant_id, m, since) for d, m in DEPTHS.items()}
    ranges = {d: (max(v for _, v in p) - min(v for _, v in p)) if p else 0 for d, p in data.items()}
    probes = {d: probe_health(p, hours, [r for k, r in ranges.items() if k != d]) for d, p in data.items()}
    from app.services.decision_engine import Inputs, sensor_suspect
    from app.services.telemetry import latest_readings
    latest = latest_readings(plant_id)
    suspect = sensor_suspect(Inputs(root=latest.get("soil_root", {}).get("value"), mid=latest.get("soil_mid", {}).get("value"), surface=latest.get("soil_surface", {}).get("value")))
    return {"window_hours": hours, "label": "derived", "probes": probes, "connectivity": connectivity(data["root"]),
            "suspect_now": suspect, "device": device_state.device_summary(plant_id),
            "note": "Calibration is only ever suggested, never applied automatically; unhealthy probes are excluded from decisions only through an explicit logged rule."}


# ------------------------------------------------------------------------------ 6. pump / actuation health
def pump_health(plant_id: str, days: int = 30) -> dict:
    since = _now() - timedelta(days=days)
    with db_session() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM irrigation_events WHERE plant_id=? AND created_at>=? AND source IN ('auto','manual') ORDER BY id", (plant_id, since.isoformat())).fetchall()]
    sent = [r for r in rows if r["status"] not in ("failed_publish", "not_sent", "rejected")]
    if len(sent) < 3:
        return _unavailable(f"needs >= 3 sent commands (found {len(sent)})", commands=len(sent))
    confirmed = [r for r in sent if r["status"] == "confirmed" and r["observed_start_at"] and r["observed_end_at"]]
    ratios = [((datetime.fromisoformat(r["observed_end_at"]) - datetime.fromisoformat(r["observed_start_at"])).total_seconds() / r["duration_seconds"]) for r in confirmed if r["duration_seconds"]]
    unconfirmed = sum(r["status"] in ("unconfirmed", "unconfirmed_end") for r in sent)
    fp = response_fingerprint(plant_id, days, min_events=3)
    streak = 0
    if fp.get("available") or fp.get("events"):
        for r in reversed(fp.get("events", [])):
            d = r["depths"]
            if all(d[k].get("available") for k in ("root", "surface")) and not d["root"]["responded"] and not d["surface"]["responded"]:
                streak += 1
            else:
                break
    flags = []
    if unconfirmed / len(sent) >= 0.3:
        flags.append("many commands were never confirmed by the device (connectivity or node problem)")
    if ratios and not 0.6 <= statistics.median(ratios) <= 1.4:
        flags.append("observed pump time differs strongly from the requested time")
    if streak >= 3:
        flags.append("repeated waterings produced no moisture response at any probe: possible empty tank, clogged line or disconnected pump")
    efficiency = None
    if settings.flow_ml_per_second and fp.get("available") and fp["aggregate"]["root"]["median_gain"] is not None and confirmed:
        ml = statistics.median([r["duration_seconds"] * settings.flow_ml_per_second for r in confirmed])
        efficiency = {"root_gain_points_per_100ml": round(100 * fp["aggregate"]["root"]["median_gain"] / ml, 2), "label": "estimated",
                      "note": "Uses the configured flow rate, not a measured volume."}
    return {"available": True, "label": "derived", "window_days": days, "commands": len(sent), "confirmed": len(confirmed), "unconfirmed": unconfirmed,
            "median_observed_to_requested": round(statistics.median(ratios), 2) if ratios else None, "no_response_streak": streak,
            "flags": flags, "efficiency": efficiency}


# ------------------------------------------------------------------------------ 2. water-demand model
def fit_demand(pairs: list[tuple[float, float, float]]) -> dict:
    """pairs = (vpd, delta_root_per_hour, time_index). Chronological 70/30 split; hidden unless better than baselines."""
    if len(pairs) < 48:
        return _unavailable(f"needs >= 48 dry-down hours (found {len(pairs)})")
    pairs = sorted(pairs, key=lambda p: p[2])
    cut = int(len(pairs) * 0.7)
    tr, te = pairs[:cut], pairs[cut:]
    x, y = np.array([p[0] for p in tr]), np.array([p[1] for p in tr])
    if np.ptp(x) < 0.3:
        return _unavailable("VPD range in the data is too narrow (< 0.3 kPa) to estimate demand")
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res, ss_tot = float(np.sum((y - pred) ** 2)), float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    xt, yt = np.array([p[0] for p in te]), np.array([p[1] for p in te])
    mae_model = float(np.mean(np.abs(yt - (a + b * xt))))
    mae_mean = float(np.mean(np.abs(yt - y.mean())))
    mae_persist = float(np.mean(np.abs(yt)))
    sigma = float(np.sqrt(ss_res / max(1, len(tr) - 2)))
    ok = b < 0 and r2 >= 0.2 and mae_model < min(mae_mean, mae_persist)
    return {"available": ok, "label": "derived", "n_train": len(tr), "n_test": len(te), "slope_per_kpa": round(float(b), 3), "intercept": round(float(a), 3),
            "r2_train": round(r2, 3), "mae_model": round(mae_model, 3), "mae_baseline_mean": round(mae_mean, 3), "mae_baseline_persistence": round(mae_persist, 3),
            "sigma": round(sigma, 3), "reason": None if ok else "model does not beat the baselines on held-out hours; forecast hidden", "_a": a, "_b": b}


def demand_model(plant_id: str, days: int = 14) -> dict:
    since = _now() - timedelta(days=days)
    root, temp, hum = series(plant_id, "soil_root", since), series(plant_id, "temperature_c", since), series(plant_id, "humidity_pct", since)
    if len(root) < 500 or len(temp) < 500 or len(hum) < 500:
        return _unavailable("needs several days of root, temperature and humidity data")

    def hourly(pts):
        buckets: dict[datetime, list[float]] = {}
        for t, v in pts:
            buckets.setdefault(t.replace(minute=0, second=0, microsecond=0), []).append(v)
        return {h: float(np.mean(v)) for h, v in buckets.items() if len(v) >= 120}  # >= 20 min of a 10 s stream

    r_h, t_h, h_h = hourly(root), hourly(temp), hourly(hum)
    wet_hours = set()
    for ev in confirmed_events(plant_id, since):
        s = datetime.fromisoformat(ev["observed_start_at"]).replace(minute=0, second=0, microsecond=0)
        wet_hours.update({s - timedelta(hours=1), s, s + timedelta(hours=1), s + timedelta(hours=2)})
    pairs = []
    for h, v in sorted(r_h.items()):
        nxt = h + timedelta(hours=1)
        if nxt not in r_h or h in wet_hours or nxt in wet_hours or h not in t_h or h not in h_h:
            continue
        delta = r_h[nxt] - v
        vpd = calculate_vpd(t_h[h], h_h[h])
        if vpd is not None and delta <= 0.3:  # dry-down only; rises not caused by logged watering are excluded, not explained away
            pairs.append((vpd, delta, h.timestamp()))
    fit = fit_demand(pairs)
    prof = plant_profile(plant_id)
    out = {k: v for k, v in fit.items() if not k.startswith("_")}
    out["window_days"] = days
    if not fit["available"]:
        return out
    last_h = sorted(h_h)[-3:]
    recent_vpd = [calculate_vpd(t_h[h], h_h[h]) for h in last_h if h in t_h]
    recent_vpd = [v for v in recent_vpd if v is not None]
    cur = root[-1][1]
    if not recent_vpd:
        out["forecast"] = _unavailable("no recent temperature/humidity data")
        return out
    slope = fit["_a"] + fit["_b"] * float(np.mean(recent_vpd))
    if slope >= -0.01:
        out["forecast"] = _unavailable("predicted dry-down rate is ~0 under current conditions")
        return out
    hours = (cur - prof["low"]) / -slope
    lo_s, hi_s = slope - 1.96 * fit["sigma"], slope + 1.96 * fit["sigma"]
    out["forecast"] = {"available": True, "label": "derived", "root_now": round(cur, 1), "profile_min": prof["low"], "hours_to_min": round(max(0.0, hours), 1),
                       "hours_range_95": [round(max(0.0, (cur - prof["low"]) / -lo_s), 1), (round((cur - prof["low"]) / -hi_s, 1) if hi_s < -0.01 else None)],
                       "note": "Advisory forecast. It can corroborate the controller but never triggers watering by itself."}
    return out


# ------------------------------------------------------------------------------ alerts + weekly report
def run_alert_rules(plant_id: str) -> int:
    n = 0
    k = stress_kpis(plant_id, days=1)["depths"]["root"]
    with db_session() as db:
        if k.get("available") and k["saturation_hours"] >= 6:
            device_state.add_alert(db, plant_id, "sustained_saturation", f"Root zone >= {SAT_PCT:.0f}% for {k['saturation_hours']} h in the last 24 h (waterlogging risk).")
            n += 1
        if k.get("available") and k["below_min_hours"] >= 6:
            device_state.add_alert(db, plant_id, "sustained_dry", f"Root moisture below the plant's minimum for {k['below_min_hours']} h in the last 24 h.")
            n += 1
    ph = pump_health(plant_id)
    with db_session() as db:
        if ph.get("available") and ph["no_response_streak"] >= 3:
            device_state.add_alert(db, plant_id, "pump_no_response", "Repeated waterings produced no moisture response (possible empty tank, clogged line or disconnected pump).", "critical")
            n += 1
    ig = integrity(plant_id)
    with db_session() as db:
        for depth, p in ig["probes"].items():
            if p.get("available") and p["score"] < 50:
                device_state.add_alert(db, plant_id, f"probe_unhealthy_{depth}", f"The {depth} probe health score is {p['score']}/100: {'; '.join(p['reasons']) or 'low score'}.")
                n += 1
    return n


_T = {
    "en": {"title": "Weekly report", "no_data": "Not enough recorded data for this section yet.",
           "range": "Root zone stayed inside the target band {pct}% of the time ({covered} h of continuous data).",
           "stress": "Time below the minimum: {h} h; stress integral {s} point-hours.",
           "events": "{n} watering commands sent, {c} confirmed by the device, {u} unconfirmed.",
           "micro": "Heat-stress hours: {heat}; high-VPD hours: {vh}; fungal-risk index: {fi}/100 (indicator only).",
           "health": "Probe health (surface/mid/root): {s}/{m}/{r}; connectivity score: {c}.",
           "foot": "Numbers are derived from recorded sensor data; water volume is not measured."},
    "ar": {"title": "التقرير الأسبوعي", "no_data": "لا توجد بيانات مسجّلة كافية لهذا القسم بعد.",
           "range": "بقيت منطقة الجذور داخل النطاق المستهدف {pct}% من الوقت ({covered} ساعة بيانات متصلة).",
           "stress": "الوقت تحت الحد الأدنى: {h} ساعة؛ تكامل الإجهاد {s} نقطة-ساعة.",
           "events": "تم إرسال {n} أمر ري، أكّد الجهاز {c} منها، و{u} غير مؤكدة.",
           "micro": "ساعات الإجهاد الحراري: {heat}؛ ساعات VPD المرتفع: {vh}؛ مؤشر خطر الفطريات: {fi}/100 (مؤشر فقط).",
           "health": "صحة الحساسات (سطح/وسط/جذر): {s}/{m}/{r}؛ درجة الاتصال: {c}.",
           "foot": "الأرقام مشتقة من بيانات الحساسات المسجّلة؛ حجم المياه غير مقيس."},
}


def weekly_report(plant_id: str, lang: str = "en") -> dict:
    t = _T["ar" if lang == "ar" else "en"]
    kp, mc, ig = stress_kpis(plant_id, 7), microclimate(plant_id, 7), integrity(plant_id, 24)
    root, lines = kp["depths"]["root"], []
    if root.get("available"):
        lines.append(t["range"].format(pct=root["time_in_range_pct"], covered=root["covered_hours"]))
        lines.append(t["stress"].format(h=root["below_min_hours"], s=root["stress_integral_pct_hours"]))
    else:
        lines.append(t["no_data"])
    ir = kp["irrigation"]
    with db_session() as db:
        uc = db.execute("SELECT COUNT(*) c FROM irrigation_events WHERE plant_id=? AND status IN ('unconfirmed','unconfirmed_end') AND created_at>=?", (plant_id, (_now() - timedelta(days=7)).isoformat())).fetchone()["c"]
    lines.append(t["events"].format(n=ir["commands"], c=ir["confirmed_events"], u=uc))
    lines.append(t["micro"].format(heat=mc["heat_stress_hours"], vh=mc["high_vpd_hours"], fi=mc["fungal_risk_index"]) if mc.get("available") else t["no_data"])
    sc = lambda d: ig["probes"][d].get("score", "-")
    lines.append(t["health"].format(s=sc("surface"), m=sc("mid"), r=sc("root"), c=ig["connectivity"].get("score", "-")))
    lines.append(t["foot"])
    return {"title": t["title"], "lang": "ar" if lang == "ar" else "en", "generated_at": _now().isoformat(), "lines": lines, "label": "derived",
            "source": "deterministic templates over stored data; no LLM"}


def summary(plant_id: str, days: int = 7) -> dict:
    return {"plant_id": plant_id, "kpis": stress_kpis(plant_id, days), "response": response_fingerprint(plant_id, max(days, 14)),
            "microclimate": microclimate(plant_id, days), "integrity": integrity(plant_id, 24), "pump_health": pump_health(plant_id, max(days, 14)),
            "demand": demand_model(plant_id, max(days, 14))}
