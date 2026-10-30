"""SYNTHETIC sawtooth moisture data, used ONLY to exercise the pipeline mechanics. Metrics from it mean nothing about real plants."""
import json
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.db.database import db_session
from app.ml import dataset, inference, registry, train as trainer
from app.ml.dataset import InsufficientData


@pytest.fixture(autouse=True)
def model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "model_dir", str(tmp_path / "models"))


def seed_synthetic(plant="plant01", days=10, step=30, seed=1, end=None):
    rnd = random.Random(seed)
    end = end or datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=days)
    root, t = 70.0, start
    rows, events = [], []
    while t <= end:
        hour = t.hour + t.minute / 60
        temp = 24 + 6 * np.sin((hour - 9) / 24 * 2 * np.pi) + rnd.gauss(0, 0.2)
        hum = 55 - 20 * np.sin((hour - 9) / 24 * 2 * np.pi) + rnd.gauss(0, 0.5)
        root -= (4.0 / 3600) * step * (1 + 0.3 * (temp - 24) / 6) + rnd.gauss(0, 0.01)
        if root < 25:
            root += 40
            events.append(t)
        for m, v in (("soil_root", root), ("soil_mid", root + 5), ("soil_surface", root + 10), ("temperature_c", temp), ("humidity_pct", hum)):
            rows.append((plant, m, round(v, 2), t.isoformat(), "synthetic"))
        t += timedelta(seconds=step)
    with db_session() as db:
        db.executemany("INSERT INTO readings(plant_id,metric,value,received_at,topic) VALUES(?,?,?,?,?)", rows)
        db.execute("UPDATE plants SET ideal_moisture_min=35, ideal_moisture_max=65 WHERE plant_id=?", (plant,))
        for e in events:
            db.execute("INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,command_id,status,observed_start_at,observed_end_at) VALUES(?,?,?,?,?,?,?,?)",
                       (plant, e.isoformat(), "auto", 5, "c", "confirmed", e.isoformat(), (e + timedelta(seconds=5)).isoformat()))
    return events


def test_insufficient_data_never_trains_or_fakes(env):
    with pytest.raises(InsufficientData):
        trainer.train(["plant01"])
    seed_synthetic(days=1)
    with pytest.raises(InsufficientData):
        trainer.train(["plant01"])
    assert registry.list_versions() == []


def test_labels_are_strictly_future_and_incomplete_windows_dropped():
    idx = pd.date_range("2026-01-01", periods=12, freq="10min", tz="UTC")
    root = [50, 50, 50, 50, 34, 50, 50, 50, 50, 50, 50, 50.0]
    bins = pd.DataFrame({"root": root}, index=idx)
    y = dataset.build_labels(bins, low=35, horizon_min=30, waterings=[])
    assert y.iloc[0] == 0 and y.iloc[1] == 1 and y.iloc[3] == 1 and y.iloc[4] == 0  # t sees only t+1..t+3
    assert y.iloc[-1] != y.iloc[-1] and y.iloc[-3] != y.iloc[-3]  # window runs past the data -> NaN, not 0


def test_exclude_labels_with_watering_inside_horizon():
    idx = pd.date_range("2026-01-01", periods=12, freq="10min", tz="UTC")
    bins = pd.DataFrame({"root": [30.0] * 12}, index=idx)
    y = dataset.build_labels(bins, 35, 30, [idx[5] + pd.Timedelta(minutes=1)], exclude_watered=True)
    assert y.iloc[3] != y.iloc[3] and y.iloc[4] != y.iloc[4] and y.iloc[5] != y.iloc[5]  # watering within the next 30 min
    assert y.iloc[0] == 1
    y2 = dataset.build_labels(bins, 35, 30, [idx[5] + pd.Timedelta(minutes=1)], exclude_watered=False)
    assert y2.iloc[3] == 1


