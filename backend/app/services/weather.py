from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.db.database import db_session

CACHE_TTL = timedelta(hours=1)


def _unavailable(plant_id: str, source: str, error: str | None = None):
    out = {"plant_id": plant_id, "checked_at": None, "rain_probability": None, "rain_mm": None, "source": source, "available": False}
    if error:
        out["error"] = error[:120]
    return out


def _location(plant_id: str):
    with db_session() as db:
        row = db.execute("SELECT latitude,longitude FROM plants WHERE plant_id=?", (plant_id,)).fetchone()
    if row and row["latitude"] is not None and row["longitude"] is not None:
        return row["latitude"], row["longitude"]
    return settings.openweather_lat, settings.openweather_lon


def get_weather(plant_id: str, force: bool = False):
    """Cached forecast. A missing/failed forecast is reported as unavailable, NEVER as 0% rain."""
    with db_session() as db:
        row = db.execute("SELECT * FROM weather_snapshots WHERE plant_id=?", (plant_id,)).fetchone()
    if row and not force:
        checked = datetime.fromisoformat(row["checked_at"])
        if datetime.now(timezone.utc) - checked < CACHE_TTL:
            return {"plant_id": plant_id, "checked_at": row["checked_at"], "rain_probability": row["rain_probability"],
                    "rain_mm": row["rain_mm"], "source": row["source"], "available": True}
    lat, lon = _location(plant_id)
    if not settings.openweather_api_key or lat is None or lon is None:
        return _unavailable(plant_id, "not_configured")
    try:
        with httpx.Client(timeout=6) as client:
            res = client.get("https://api.openweathermap.org/data/2.5/forecast",
                             params={"lat": lat, "lon": lon, "appid": settings.openweather_api_key, "units": "metric"})
            if res.status_code == 429:
                return _unavailable(plant_id, "rate_limited")
            res.raise_for_status()
            data = res.json()
        forecasts = data.get("list", [])[:8]
        if not forecasts:
            return _unavailable(plant_id, "error", "empty forecast")
        probs = [float(x["pop"]) for x in forecasts if x.get("pop") is not None]
        rain = sum(float(x.get("rain", {}).get("3h", 0)) for x in forecasts)
        probability = max(probs) if probs else None
        checked = datetime.now(timezone.utc).isoformat()
        with db_session() as db:
            db.execute("INSERT INTO weather_snapshots(plant_id,checked_at,rain_probability,rain_mm,source) VALUES(?,?,?,?,?) "
                       "ON CONFLICT(plant_id) DO UPDATE SET checked_at=excluded.checked_at,rain_probability=excluded.rain_probability,"
                       "rain_mm=excluded.rain_mm,source=excluded.source", (plant_id, checked, probability, rain, "openweathermap"))
        return {"plant_id": plant_id, "checked_at": checked, "rain_probability": probability, "rain_mm": round(rain, 2),
                "source": "openweathermap", "available": True}
    except httpx.TimeoutException:
        return _unavailable(plant_id, "timeout")
    except Exception as exc:
        return _unavailable(plant_id, "error", type(exc).__name__)
