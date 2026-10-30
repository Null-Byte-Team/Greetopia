"""Randomised A/B experiment engine.

An experiment assigns N plants to arms (adaptive controller vs a documented fixed-schedule or fixed-threshold control) with a
stored random seed, snapshots the configuration, and later computes per-plant metrics ONLY from recorded data. The unit of
analysis is the plant (one value per plant per metric), so n = number of plants per arm. With small n the report says so and
withholds p-values instead of presenting weak evidence as proof. Simulated experiments are labelled everywhere.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import zipfile
from datetime import datetime, timezone

import numpy as np

from app.core.config import settings
from app.db.database import db_session
from app.services import insights
from app.services.stats import bootstrap_median_diff, mann_whitney

ARMS = ("adaptive", "fixed_threshold", "fixed_schedule")
METRICS = {  # metric -> (label, lower is better?)
    "requested_seconds": ("Total requested pump time (s)", True),
    "observed_seconds": ("Total observed pump time (s)", True),
    "water_ml": ("Water used (ml, measured if available, else estimated)", True),
    "commands": ("Number of irrigation commands", None),
    "time_below_target_pct": ("Time root moisture below target (%)", True),
    "stress_integral_pct_hours": ("Stress integral (points x hours below target)", True),
    "root_moisture_std": ("Root moisture std (stability)", True),
    "green_fraction_change_per_day": ("Green-area proxy change per day (growth proxy)", False),
}
DEFAULT_PARAMS = {"fixed_schedule": {"interval_hours": 12, "seconds": 8}, "fixed_threshold": {"threshold_pct": 35.0, "seconds": 8}, "adaptive": {}}


class ExperimentError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "exp"
    return f"{base}-{_now().strftime('%Y%m%d%H%M%S')}"


def assign_arms(plant_ids: list[str], arms: list[str], seed: int) -> dict[str, str]:
    """Seeded shuffle, then round-robin over the arms => balanced groups (sizes differ by at most one)."""
    order = sorted(plant_ids)
    random.Random(seed).shuffle(order)
    return {pid: arms[i % len(arms)] for i, pid in enumerate(order)}


def create(name, hypothesis, plant_ids, arms, seed, data_origin, created_by, params=None, analysis_plan="", primary_metrics=None):
    if len(set(plant_ids)) != len(plant_ids) or len(plant_ids) < 2:
        raise ExperimentError("Provide at least 2 distinct plants")
    if "adaptive" not in arms or len(set(arms)) < 2 or any(a not in ARMS for a in arms):
        raise ExperimentError("Arms must include 'adaptive' and at least one control arm")
    metrics = primary_metrics or ["water_ml", "time_below_target_pct", "green_fraction_change_per_day"]
    if any(m not in METRICS for m in metrics):
        raise ExperimentError("Unknown primary metric")
    assignment = assign_arms(plant_ids, arms, seed)
    key = _key(name)
    with db_session() as db:
        for pid in plant_ids:
            if not db.execute("SELECT 1 FROM plants WHERE plant_id=?", (pid,)).fetchone():
                raise ExperimentError(f"Unknown plant {pid}")
        cur = db.execute("INSERT INTO experiments(key,name,hypothesis,primary_metrics_json,analysis_plan,seed,data_origin,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         (key, name.strip(), hypothesis.strip(), json.dumps(metrics), analysis_plan, seed, data_origin, created_by, _now().isoformat()))
        for pid, arm in assignment.items():
            p = {**DEFAULT_PARAMS[arm], **(params or {}).get(arm, {})}
            db.execute("INSERT INTO experiment_runs(experiment_id,plant_id,arm,params_json) VALUES(?,?,?,?)", (cur.lastrowid, pid, arm, json.dumps(p)))
    return get(key)


def get(key: str) -> dict:
    with db_session() as db:
        e = db.execute("SELECT * FROM experiments WHERE key=?", (key,)).fetchone()
        if not e:
            raise ExperimentError("Experiment not found")
        runs = db.execute("SELECT * FROM experiment_runs WHERE experiment_id=? ORDER BY plant_id", (e["id"],)).fetchall()
    out = dict(e)
    out["primary_metrics"] = json.loads(out.pop("primary_metrics_json"))
    out["config_snapshot"] = json.loads(out.pop("config_snapshot_json") or "null")
    out["runs"] = [{"plant_id": r["plant_id"], "arm": r["arm"], "params": json.loads(r["params_json"]), "profile_snapshot": json.loads(r["profile_snapshot_json"] or "null")} for r in runs]
    return out


def list_all() -> list[dict]:
    with db_session() as db:
        rows = db.execute("SELECT key,name,status,data_origin,created_at,started_at,ended_at FROM experiments ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def start(key: str) -> dict:
    exp = get(key)
    if exp["status"] != "draft":
        raise ExperimentError("Only a draft experiment can be started")
    with db_session() as db:
        for r in exp["runs"]:
            busy = db.execute("SELECT e.key FROM experiment_runs r JOIN experiments e ON e.id=r.experiment_id WHERE r.plant_id=? AND e.status='running'", (r["plant_id"],)).fetchone()
            if busy:
                raise ExperimentError(f"Plant {r['plant_id']} is already in running experiment {busy['key']}")
        snap = {"settings": {k: getattr(settings, k) for k in ("irrigation_cooldown_minutes", "max_daily_runtime_seconds", "max_commands_per_day", "hysteresis_pct",
                                                                  "rain_skip_probability", "min_water_seconds", "seconds_per_deficit_pct", "flow_ml_per_second",
                                                                  "decision_max_age_s", "auto_decisions_enabled")},
                "engine_version": __import__("app.services.decision_engine", fromlist=["ENGINE_VERSION"]).ENGINE_VERSION}
        e = db.execute("SELECT id FROM experiments WHERE key=?", (key,)).fetchone()
        for r in exp["runs"]:
            prof = insights.plant_profile(r["plant_id"])
            db.execute("UPDATE experiment_runs SET profile_snapshot_json=? WHERE experiment_id=? AND plant_id=?", (json.dumps(prof), e["id"], r["plant_id"]))
        db.execute("UPDATE experiments SET status='running',started_at=?,config_snapshot_json=? WHERE key=?", (_now().isoformat(), json.dumps(snap), key))
    return get(key)


def stop(key: str) -> dict:
    exp = get(key)
    if exp["status"] != "running":
        raise ExperimentError("Only a running experiment can be stopped")
    with db_session() as db:
        db.execute("UPDATE experiments SET status='finished',ended_at=? WHERE key=?", (_now().isoformat(), key))
    return get(key)


# ------------------------------------------------------------------------------ active arm (used by the controller loop)
def active_run(plant_id: str) -> dict | None:
    with db_session() as db:
        r = db.execute("SELECT e.key,e.started_at,r.arm,r.params_json FROM experiment_runs r JOIN experiments e ON e.id=r.experiment_id WHERE r.plant_id=? AND e.status='running'", (plant_id,)).fetchone()
    return {"key": r["key"], "started_at": r["started_at"], "arm": r["arm"], "params": json.loads(r["params_json"])} if r else None


# ------------------------------------------------------------------------------ per-plant metrics (recorded data only)
def run_metrics(plant_id: str, start_at: datetime, end_at: datetime, low: float, high: float) -> dict:
    root = insights.series(plant_id, "soil_root", start_at, end_at)
    kp = insights.kpis_from_points(root, low, high)
    with db_session() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM irrigation_events WHERE plant_id=? AND created_at>=? AND created_at<=? AND source IN ('auto','manual') "
                                            "AND status NOT IN ('failed_publish','not_sent','rejected')", (plant_id, start_at.isoformat(), end_at.isoformat())).fetchall()]
    observed = sum((datetime.fromisoformat(r["observed_end_at"]) - datetime.fromisoformat(r["observed_start_at"])).total_seconds()
                   for r in rows if r["observed_start_at"] and r["observed_end_at"])
    measured = [r["measured_water_ml"] for r in rows if r["measured_water_ml"] is not None]
    if rows and len(measured) == len(rows):
        water, basis = float(sum(measured)), "measured"
    elif rows and settings.flow_ml_per_second:
        water, basis = float(sum(r["duration_seconds"] for r in rows) * settings.flow_ml_per_second), "estimated"
    else:
        water, basis = None, "unavailable"
    growth = growth_proxy(plant_id, start_at, end_at)
    m = {"commands": len(rows), "requested_seconds": sum(r["duration_seconds"] or 0 for r in rows), "observed_seconds": round(observed, 1),
         "water_ml": None if water is None else round(water, 1), "water_basis": basis,
         "time_below_target_pct": round(100 * kp["below_min_hours"] / kp["covered_hours"], 2) if kp.get("available") else None,
         "stress_integral_pct_hours": kp.get("stress_integral_pct_hours"), "root_moisture_std": kp.get("std"),
         "covered_hours": kp.get("covered_hours"), "green_fraction_change_per_day": growth}
    return m


def growth_proxy(plant_id: str, start_at: datetime, end_at: datetime, min_photos: int = 10):
    """Slope (per day) of the green-area proxy from camera photos; None unless enough photos span >= 2 days."""
    with db_session() as db:
        rows = db.execute("SELECT received_at,green_fraction FROM photo_metrics WHERE plant_id=? AND received_at>=? AND received_at<=? ORDER BY received_at",
                          (plant_id, start_at.isoformat(), end_at.isoformat())).fetchall()
    if len(rows) < min_photos:
        return None
    t0 = datetime.fromisoformat(rows[0]["received_at"])
    xs = np.array([(datetime.fromisoformat(r["received_at"]) - t0).total_seconds() / 86400 for r in rows])
    if xs[-1] < 2:
        return None
    return round(float(np.polyfit(xs, [r["green_fraction"] for r in rows], 1)[0]), 5)


def results(key: str) -> dict:
    exp = get(key)
    if not exp["started_at"]:
        raise ExperimentError("Experiment has not started")
    start_at = datetime.fromisoformat(exp["started_at"])
    end_at = datetime.fromisoformat(exp["ended_at"]) if exp["ended_at"] else _now()
    per_plant = []
    for r in exp["runs"]:
        prof = r["profile_snapshot"] or insights.plant_profile(r["plant_id"])
        per_plant.append({"plant_id": r["plant_id"], "arm": r["arm"], "metrics": run_metrics(r["plant_id"], start_at, end_at, prof["low"], prof["high"])})
    by_arm: dict[str, list] = {}
    for p in per_plant:
        by_arm.setdefault(p["arm"], []).append(p)
    comparisons = []
    for metric in exp["primary_metrics"]:
        base = [p["metrics"][metric] for p in by_arm.get("adaptive", []) if p["metrics"][metric] is not None]
        for arm, plants in by_arm.items():
            if arm == "adaptive":
                continue
            other = [p["metrics"][metric] for p in plants if p["metrics"][metric] is not None]
            comparisons.append({"metric": metric, "label": METRICS[metric][0], "adaptive_vs": arm, "adaptive_values": base, "control_values": other,
                                "test": mann_whitney(base, other), "bootstrap": bootstrap_median_diff(base, other, exp["seed"])})
    return {"experiment": {k: exp[k] for k in ("key", "name", "hypothesis", "status", "data_origin", "seed", "started_at", "ended_at", "analysis_plan", "primary_metrics", "config_snapshot")},
            "window": {"start": start_at.isoformat(), "end": end_at.isoformat()}, "per_plant": per_plant, "comparisons": comparisons,
            "arms": {a: [p["plant_id"] for p in v] for a, v in by_arm.items()},
            "label": "SIMULATED" if exp["data_origin"] == "simulated" else "EXPERIMENTAL"}


# ------------------------------------------------------------------------------ report + export
def report_markdown(key: str) -> str:
    r = results(key)
    e = r["experiment"]
    banner = "> **SIMULATED DATA. Not evidence about real plants.**\n\n" if r["label"] == "SIMULATED" else ""
    lines = [f"# {e['name']}", "", banner + f"*Data origin: {r['label']}. Generated {_now().isoformat()}.*", "", "## Hypothesis", e["hypothesis"], "",
             "## Pre-registered analysis plan", e["analysis_plan"] or "(none recorded)", "",
             "## Design", f"- Experiment key: `{e['key']}`; random seed: {e['seed']}; window: {r['window']['start']} to {r['window']['end']}",
             f"- Unit of analysis: the plant. Arms: " + "; ".join(f"{a}: {', '.join(p)}" for a, p in r["arms"].items()),
             "- Configuration snapshot is stored with the experiment (see experiment.json).", "", "## Per-plant results",
             "| Plant | Arm | " + " | ".join(m for m in e["primary_metrics"]) + " |", "|---|---|" + "---|" * len(e["primary_metrics"])]
    for p in r["per_plant"]:
        lines.append(f"| {p['plant_id']} | {p['arm']} | " + " | ".join("n/a" if p["metrics"][m] is None else str(p["metrics"][m]) for m in e["primary_metrics"]) + " |")
    lines += ["", "## Adaptive vs control (Mann-Whitney U, rank-biserial effect size, bootstrap 95% CI of the median difference)"]
    for c in r["comparisons"]:
        t, b = c["test"], c["bootstrap"]
        p = "not reported" if t["p_value"] is None else f"{t['p_value']} ({t['method']})"
        ci = f"{b['median_diff']} [{b['ci95'][0]}, {b['ci95'][1]}]" if b.get("available") else "n/a"
        lines.append(f"- **{c['label']}**, adaptive vs {c['adaptive_vs']}: n = {t['n1']} vs {t['n2']}; p = {p}; effect = {t['rank_biserial']}; median difference {ci}." + (f" *{t['note']}*" if t.get("note") else ""))
    lines += ["", "## Limitations (read before drawing conclusions)",
              "- Plants are the unit of analysis; a small number of plants gives low power and wide intervals.",
              "- Water volume is *measured* only when a flow sensor recorded it; otherwise it is *estimated* from a configured pump flow rate, or unavailable.",
              "- Growth is a camera-based green-area proxy, not biomass. Lighting and camera position must be constant.",
              "- Environmental differences between plant positions are not controlled by the software.",
              "- No claim of water saving, growth improvement or accuracy is made beyond what the tables above show."]
    return "\n".join(lines) + "\n"


def export_zip(key: str) -> bytes:
    r = results(key)
    start_at, end_at = datetime.fromisoformat(r["window"]["start"]), datetime.fromisoformat(r["window"]["end"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.md", report_markdown(key))
        z.writestr("experiment.json", json.dumps({**r, "exported_at": _now().isoformat()}, indent=2, default=str))
        rows = io.StringIO()
        w = csv.writer(rows)
        cols = list(METRICS) + ["water_basis", "covered_hours"]
        w.writerow(["data_origin", "plant_id", "arm"] + cols)
        for p in r["per_plant"]:
            w.writerow([r["label"].lower(), p["plant_id"], p["arm"]] + [p["metrics"].get(c) for c in cols])
        z.writestr("per_plant_metrics.csv", rows.getvalue())
        for p in r["per_plant"]:
            raw = io.StringIO()
            rw = csv.writer(raw)
            rw.writerow(["data_origin", "plant_id", "arm", "metric", "received_at_utc", "value"])
            for metric in ("soil_surface", "soil_mid", "soil_root", "temperature_c", "humidity_pct"):
                for t, v in insights.series(p["plant_id"], metric, start_at, end_at):
                    rw.writerow([r["label"].lower(), p["plant_id"], p["arm"], metric, t.isoformat(), v])
            z.writestr(f"raw/{p['plant_id']}_{p['arm']}.csv", raw.getvalue())
        with db_session() as db:
            ev = db.execute("SELECT * FROM irrigation_events WHERE created_at>=? AND created_at<=? AND plant_id IN (%s) ORDER BY id" % ",".join("?" * len(r["per_plant"])),
                            [start_at.isoformat(), end_at.isoformat()] + [p["plant_id"] for p in r["per_plant"]]).fetchall()
        eo = io.StringIO()
        ew = csv.writer(eo)
        if ev:
            ew.writerow(ev[0].keys())
            for row in ev:
                ew.writerow(list(row))
        z.writestr("irrigation_events.csv", eo.getvalue())
    return buf.getvalue()
