"""Training + honest evaluation: chronological train/val/test split with a purge gap equal to the horizon, time-series CV on train+val,
comparison with a persistence baseline, no synthetic or invented results. Raises InsufficientData instead of training on too little."""
from __future__ import annotations

from app.ml import registry
from app.ml.dataset import BIN_MIN, FEATURE_VERSION, FEATURES, InsufficientData, build_dataset, dataset_fingerprint
from app.services.insights import plant_profile

MIN_ROWS, MIN_TRAIN_POS, MIN_TEST_POS, BASELINE_MARGIN = 500, 30, 10, 5.0


def chrono_split(data: pd.DataFrame, horizon_min: int):
    """60/20/20 by TIME with a purge gap of `horizon_min` between sets so label windows never overlap across the boundary."""
    import numpy as np  # lazy
    import pandas as pd  # lazy
    times = np.sort(data.index.unique())
    n = len(times)
    t1, t2 = times[int(n * 0.6)], times[int(n * 0.8)]
    gap = pd.Timedelta(minutes=horizon_min)
    return data[data.index < t1 - gap], data[(data.index >= t1) & (data.index < t2 - gap)], data[data.index >= t2]


def baseline_score(df: pd.DataFrame, low: float) -> "np.ndarray":
    """Persistence rule: the lower the current root moisture relative to low+margin, the higher the stress score (clipped to 0..1)."""
    import numpy as np  # lazy
    return np.clip((low + BASELINE_MARGIN - df["root"].values) / BASELINE_MARGIN, 0, 1)


def metrics(y, p, threshold=0.5) -> dict:
    import numpy as np  # lazy
    from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score  # lazy
    y, p = np.asarray(y), np.asarray(p)
    pred = (p >= threshold).astype(int)
    out = {"n": int(len(y)), "positives": int(y.sum()), "threshold": round(float(threshold), 3),
           "precision": round(float(precision_score(y, pred, zero_division=0)), 3), "recall": round(float(recall_score(y, pred, zero_division=0)), 3),
           "f1": round(float(f1_score(y, pred, zero_division=0)), 3), "brier": round(float(brier_score_loss(y, np.clip(p, 0, 1))), 4),
           "roc_auc": round(float(roc_auc_score(y, p)), 3) if 0 < y.sum() < len(y) else None}
    edges, cal = np.linspace(0, 1, 6), []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & ((p < b) if b < 1 else (p <= b))
        if m.sum():
            cal.append({"bin": f"{a:.1f}-{b:.1f}", "n": int(m.sum()), "mean_pred": round(float(p[m].mean()), 3), "observed": round(float(y[m].mean()), 3)})
    out["calibration"] = cal
    return out


def best_threshold(y, p) -> float:
    import numpy as np  # lazy
    from sklearn.metrics import f1_score  # lazy
    return float(max(np.linspace(0.1, 0.9, 17), key=lambda t: f1_score(y, (np.asarray(p) >= t).astype(int), zero_division=0)))


def candidate_models():
    from sklearn.ensemble import GradientBoostingClassifier  # lazy
    from sklearn.linear_model import LogisticRegression  # lazy
    from sklearn.pipeline import make_pipeline  # lazy
    from sklearn.preprocessing import StandardScaler  # lazy
    return {"logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, class_weight="balanced")),
            "gboost": GradientBoostingClassifier(n_estimators=120, max_depth=3, random_state=0)}


def train(plant_ids: list[str], horizon_min: int = 60) -> dict:
    lows = {pid: plant_profile(pid)["low"] for pid in plant_ids}
    if len(set(lows.values())) > 1:
        raise InsufficientData("plants have different profile minimums; train one model per target level")
    low = next(iter(lows.values()))
    data = build_dataset(plant_ids, horizon_min, lows)
    if len(data) < MIN_ROWS:
        raise InsufficientData(f"needs >= {MIN_ROWS} complete labelled rows (found {len(data)})")
    tr, va, te = chrono_split(data, horizon_min)
    pos_trva, pos_te = int(tr["y"].sum() + va["y"].sum()), int(te["y"].sum())
    if pos_trva < MIN_TRAIN_POS or pos_te < MIN_TEST_POS or tr["y"].nunique() < 2 or va["y"].nunique() < 2:
        raise InsufficientData(f"needs >= {MIN_TRAIN_POS} stress rows in train+val and >= {MIN_TEST_POS} in the test period (found {pos_trva} / {pos_te}) with both classes in each split")
    fitted, val_scores, cv = {}, {}, {}
    trva = pd.concat([tr, va])
    for name, model in candidate_models().items():
        model.fit(tr[FEATURES], tr["y"])
        fitted[name] = model
        pv = model.predict_proba(va[FEATURES])[:, 1]
        val_scores[name] = metrics(va["y"], pv, best_threshold(va["y"], pv))
        aucs = []
        for a, b in TimeSeriesSplit(n_splits=3, gap=horizon_min // BIN_MIN).split(trva):
            yt = trva["y"].iloc[b]
            if 0 < yt.sum() < len(yt) and trva["y"].iloc[a].nunique() == 2:
                m = candidate_models()[name].fit(trva[FEATURES].iloc[a], trva["y"].iloc[a])
                aucs.append(roc_auc_score(yt, m.predict_proba(trva[FEATURES].iloc[b])[:, 1]))
        cv[name] = {"folds": len(aucs), "roc_auc_mean": round(float(np.mean(aucs)), 3) if aucs else None, "roc_auc_std": round(float(np.std(aucs)), 3) if aucs else None}
    selected = max(fitted, key=lambda n: (val_scores[n]["roc_auc"] or 0, val_scores[n]["f1"]))
    pt = fitted[selected].predict_proba(te[FEATURES])[:, 1]
    b_thr = best_threshold(va["y"], baseline_score(va, low))
    meta = {
        "plant_ids": plant_ids, "horizon_min": horizon_min, "bin_min": BIN_MIN, "feature_version": FEATURE_VERSION, "feature_schema": FEATURES,
        "low_pct_trained": low, "selected_model": selected, "dataset": dataset_fingerprint(data),
        "label_definition": "1 if root-zone moisture < profile minimum in any 10-min bin within the next horizon (strictly future); rows with a confirmed watering inside the horizon are excluded",
        "split": {"train": [tr.index.min().isoformat(), tr.index.max().isoformat(), len(tr)], "val": [va.index.min().isoformat(), va.index.max().isoformat(), len(va)],
                  "test": [te.index.min().isoformat(), te.index.max().isoformat(), len(te)], "purge_gap_min": horizon_min},
        "metrics": {"validation": val_scores, "cv_roc_auc": cv,
                    "test": {"baseline": metrics(te["y"], baseline_score(te, low), b_thr), selected: metrics(te["y"], pt, val_scores[selected]["threshold"])}},
        "limitations": ["Trained on one site/plant set; no claim of generalisation.", "Labels depend on the plant profile minimum at training time.",
                        "Controller actions are excluded from labels, so the model predicts natural dry-down stress only.",
                        "Online learning is not implemented; models are retrained offline and approved explicitly."],
    }
    return registry.meta(registry.save(fitted[selected], meta))
