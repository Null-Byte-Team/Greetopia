"""Synthetic data only to exercise the code paths; never presented as results."""
import io
import random
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.database import db_session
from app.services import controllers, experiments, irrigation
from app.services.stats import bootstrap_median_diff, mann_whitney
from tests.conftest import _signup, make_jpeg


def add_plants(*ids):
    with db_session() as db:
        for i in ids:
            db.execute("INSERT OR IGNORE INTO plants(plant_id,name,species,growth_stage,created_at,ideal_moisture_min,ideal_moisture_max) VALUES(?,?,?,?,?,?,?)",
                       (i, i, "x", "x", datetime.now(timezone.utc).isoformat(), 35, 65))


# ---------------- statistics
def test_mann_whitney_exact_matches_scipy():
    scipy_stats = pytest.importorskip("scipy.stats")
    x, y = [1.1, 2.3, 3.7, 4.2, 9.9], [5.5, 6.1, 7.7, 8.2, 12.3]
    ours = mann_whitney(x, y)
    ref = scipy_stats.mannwhitneyu(x, y, alternative="two-sided", method="exact")
    assert ours["method"] == "exact permutation" and abs(ours["p_value"] - ref.pvalue) < 1e-3 and ours["u"] == ref.statistic


def test_mann_whitney_normal_approx_close_to_scipy_with_ties():
    scipy_stats = pytest.importorskip("scipy.stats")
    rnd = random.Random(3)
    x = [round(rnd.gauss(10, 2)) for _ in range(20)]
    y = [round(rnd.gauss(12, 2)) for _ in range(20)]
    ours = mann_whitney(x, y)
    ref = scipy_stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic", use_continuity=True)
    assert abs(ours["p_value"] - ref.pvalue) < 0.01


def test_small_samples_get_no_p_value():
    out = mann_whitney([1, 2], [3, 4, 5])
    assert out["p_value"] is None and "no p-value" in out["note"] and out["rank_biserial"] is not None
    assert mann_whitney([], [1, 2, 3])["p_value"] is None


def test_bootstrap_is_reproducible_and_wide_for_tiny_n():
    a = bootstrap_median_diff([1, 2, 3], [2, 3, 4], seed=1)
    assert a == bootstrap_median_diff([1, 2, 3], [2, 3, 4], seed=1) and a["ci95"][1] - a["ci95"][0] >= 1


# ---------------- design
def test_assignment_is_seeded_balanced_and_reproducible():
    ids = [f"p{i}" for i in range(8)]
    a1 = experiments.assign_arms(ids, ["adaptive", "fixed_schedule"], 7)
    assert a1 == experiments.assign_arms(ids[::-1], ["adaptive", "fixed_schedule"], 7)
    assert sorted(list(a1.values())).count("adaptive") == 4
    assert a1 != experiments.assign_arms(ids, ["adaptive", "fixed_schedule"], 8)


def test_create_validation_and_start_lock(env):
    add_plants("a", "b", "c", "d")
    with pytest.raises(experiments.ExperimentError):
        experiments.create("t", "hyp hyp hyp hyp", ["a"], ["adaptive", "fixed_schedule"], 1, "experimental", "u")
    with pytest.raises(experiments.ExperimentError):
        experiments.create("t", "hyp hyp hyp hyp", ["a", "b"], ["fixed_schedule", "fixed_threshold"], 1, "experimental", "u")
    e1 = experiments.create("first", "hyp hyp hyp hyp", ["a", "b"], ["adaptive", "fixed_schedule"], 1, "experimental", "u")
    e2 = experiments.create("second", "hyp hyp hyp hyp", ["b", "c"], ["adaptive", "fixed_schedule"], 1, "experimental", "u")
    experiments.start(e1["key"])
    with pytest.raises(experiments.ExperimentError, match="already in running"):
        experiments.start(e2["key"])
    snap = experiments.get(e1["key"])
    assert snap["config_snapshot"]["settings"]["max_daily_runtime_seconds"] == settings.max_daily_runtime_seconds and snap["runs"][0]["profile_snapshot"]["low"] == 35


# ---------------- baseline controllers share the safety limits
@pytest.fixture()
def broker(monkeypatch):
    sent = []
    monkeypatch.setattr(irrigation, "publish_water", lambda p, s: (sent.append((p, s)) or {"published": True, "topic": "t", "payload": f"ON:{s}", "message": "ok"}))
    return sent


def online(plant, root=20.0):
    from app.services.telemetry import record_reading
    record_reading(plant, "soil_root", root, "t")


def make_running(plant, arm, params):
    add_plants(plant, "other")
    arms = ["adaptive", arm]
    e = experiments.create("x", "hyp hyp hyp hyp", [plant, "other"], arms, 1, "experimental", "u", params={arm: params})
    with db_session() as db:  # force the arm for this plant regardless of the random assignment
        db.execute("UPDATE experiment_runs SET arm=?,params_json=? WHERE plant_id=?", (arm, __import__("json").dumps({**experiments.DEFAULT_PARAMS[arm], **params}), plant))
    experiments.start(e["key"])
    return e["key"]


