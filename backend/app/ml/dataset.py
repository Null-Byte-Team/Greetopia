"""Dataset construction for the root-zone water-stress predictor.

Target: y = 1 if the root-zone moisture falls BELOW the plant's profile minimum at any 10-minute bin within the next `horizon` minutes
(strictly future bins). Features use only bins at or before t. Rows whose future window is incomplete are dropped, and by default rows
with a confirmed watering inside the horizon are excluded so the model learns natural dry-down stress rather than the controller's actions.
"""
from __future__ import annotations

import hashlib

from app.db.database import db_session
from app.services.vpd import calculate_vpd

BIN_MIN = 10
MIN_SAMPLES_PER_BIN = 20  # of ~60 expected at 10 s
FEATURE_VERSION = "v1"
FEATURES = ["root", "mid", "surface", "temp", "hum", "vpd", "root_slope_30m", "root_slope_60m", "surface_minus_root", "mid_minus_root",
            "min_since_watering", "hour_sin", "hour_cos"]


class InsufficientData(Exception):
    pass


def load_bins(plant_id: str) -> pd.DataFrame:
    import pandas as pd  # lazy
    with db_session() as db:
        rows = db.execute("SELECT metric,value,received_at FROM readings WHERE plant_id=? AND metric IN ('soil_root','soil_mid','soil_surface','temperature_c','humidity_pct')", (plant_id,)).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["t"] = pd.to_datetime(df["received_at"], utc=True, format="ISO8601")
    wide = {}
    for metric, name in (("soil_root", "root"), ("soil_mid", "mid"), ("soil_surface", "surface"), ("temperature_c", "temp"), ("humidity_pct", "hum")):
        s = df[df["metric"] == metric].set_index("t")["value"].sort_index()
        grp = s.resample(f"{BIN_MIN}min", label="right", closed="right")
        mean, cnt = grp.mean(), grp.count()
        wide[name] = mean.where(cnt >= MIN_SAMPLES_PER_BIN)
    return pd.DataFrame(wide).asfreq(f"{BIN_MIN}min")


def watering_times(plant_id: str) -> list[pd.Timestamp]:
    import pandas as pd  # lazy
    with db_session() as db:
        rows = db.execute("SELECT observed_start_at FROM irrigation_events WHERE plant_id=? AND status='confirmed' AND observed_start_at IS NOT NULL", (plant_id,)).fetchall()
    out = []
    for r in rows:
        ts = pd.Timestamp(r["observed_start_at"])
        out.append(ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC"))
    return sorted(out)


def build_features(bins: pd.DataFrame, waterings: list[pd.Timestamp]) -> pd.DataFrame:
    """Features at bin t depend ONLY on bins <= t (and waterings <= t)."""
    import numpy as np  # lazy
    import pandas as pd  # lazy
    f = pd.DataFrame(index=bins.index)
    f["root"], f["mid"], f["surface"], f["temp"], f["hum"] = bins["root"], bins["mid"], bins["surface"], bins["temp"], bins["hum"]
    f["vpd"] = [calculate_vpd(t, h) if pd.notna(t) and pd.notna(h) else np.nan for t, h in zip(bins["temp"], bins["hum"])]
    f["root_slope_30m"] = (bins["root"] - bins["root"].shift(3)) / 0.5
    f["root_slope_60m"] = (bins["root"] - bins["root"].shift(6)) / 1.0
    f["surface_minus_root"] = bins["surface"] - bins["root"]
    f["mid_minus_root"] = bins["mid"] - bins["root"]
    idx = bins.index
    since = np.full(len(idx), 1440.0)
    if waterings:
        w = np.array([t.value for t in waterings], dtype=np.int64)
        tv = idx.as_unit("ns").asi8
        pos = np.searchsorted(w, tv, side="right") - 1
        ok = pos >= 0
        since[ok] = np.minimum(1440.0, (tv[ok] - w[pos[ok]]) / 6e10)
    f["min_since_watering"] = since
    hour = idx.hour + idx.minute / 60
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    return f[FEATURES]


def build_labels(bins: pd.DataFrame, low: float, horizon_min: int, waterings: list[pd.Timestamp], exclude_watered: bool = True) -> pd.Series:
    """y[t] = 1 if min(root[t+1 .. t+H]) < low. NaN when the future window is incomplete (or watered, if exclude_watered)."""
    import numpy as np  # lazy
    import pandas as pd  # lazy
    h = horizon_min // BIN_MIN
    root = bins["root"]
    fut = pd.concat([root.shift(-k) for k in range(1, h + 1)], axis=1)
    complete = fut.notna().all(axis=1)
    y = (fut.min(axis=1) < low).astype(float).where(complete)
    if exclude_watered and waterings:
        w = np.array([t.value for t in waterings], dtype=np.int64)
        tv = bins.index.as_unit("ns").asi8
        end = tv + horizon_min * 60 * int(1e9)
        pos = np.searchsorted(w, tv, side="right")  # first watering strictly after t
        watered = (pos < len(w)) & (w[np.minimum(pos, len(w) - 1)] <= end)
        y[watered] = np.nan
    return y


def build_dataset(plant_ids: list[str], horizon_min: int, lows: dict[str, float], exclude_watered: bool = True) -> pd.DataFrame:
    import pandas as pd  # lazy
    parts = []
    for pid in plant_ids:
        bins = load_bins(pid)
        if bins.empty:
            continue
        w = watering_times(pid)
        df = build_features(bins, w).copy()
        df["y"], df["plant_id"] = build_labels(bins, lows[pid], horizon_min, w, exclude_watered), pid
        parts.append(df.dropna())
    if not parts:
        raise InsufficientData("no usable data")
    return pd.concat(parts).sort_index()


def dataset_fingerprint(data: pd.DataFrame) -> dict:
    import pandas as pd  # lazy
    h = hashlib.sha256(pd.util.hash_pandas_object(data.drop(columns=["plant_id"]), index=True).values.tobytes()).hexdigest()
    return {"rows": int(len(data)), "positives": int(data["y"].sum()), "start": data.index.min().isoformat(), "end": data.index.max().isoformat(),
            "sha256": h, "plants": sorted(data["plant_id"].unique().tolist()), "provenance": "device readings and confirmed irrigation events from the Greetopia database"}
