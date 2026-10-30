"""Model registry. Artifacts are loaded only when approved AND their SHA-256 matches the recorded checksum (joblib/pickle must never be
loaded from an unverified file)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

from app.core.config import settings


def root() -> Path:
    p = Path(settings.model_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(model, meta: dict) -> str:
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + meta["dataset"]["sha256"][:8]
    d = root() / version
    d.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, d / "model.joblib")
    meta = {**meta, "version": version, "artifact_sha256": sha256_file(d / "model.joblib"), "status": "experimental", "approved": False,
            "created_at": datetime.now(timezone.utc).isoformat()}
    (d / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return version


def meta(version: str) -> dict:
    return json.loads((root() / version / "meta.json").read_text())


def list_versions() -> list[dict]:
    out = []
    for d in sorted(root().iterdir()):
        if (d / "meta.json").is_file():
            m = json.loads((d / "meta.json").read_text())
            out.append({k: m[k] for k in ("version", "status", "approved", "selected_model", "horizon_min", "plant_ids", "created_at")})
    return out


def approve(version: str, approved_by: str) -> dict:
    m = meta(version)
    t = m["metrics"]["test"]
    b, s = t["baseline"], t[m["selected_model"]]
    if s.get("roc_auc") is None or b.get("roc_auc") is None or not (s["roc_auc"] > b["roc_auc"] and s["f1"] > b["f1"]):
        raise ValueError("Refusing to approve: the model does not beat the persistence baseline on the held-out test period (ROC-AUC and F1).")
    m.update(approved=True, status="approved", approved_by=approved_by, approved_at=datetime.now(timezone.utc).isoformat())
    (root() / version / "meta.json").write_text(json.dumps(m, indent=2, default=str))
    return m


def load_approved(plant_id: str | None = None):
    """Newest approved model with a matching checksum, or None."""
    for d in sorted(root().iterdir(), reverse=True):
        mp = d / "meta.json"
        if not mp.is_file():
            continue
        m = json.loads(mp.read_text())
        if not m.get("approved") or (plant_id and plant_id not in m["plant_ids"]):
            continue
        art = d / "model.joblib"
        if art.is_file() and sha256_file(art) == m["artifact_sha256"]:
            return joblib.load(art), m
    return None
