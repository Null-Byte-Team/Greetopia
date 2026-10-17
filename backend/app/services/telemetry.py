from datetime import datetime, timezone, timedelta
from app.db.database import db_session
from app.core.config import settings

ALLOWED_METRICS = {'soil/surface':'soil_surface','soil/mid':'soil_mid','soil/root':'soil_root','temp':'temperature_c','humidity':'humidity_pct','status':'device_status','leaf_wetness':'leaf_wetness_pct'}

def utcnow(): return datetime.now(timezone.utc)

def parse_payload(metric: str, payload: str):
    if metric == 'device_status':
        value = payload.strip().lower()
        if value not in {'idle','watering'}: raise ValueError('Invalid status')
        return value
    value = float(payload.strip())
    if metric in {'soil_surface','soil_mid','soil_root','leaf_wetness_pct'}:
        if not 0 <= value <= 100: raise ValueError('Percent reading must be 0..100')
    elif metric == 'humidity':
        if not 0 <= value <= 100: raise ValueError('Humidity must be 0..100')
    elif metric == 'temp' and not -40 <= value <= 85:
        raise ValueError('Temperature out of range')
    return value

def record_reading(plant_id: str, metric: str, value, topic: str, received_at=None):
    received_at = (received_at or utcnow()).isoformat()
    with db_session() as db:
        db.execute('INSERT INTO readings(plant_id,metric,value,received_at,topic) VALUES(?,?,?,?,?)', (plant_id, metric, value, received_at, topic))
        # Keep a bounded local history per metric for prototype installations.
        db.execute('DELETE FROM readings WHERE id IN (SELECT id FROM readings WHERE plant_id=? AND metric=? ORDER BY id DESC LIMIT -1 OFFSET 5000)', (plant_id, metric))
    return {'plant_id':plant_id,'metric':metric,'value':value,'received_at':received_at,'topic':topic}

def ingest_mqtt(topic: str, payload: bytes | str):
    parts = topic.split('/')
    if len(parts) < 3 or parts[0] != 'plants': raise ValueError('Unexpected topic')
    plant_id = parts[1]
    suffix = '/'.join(parts[2:])
    if not plant_id or not all(c.isalnum() or c in '_-' for c in plant_id): raise ValueError('Invalid plant id')
    metric = ALLOWED_METRICS.get(suffix)
    if not metric: raise ValueError(f'Unsupported topic: {suffix}')
    text = payload.decode('utf-8') if isinstance(payload, bytes) else str(payload)
    value = parse_payload(metric, text)
    return record_reading(plant_id, metric, value, topic)

def latest_readings(plant_id: str):
    with db_session() as db:
        rows = db.execute("""SELECT r.* FROM readings r JOIN (SELECT metric, MAX(id) id FROM readings WHERE plant_id=? GROUP BY metric) x ON x.id=r.id""", (plant_id,)).fetchall()
    now = utcnow()
    result = {}
    for r in rows:
        age = (now - datetime.fromisoformat(r['received_at'])).total_seconds()
        result[r['metric']] = {'value':r['value'],'received_at':r['received_at'],'age_seconds':max(0, round(age)), 'fresh':age <= settings.sensor_stale_minutes*60}
    return result

def history(plant_id: str, metric: str | None = None, limit: int = 200):
    with db_session() as db:
        if metric:
            rows=db.execute('SELECT metric,value,received_at FROM readings WHERE plant_id=? AND metric=? ORDER BY id DESC LIMIT ?', (plant_id,metric,limit)).fetchall()
        else:
            rows=db.execute('SELECT metric,value,received_at FROM readings WHERE plant_id=? ORDER BY id DESC LIMIT ?', (plant_id,limit)).fetchall()
    return [dict(r) for r in reversed(rows)]