def test_features_never_use_the_future():
    idx = pd.date_range("2026-01-01", periods=40, freq="10min", tz="UTC")
    rng = np.random.default_rng(0)
    bins = pd.DataFrame({c: rng.uniform(20, 70, 40) for c in ("root", "mid", "surface", "temp", "hum")}, index=idx)
    full = dataset.build_features(bins, [idx[10]])
    cut = dataset.build_features(bins.iloc[:25], [idx[10]])
    pd.testing.assert_frame_equal(full.iloc[:25], cut)
    tampered = bins.copy(); tampered.iloc[30:] = 999
    pd.testing.assert_frame_equal(dataset.build_features(tampered, [idx[10]]).iloc[:25], cut)


def test_chronological_split_has_purge_gap_and_no_overlap():
    idx = pd.date_range("2026-01-01", periods=2000, freq="10min", tz="UTC")
    df = pd.DataFrame({"y": 0.0, "plant_id": "p"}, index=idx)
    tr, va, te = trainer.chrono_split(df, 60)
    assert tr.index.max() + pd.Timedelta(minutes=60) <= va.index.min() and va.index.max() + pd.Timedelta(minutes=60) <= te.index.min()
    assert len(tr) + len(va) + len(te) < len(df)  # rows inside the gaps were purged


def test_train_registers_experimental_model_with_full_provenance(env):
    seed_synthetic(days=10)
    meta = trainer.train(["plant01"], 60)
    assert meta["approved"] is False and meta["status"] == "experimental"
    assert meta["dataset"]["sha256"] and meta["dataset"]["rows"] > 500 and meta["feature_schema"] == dataset.FEATURES
    t = meta["metrics"]["test"]
    assert "baseline" in t and meta["selected_model"] in t and {"precision", "recall", "f1", "roc_auc", "brier", "calibration"} <= set(t["baseline"])
    assert meta["split"]["purge_gap_min"] == 60 and meta["limitations"]
    assert inference.predict("plant01")["status"] == "unavailable"  # not approved yet => never used


def test_approval_requires_beating_baseline():
    base = {"roc_auc": 0.80, "f1": 0.60}
    def fake(sel):
        return {"selected_model": "m", "metrics": {"test": {"baseline": base, "m": sel}}}
    from app.ml import registry as r
    import types
    orig = r.meta
    try:
        r.meta = lambda v: fake({"roc_auc": 0.70, "f1": 0.5})
        with pytest.raises(ValueError, match="does not beat"):
            r.approve("v", "me")
        r.meta = lambda v: fake({"roc_auc": None, "f1": 0.9})
        with pytest.raises(ValueError):
            r.approve("v", "me")
    finally:
        r.meta = orig


def approve_for_test(version):
    d = registry.root() / version
    m = json.loads((d / "meta.json").read_text())
    m.update(approved=True, status="approved")
    (d / "meta.json").write_text(json.dumps(m))


def test_inference_checksum_tamper_and_profile_change(env):
    seed_synthetic(days=10)
    version = trainer.train(["plant01"], 60)["version"]
    approve_for_test(version)
    out = inference.predict("plant01")
    assert out["status"] == "ok" and 0 <= out["stress_probability"] <= 1 and out["model_version"] == version
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) c FROM ml_predictions").fetchone()["c"] == 1
    assert abs(inference.cached_probability("plant01") - out["stress_probability"]) < 1e-3  # output is rounded to 4 decimals
    with db_session() as db:
        db.execute("UPDATE plants SET ideal_moisture_min=40 WHERE plant_id='plant01'")
    assert "changed" in inference.predict("plant01", persist=False)["reason"]
    with db_session() as db:
        db.execute("UPDATE plants SET ideal_moisture_min=35 WHERE plant_id='plant01'")
    (registry.root() / version / "model.joblib").write_bytes(b"malicious pickle bytes")
    assert registry.load_approved("plant01") is None  # checksum mismatch: never unpickled
    assert inference.predict("plant01", persist=False)["status"] == "unavailable"


def test_ml_endpoints_and_decision_engine_is_unaffected_without_model(client, admin):
    r = client.get("/api/v1/plants/plant01/ml/status", headers=admin).json()
    assert r["prediction"]["status"] == "unavailable" and "never sends pump commands" in r["note"]
    assert client.get("/api/v1/plants/plant01/ml/predictions", headers=admin).json() == []
    assert client.get("/api/v1/plants/plant01/ml/status").status_code == 401
