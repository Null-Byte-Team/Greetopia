"""Vision result schema (version 1) and strict validation of provider output.

Vision output is an uncertain observation, never a diagnosis and never a pump trigger. Species is only ever a
*candidate*; it becomes the plant's species only when a user confirms it.
"""
from __future__ import annotations

from typing import Any, Protocol

SCHEMA_VERSION = "1"


class VisionProvider(Protocol):
    def analyze(self, image_path: str, plant_id: str) -> dict[str, Any]: ...


def _bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


def _conf(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, f)), 3) if f == f else None


def _text(v: Any, n: int) -> str | None:
    return v.strip()[:n] if isinstance(v, str) and v.strip() else None


def _strings(v: Any, n_items: int = 8, n_chars: int = 160) -> list[str]:
    return [x.strip()[:n_chars] for x in v if isinstance(x, str) and x.strip()][:n_items] if isinstance(v, list) else []


def normalize_vision(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce provider JSON into the documented schema; unknown/invalid fields become null, never invented."""
    candidates = []
    name, conf = _text(raw.get("species_guess") or raw.get("common_name"), 100), _conf(raw.get("confidence"))
    if name:
        candidates.append({"name": name, "confidence": conf})
    for item in raw.get("species_candidates", []) if isinstance(raw.get("species_candidates"), list) else []:
        if isinstance(item, dict) and _text(item.get("name"), 100) and all(c["name"] != item["name"] for c in candidates):
            candidates.append({"name": _text(item["name"], 100), "confidence": _conf(item.get("confidence"))})
    out = {
        "schema_version": SCHEMA_VERSION, "analysis_status": "ok",
        "species_candidates": candidates[:5], "species_confidence": conf,
        "wilting": _bool(raw.get("wilting")), "discoloration": _bool(raw.get("discoloration")),
        "spots_or_pests": _bool(raw.get("spots_or_pests")), "confidence": conf,
        "notes": _text(raw.get("notes") or raw.get("summary"), 400),
        # fields kept for the dashboard
        "species_guess": name, "common_name": _text(raw.get("common_name"), 100),
        "summary": _text(raw.get("summary"), 400),
        "visible_observations": _strings(raw.get("visible_observations")),
        "possible_stress_signs": _strings(raw.get("possible_stress_signs")),
        "limitations": _strings(raw.get("limitations")),
    }
    return out
