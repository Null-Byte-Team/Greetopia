"""Inference only through an approved, checksum-verified model. Returns an explicit 'unavailable' otherwise. Never publishes commands."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.db.database import db_session
from app.ml import registry
from app.ml.dataset import FEATURE_VERSION, FEATURES, build_features, load_bins, watering_times
from app.services.insights import plant_profile

CACHE_S = 300


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "stress_probability": None, "reason": reason}


def predict(plant_id: str, persist: bool = True) -> dict:
    import pandas as pd  # lazy – heavy dep; only loaded when a prediction is requested
    loaded = registry.load_approved(plant_id)
    if not loaded:
        return _unavailable("no approved model with a valid checksum exists for this plant (the ML predictor is experimental until one is trained on real data and approved)")
    model, meta = loaded
    if abs(plant_profile(plant_id)["low"] - meta["low_pct_trained"]) > 1e-6:
        return _unavailable("the plant's moisture minimum changed since the model was trained; retrain")
    bins = load_bins(plant_id)
    if len(bins) < 8:
        return _unavailable("not enough recent data")
    feats = build_features(bins, watering_times(plant_id))
    complete = feats.dropna()  # the bin still being filled is incomplete by construction; use the newest COMPLETE bin
    now = datetime.now(timezone.utc)
    if complete.empty or (now - complete.index[-1].to_pydatetime()) > timedelta(minutes=30):
        return _unavailable("no complete 10-minute bin in the last 30 minutes")
    last = complete.iloc[-1]
    p = float(model.predict_proba(pd.DataFrame([last[FEATURES]]))[:, 1][0])
    out = {"status": "ok", "stress_probability": round(p, 4), "model_version": meta["version"], "horizon_min": meta["horizon_min"], "feature_version": FEATURE_VERSION,
           "label": "derived", "note": "Corroborating evidence only; it never triggers watering by itself."}
    if persist:
        with db_session() as db:
            db.execute("INSERT INTO ml_predictions(plant_id,created_at,model_version,feature_version,horizon_min,stress_probability,status,features_json) VALUES(?,?,?,?,?,?,?,?)",
                       (plant_id, now.isoformat(), meta["version"], FEATURE_VERSION, meta["horizon_min"], p, "ok", json.dumps({k: float(v) for k, v in last[FEATURES].items()})))
    return out


def cached_probability(plant_id: str) -> float | None:
    """Used by the decision engine. Reuses a recent stored prediction; None when unavailable."""
    since = (datetime.now(timezone.utc) - timedelta(seconds=CACHE_S)).isoformat()
    with db_session() as db:
        row = db.execute("SELECT stress_probability FROM ml_predictions WHERE plant_id=? AND status='ok' AND created_at>=? ORDER BY id DESC LIMIT 1", (plant_id, since)).fetchone()
    if row:
        return row["stress_probability"]
    try:
        r = predict(plant_id)
    except Exception:
        return None
    return r["stress_probability"] if r["status"] == "ok" else None