def test_fixed_threshold_waters_fixed_seconds_and_obeys_limits(env, broker):
    make_running("t1", "fixed_threshold", {"threshold_pct": 40, "seconds": 7})
    online("t1", 20.0)
    r = controllers.run_cycle("t1", execute=True)
    assert r["decision"] == "water" and r["executed"] and broker == [("t1", 7)]
    assert controllers.run_cycle("t1", execute=True)["executed"] is False and len(broker) == 1  # pending/cooldown applies to control arms too


def test_fixed_threshold_ignores_stale_and_suspect_sensors(env, broker):
    make_running("t2", "fixed_threshold", {"threshold_pct": 40})
    assert controllers.run_cycle("t2", execute=True)["decision"] == "skip" and broker == []
    from app.services.telemetry import record_reading
    for m, v in (("soil_root", 0.0), ("soil_mid", 80.0), ("soil_surface", 80.0)):
        record_reading("t2", m, v, "t")
    assert controllers.run_cycle("t2", execute=True)["decision"] == "skip" and broker == []


def test_fixed_schedule_due_logic_and_advisory_mode(env, broker):
    assert controllers.schedule_due(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc), 12)
    assert not controllers.schedule_due(datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc), 12)
    make_running("s1", "fixed_schedule", {"interval_hours": 0, "seconds": 6})
    online("s1", 90.0)  # wet soil: a fixed schedule waters anyway (that is what a schedule is)
    advisory = controllers.run_cycle("s1", execute=False)
    assert advisory["decision"] == "water" and advisory["executed"] is False and broker == []
    assert controllers.run_cycle("s1", execute=True)["executed"] and broker == [("s1", 6)]


def test_control_arm_never_sends_when_node_offline_or_manual(env, broker):
    make_running("s2", "fixed_schedule", {"interval_hours": 0})
    assert controllers.run_cycle("s2", execute=True)["decision"] == "skip"  # no telemetry => not online
    online("s2")
    with db_session() as db:
        db.execute("UPDATE plants SET mode='manual' WHERE plant_id='s2'")
    assert controllers.run_cycle("s2", execute=True)["decision"] == "skip" and broker == []


def test_duration_is_clamped_to_firmware_limit(env, broker):
    make_running("t3", "fixed_threshold", {"threshold_pct": 90, "seconds": 999})
    online("t3", 10.0)
    controllers.run_cycle("t3", execute=True)
    assert broker == [("t3", 15)]


# ---------------- results, report, export
def run_full_experiment(env_, monkeypatch=None):
    add_plants("a1", "a2", "c1", "c2")
    e = experiments.create("water test", "Adaptive uses less water", ["a1", "a2", "c1", "c2"], ["adaptive", "fixed_schedule"], 5, "experimental", "u",
                           analysis_plan="Mann-Whitney on water use.", primary_metrics=["commands", "time_below_target_pct"])
    experiments.start(e["key"])
    start = datetime.fromisoformat(experiments.get(e["key"])["started_at"])
    run_arm = {r["plant_id"]: r["arm"] for r in experiments.get(e["key"])["runs"]}
    with db_session() as db:
        for pid, arm in run_arm.items():
            for i in range(800):
                db.execute("INSERT INTO readings(plant_id,metric,value,received_at,topic) VALUES(?,?,?,?,?)", (pid, "soil_root", 30.0 if arm == "adaptive" else 50.0, (start + timedelta(seconds=10 * i)).isoformat(), "t"))
            n = 2 if arm == "adaptive" else 4
            for j in range(n):
                db.execute("INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,command_id,status) VALUES(?,?,?,?,?,?)", (pid, (start + timedelta(minutes=j + 1)).isoformat(), "auto", 5, "c", "confirmed"))
    experiments.stop(e["key"])
    with db_session() as db:  # the synthetic data is timestamped after "now"; widen the recorded window to cover it
        db.execute("UPDATE experiments SET ended_at=? WHERE key=?", ((start + timedelta(hours=3)).isoformat(), e["key"]))
    return e["key"], run_arm


def test_results_only_from_recorded_data_and_small_n_withholds_p(env):
    key, arms = run_full_experiment(env)
    r = experiments.results(key)
    ad = [p for p in r["per_plant"] if p["arm"] == "adaptive"][0]["metrics"]
    assert ad["commands"] == 2 and ad["requested_seconds"] == 10 and ad["water_basis"] == "unavailable" and ad["water_ml"] is None
    assert ad["green_fraction_change_per_day"] is None  # no photos => unavailable, not zero
    cmp_ = [c for c in r["comparisons"] if c["metric"] == "commands"][0]
    assert cmp_["test"]["p_value"] is None and "no p-value" in cmp_["test"]["note"] and r["label"] == "EXPERIMENTAL"


def test_estimated_vs_measured_water(env, monkeypatch):
    monkeypatch.setattr(settings, "flow_ml_per_second", 10.0)
    key, _ = run_full_experiment(env)
    m = experiments.results(key)["per_plant"][0]["metrics"]
    assert m["water_basis"] == "estimated" and m["water_ml"] == m["requested_seconds"] * 10.0
    with db_session() as db:
        db.execute("UPDATE irrigation_events SET measured_water_ml=33.0")
    m2 = experiments.results(key)["per_plant"][0]["metrics"]
    assert m2["water_basis"] == "measured" and m2["water_ml"] == 33.0 * m2["commands"]


