from datetime import datetime, timezone, timedelta
import httpx
from app.core.config import settings
from app.db.database import db_session

def get_weather(plant_id: str, force: bool=False):
    with db_session() as db:
        row=db.execute('SELECT * FROM weather_snapshots WHERE plant_id=?',(plant_id,)).fetchone()
    if row and not force:
        checked=datetime.fromisoformat(row['checked_at'])
        if datetime.now(timezone.utc)-checked < timedelta(hours=1):
            return {'plant_id':plant_id,'checked_at':row['checked_at'],'rain_probability':row['rain_probability'],'rain_mm':row['rain_mm'],'source':row['source'],'available':True}
    if not settings.openweather_api_key or settings.openweather_lat is None or settings.openweather_lon is None:
        return {'plant_id':plant_id,'checked_at':None,'rain_probability':None,'rain_mm':None,'source':'not_configured','available':False}
    try:
        with httpx.Client(timeout=6) as client:
            res=client.get('https://api.openweathermap.org/data/2.5/forecast',params={'lat':settings.openweather_lat,'lon':settings.openweather_lon,'appid':settings.openweather_api_key,'units':'metric'})
            res.raise_for_status(); data=res.json()
        forecasts=data.get('list',[])[:8]
        probs=[float(x.get('pop',0)) for x in forecasts]
        rain=sum(float(x.get('rain',{}).get('3h',0)) for x in forecasts)
        probability=max(probs) if probs else None
        checked=datetime.now(timezone.utc).isoformat()
        with db_session() as db:
            db.execute('INSERT INTO weather_snapshots(plant_id,checked_at,rain_probability,rain_mm,source) VALUES(?,?,?,?,?) ON CONFLICT(plant_id) DO UPDATE SET checked_at=excluded.checked_at,rain_probability=excluded.rain_probability,rain_mm=excluded.rain_mm,source=excluded.source',(plant_id,checked,probability,rain,'openweathermap'))
        return {'plant_id':plant_id,'checked_at':checked,'rain_probability':probability,'rain_mm':round(rain,2),'source':'openweathermap','available':True}
    except Exception as exc:
        return {'plant_id':plant_id,'checked_at':None,'rain_probability':None,'rain_mm':None,'source':'error','available':False,'error':str(exc)}
