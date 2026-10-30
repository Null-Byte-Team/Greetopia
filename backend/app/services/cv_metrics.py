"""Objective plant metrics from the fixed camera (classical computer vision, no LLM).

green_fraction = share of pixels whose excess-green index (2g - r - b, on chromatic coordinates r/(r+g+b) etc.) exceeds a threshold: a
leaf-area proxy. Chromatic coordinates cancel overall exposure/brightness. White balance is NOT corrected (a gray-world correction would
erase the signal in a leaf-dominated frame), so the camera and lighting must stay constant. It is a PROXY, not biomass; the wilting/growth
interpretation stays with the user."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import Image

from app.db.database import db_session

log = logging.getLogger(__name__)
EXG_THRESHOLD = 0.10


def compute(jpeg: bytes) -> dict:
    with Image.open(io.BytesIO(jpeg)) as img:
        img = img.convert("RGB")
        img.thumbnail((320, 320))
        a = np.asarray(img, dtype=np.float64)
    gray = a.mean()
    if gray <= 1e-6:
        return {"green_fraction": 0.0, "mean_exg": 0.0, "brightness": 0.0}
    s = a.sum(axis=2) + 1e-6
    r, g, b = a[..., 0] / s, a[..., 1] / s, a[..., 2] / s
    exg = 2 * g - r - b
    mask = exg > EXG_THRESHOLD
    return {"green_fraction": round(float(mask.mean()), 5), "mean_exg": round(float(exg[mask].mean()) if mask.any() else 0.0, 5),
            "brightness": round(float(gray / 255), 4)}


def store(photo_id: int, plant_id: str, received_at: str, jpeg: bytes) -> None:
    try:
        m = compute(jpeg)
        with db_session() as db:
            db.execute("INSERT OR REPLACE INTO photo_metrics(photo_id,plant_id,received_at,green_fraction,mean_exg,brightness,computed_at) VALUES(?,?,?,?,?,?,?)",
                       (photo_id, plant_id, received_at, m["green_fraction"], m["mean_exg"], m["brightness"], datetime.now(timezone.utc).isoformat()))
    except Exception:
        log.exception("photo metrics failed for photo %s", photo_id)


def backfill(plant_id: str, limit: int = 500) -> int:
    from app.services.photos import resolve_photo_path
    n = 0
    with db_session() as db:
        rows = db.execute("SELECT id,file_path,received_at FROM photos WHERE plant_id=? AND id NOT IN (SELECT photo_id FROM photo_metrics) ORDER BY id LIMIT ?", (plant_id, limit)).fetchall()
    for r in rows:
        path = resolve_photo_path(r["file_path"])
        if path:
            store(r["id"], plant_id, r["received_at"], path.read_bytes())
            n += 1
    return n


def growth_series(plant_id: str, days: int = 14) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db_session() as db:
        rows = db.execute("SELECT received_at,green_fraction,mean_exg,brightness FROM photo_metrics WHERE plant_id=? AND received_at>=? ORDER BY received_at", (plant_id, since)).fetchall()
    pts = [dict(r) for r in rows]
    out = {"label": "derived", "window_days": days, "samples": len(pts), "points": pts[-500:],
           "note": "Green-area proxy from classical CV; requires constant camera position and lighting; not biomass."}
    if len(pts) < 10:
        return {**out, "available": False, "reason": f"needs >= 10 analysed photos (found {len(pts)})"}
    t0 = datetime.fromisoformat(pts[0]["received_at"])
    xs = np.array([(datetime.fromisoformat(p["received_at"]) - t0).total_seconds() / 86400 for p in pts])
    if xs[-1] < 2:
        return {**out, "available": False, "reason": "photos span less than 2 days"}
    slope = float(np.polyfit(xs, [p["green_fraction"] for p in pts], 1)[0])
    return {**out, "available": True, "green_fraction_change_per_day": round(slope, 5)}