def test_report_and_zip_export_content(env):
    key, _ = run_full_experiment(env)
    md = experiments.report_markdown(key)
    assert "Pre-registered analysis plan" in md and "Limitations" in md and "random seed: 5" in md and "SIMULATED" not in md
    z = zipfile.ZipFile(io.BytesIO(experiments.export_zip(key)))
    names = set(z.namelist())
    assert {"report.md", "experiment.json", "per_plant_metrics.csv", "irrigation_events.csv"} <= names and any(n.startswith("raw/") for n in names)
    assert z.read("per_plant_metrics.csv").decode().splitlines()[1].startswith("experimental,")


def test_simulated_experiments_are_labelled_everywhere(env):
    add_plants("s1", "s2")
    e = experiments.create("sim run", "Simulated hypothesis text", ["s1", "s2"], ["adaptive", "fixed_schedule"], 1, "simulated", "u")
    experiments.start(e["key"]); experiments.stop(e["key"])
    assert "SIMULATED DATA" in experiments.report_markdown(e["key"])
    assert experiments.results(e["key"])["label"] == "SIMULATED"
    assert zipfile.ZipFile(io.BytesIO(experiments.export_zip(e["key"]))).read("per_plant_metrics.csv").decode().splitlines()[1].startswith("simulated,")


def test_experiment_api_roles_and_flow(client, admin, viewer):
    add_plants("api1", "api2")
    body = {"name": "api exp", "hypothesis": "hypothesis long enough", "plant_ids": ["api1", "api2"], "seed": 9}
    assert client.post("/api/v1/experiments", json=body, headers=viewer).status_code == 403
    assert client.post("/api/v1/experiments", json={**body, "arms": ["adaptive", "adaptive"]}, headers=admin).status_code in (422,)
    key = client.post("/api/v1/experiments", json=body, headers=admin).json()["key"]
    assert client.get("/api/v1/experiments", headers=viewer).status_code == 200
    assert client.post(f"/api/v1/experiments/{key}/start", headers=viewer).status_code == 403
    assert client.get(f"/api/v1/experiments/{key}/results", headers=admin).status_code == 422  # not started
    assert client.post(f"/api/v1/experiments/{key}/start", headers=admin).status_code == 200
    assert client.post(f"/api/v1/experiments/{key}/start", headers=admin).status_code == 409
    assert client.post(f"/api/v1/experiments/{key}/stop", headers=admin).status_code == 200
    assert client.get(f"/api/v1/experiments/{key}/report.md", headers=admin).status_code == 200
    z = client.get(f"/api/v1/experiments/{key}/export.zip", headers=admin)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert client.get("/api/v1/experiments/nope", headers=admin).status_code == 404


# ---------------- camera metrics
def solid(color, size=(80, 60)):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", size, color).save(buf, "JPEG", quality=95); return buf.getvalue()


def test_cv_green_fraction_and_exposure_invariance():
    from app.services import cv_metrics
    assert cv_metrics.compute(solid((20, 160, 30)))["green_fraction"] > 0.95
    assert cv_metrics.compute(solid((150, 120, 100)))["green_fraction"] < 0.05
    bright, dark = cv_metrics.compute(solid((40, 200, 60))), cv_metrics.compute(solid((20, 100, 30)))
    assert abs(bright["green_fraction"] - dark["green_fraction"]) < 0.05 and bright["brightness"] > dark["brightness"]
    from PIL import Image
    img = Image.new("RGB", (100, 100), (120, 90, 70))
    for x in range(50):
        for y in range(100):
            img.putpixel((x, y), (30, 170, 40))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=95)
    assert 0.35 < cv_metrics.compute(buf.getvalue())["green_fraction"] < 0.65  # half the frame is leaf


def test_upload_stores_metrics_and_growth_needs_enough_photos(client, admin, device):
    from app.services import cv_metrics
    assert client.post("/upload", content=make_jpeg(color=(10, 120, 20)), headers={"X-Plant-Id": "plant01", "Content-Type": "image/jpeg", **device}).status_code == 201
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) c FROM photo_metrics").fetchone()["c"] == 1
    g = client.get("/api/v1/plants/plant01/insights/growth", headers=admin).json()
    assert g["available"] is False and "needs >= 10" in g["reason"] and g["label"] == "derived"
    assert client.get("/api/v1/plants/plant01/insights/growth?days=999", headers=admin).status_code == 422
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    with db_session() as db:
        for i in range(12):
            db.execute("INSERT INTO photo_metrics(photo_id,plant_id,received_at,green_fraction,mean_exg,brightness,computed_at) VALUES(?,?,?,?,?,?,?)", (100 + i, "plant01", (now - timedelta(days=6) + timedelta(hours=12 * i)).isoformat(), 0.1 + 0.01 * i, 0.2, 0.5, now.isoformat()))
    assert cv_metrics.growth_series("plant01", 14)["green_fraction_change_per_day"] > 0
