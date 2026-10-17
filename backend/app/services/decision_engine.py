from datetime import datetime, timezone
import json, uuid
from app.core.config import settings
from app.db.database import db_session
from app.services.telemetry import latest_readings
from app.services.vpd import calculate_vpd, vpd_band
from app.services.weather import get_weather
from app.services.mqtt_service import publish_water

def evaluate_plant(plant_id: str, execute: bool=False):
    readings=latest_readings(plant_id)
    root=readings.get('soil_root')
    temp=readings.get('temperature_c'); humidity=readings.get('humidity_pct')
    root_value=root['value'] if root and root['fresh'] else None
    vpd=calculate_vpd(temp['value'] if temp and temp['fresh'] else None, humidity['value'] if humidity and humidity['fresh'] else None)
    weather=get_weather(plant_id)
    with db_session() as db:
        plant=db.execute('SELECT * FROM plants WHERE plant_id=?',(plant_id,)).fetchone()
        if not plant: return {'plant_id':plant_id,'decision':'skip','reason':'Plant is not registered.','readings':readings}
    reasons=[]; should_water=False
    # Cooldown prevents repeated API/loop calls from issuing repeated pump commands.
    with db_session() as db:
        last_event = db.execute("SELECT created_at,status FROM irrigation_events WHERE plant_id=? AND source IN ('auto','manual') ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
    cooldown_active = False
    if last_event:
        try:
            last_time = datetime.fromisoformat(last_event['created_at'])
            if last_time.tzinfo is None: last_time = last_time.replace(tzinfo=timezone.utc)
            cooldown_active = (datetime.now(timezone.utc) - last_time).total_seconds() < max(0, settings.irrigation_cooldown_minutes) * 60
        except (TypeError, ValueError):
            cooldown_active = True  # malformed timestamps fail safe
    if plant['mode'] != 'auto': reasons.append('Plant is in Manual mode; automatic watering is disabled.')
    elif root_value is None: reasons.append('Root-zone reading is missing or stale; fail-safe skip.')
    elif root_value < settings.root_moisture_threshold:
        if cooldown_active:
            reasons.append(f'Irrigation cooldown is active ({settings.irrigation_cooldown_minutes} minutes); watering skipped.')
        elif weather.get('rain_probability') is not None and weather['rain_probability'] >= settings.rain_skip_probability:
            reasons.append('Soil is below threshold, but forecast rain probability is high; watering skipped.')
        else:
            should_water=True; reasons.append(f'Root-zone moisture {root_value:.1f}% is below configured threshold {settings.root_moisture_threshold:.1f}%.')
            if not weather.get('available'): reasons.append('Weather is unavailable; no weather-based adjustment was applied.')
    else: reasons.append(f'Root-zone moisture {root_value:.1f}% is at or above the configured threshold.')
    if vpd is not None: reasons.append(f'VPD is {vpd:.2f} kPa ({vpd_band(vpd)} band); secondary signal only.')
    publish_result = None
    if execute and should_water:
        duration=settings.default_water_seconds
        command_id=str(uuid.uuid4())
        result=publish_water(plant_id,duration)
        publish_result=result
        estimated=round(duration*settings.flow_ml_per_second,1) if settings.flow_ml_per_second else None
        with db_session() as db:
            db.execute('INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,estimated_water_ml,command_id,status) VALUES(?,?,?,?,?,?,?)',(plant_id,datetime.now(timezone.utc).isoformat(),'auto',duration,estimated,command_id,'queued' if result['published'] else 'not_sent'))
        reasons.append(result['message'])
    decision='water' if should_water else 'skip'
    now=datetime.now(timezone.utc).isoformat()
    with db_session() as db:
        db.execute('INSERT INTO decisions(plant_id,created_at,source,decision,reason,readings_json,vpd_kpa,weather_json,vision_json,command_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(plant_id,now,'auto',decision,' '.join(reasons),json.dumps(readings),vpd,json.dumps(weather),None,None))
    return {'plant_id':plant_id,'created_at':now,'decision':decision,'should_water':should_water,'executed':bool(publish_result and publish_result.get('published')),'command_published':bool(publish_result and publish_result.get('published')),'reason':' '.join(reasons),'readings':readings,'vpd_kpa':vpd,'vpd_band':vpd_band(vpd),'weather':weather}
