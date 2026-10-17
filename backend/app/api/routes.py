from fastapi import APIRouter, HTTPException, Request, Header, Query
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime, timezone
import json
from app.core.config import settings
from app.db.database import db_session
from app.schemas import PlantCreate, PlantUpdate, ModeUpdate, WaterRequest, ChatRequest, TelemetryIngest
from app.services.telemetry import latest_readings, history, record_reading
from app.services.photos import save_photo, latest_photo
from app.services.decision_engine import evaluate_plant
from app.services.mqtt_service import publish_water
from app.services.weather import get_weather
from app.services.vpd import calculate_vpd, vpd_band
from app.services.analytics import dashboard_summary
from app.services.diary import create_daily_entry
from app.services.gemini import ask_gemini_about_plant, analyze_plant_photo

router=APIRouter()

def get_plant_or_404(plant_id):
    with db_session() as db: row=db.execute('SELECT * FROM plants WHERE plant_id=?',(plant_id,)).fetchone()
    if not row: raise HTTPException(404,'Plant not found')
    return dict(row)

@router.get('/health')
def health():
    from app.services.gemini import load_profiles
    profiles = load_profiles()
    return {'status':'ok','service':settings.app_name,'mqtt_enabled':settings.mqtt_enabled,
            'gemini_enabled':settings.gemini_enabled, 'gemini_configured':bool((settings.gemini_chat_api_key or settings.gemini_android_api_key or settings.gemini_ios_api_key or settings.gemini_api_key).strip()),
            'auto_vision_analysis':settings.auto_vision_analysis, 'auto_decisions_enabled':settings.auto_decisions_enabled,
            'plant_profiles_count':sum(1 for k,v in profiles.items() if not k.startswith('_') and isinstance(v,dict))}

@router.get('/debug')
def debug():
    import traceback, sys, os as _os
    from app.core.config import is_serverless
    db_ok = False; db_error = None
    plants_count = None
    try:
        with db_session() as db:
            row = db.execute('SELECT COUNT(*) as c FROM plants').fetchone()
            plants_count = row['c']
        db_ok = True
    except Exception:
        db_error = traceback.format_exc()
    return {
        'status': 'ok' if db_ok else 'error',
        'is_serverless': is_serverless,
        'database_path': settings.database_path,
        'database_ok': db_ok,
        'database_error': db_error,
        'plants_count': plants_count,
        'env_indicators': [k for k in _os.environ.keys() if 'VERCEL' in k or 'AWS' in k or 'LAMBDA' in k],
        'python': sys.version,
    }

@router.get('/plants')
def list_plants():
    with db_session() as db: rows=db.execute('SELECT * FROM plants ORDER BY created_at').fetchall()
    return [dict(r) for r in rows]

@router.get('/plant-profiles')
def plant_profiles():
    from app.services.gemini import load_profiles
    return load_profiles()

@router.get('/plant-knowledge')
def search_plant_knowledge(q: str = Query(default='', max_length=100), limit: int = Query(default=30, ge=1, le=100)):
    """Search the local SQLite catalog; works offline and includes provenance per record."""
    term = q.strip().casefold()
    with db_session() as db:
        rows = db.execute('SELECT * FROM plant_knowledge ORDER BY common_name LIMIT 1000').fetchall()
    results = []
    for row in rows:
        item = dict(row)
        aliases = json.loads(item.pop('aliases_json') or '[]')
        payload = json.loads(item.pop('data_json') or '{}')
        haystack = ' '.join([item.get('slug',''), item.get('common_name',''), item.get('scientific_name',''), *[str(a) for a in aliases]]).casefold()
        if term and term not in haystack:
            continue
        item['aliases'] = aliases
        item['profile'] = payload
        results.append(item)
        if len(results) >= limit:
            break
    return {'count':len(results),'query':q,'offline':True,'results':results}

@router.get('/plant-knowledge/{slug}')
def plant_knowledge_detail(slug: str):
    with db_session() as db: row = db.execute('SELECT * FROM plant_knowledge WHERE slug=?',(slug,)).fetchone()
    if not row: raise HTTPException(404,'Plant knowledge record not found')
    item = dict(row); item['aliases'] = json.loads(item.pop('aliases_json') or '[]'); item['profile'] = json.loads(item.pop('data_json') or '{}')
    return item

@router.post('/plants',status_code=201)
def create_plant(body: PlantCreate):
    if body.ideal_moisture_min > body.ideal_moisture_max: raise HTTPException(422,'Minimum moisture must not exceed maximum')
    now=datetime.now(timezone.utc).isoformat()
    try:
        with db_session() as db:
            db.execute('INSERT INTO plants(plant_id,name,species,growth_stage,species_source,ideal_moisture_min,ideal_moisture_max,light_needs,notes,mode,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(body.plant_id,body.name,body.species,body.growth_stage,'manual' if body.species.strip() else 'unknown',body.ideal_moisture_min,body.ideal_moisture_max,body.light_needs,body.notes,'auto',now))
    except Exception as exc: raise HTTPException(409,'Plant ID already exists or could not be saved') from exc
    return get_plant_or_404(body.plant_id)

@router.patch('/plants/{plant_id}')
def update_plant(plant_id: str, body: PlantUpdate):
    current=get_plant_or_404(plant_id); updates=body.model_dump(exclude_unset=True)
    merged={**current,**updates}
    if 'species' in updates:
        updates['species_source'] = 'manual' if (updates.get('species') or '').strip() else 'unknown'
        merged['species_source'] = updates['species_source']
    if merged['ideal_moisture_min'] > merged['ideal_moisture_max']: raise HTTPException(422,'Minimum moisture must not exceed maximum')
    if not updates: return current
    with db_session() as db:
        db.execute('UPDATE plants SET '+','.join(f'{k}=?' for k in updates)+' WHERE plant_id=?',(*updates.values(),plant_id))
    return get_plant_or_404(plant_id)

@router.get('/plants/{plant_id}/overview')
def overview(plant_id: str):
    get_plant_or_404(plant_id); readings=latest_readings(plant_id); temp=readings.get('temperature_c'); hum=readings.get('humidity_pct')
    vpd=calculate_vpd(temp['value'] if temp and temp['fresh'] else None,hum['value'] if hum and hum['fresh'] else None)
    return {'plant':get_plant_or_404(plant_id),'readings':readings,'vpd_kpa':vpd,'vpd_band':vpd_band(vpd),'weather':get_weather(plant_id),'photo':latest_photo(plant_id),'analytics':dashboard_summary(plant_id)}

@router.get('/plants/{plant_id}/readings/latest')
def readings_latest(plant_id: str): get_plant_or_404(plant_id); return latest_readings(plant_id)

@router.get('/plants/{plant_id}/readings/history')
def readings_history(plant_id: str, metric: str|None=None, limit: int=200):
    get_plant_or_404(plant_id)
    if not 1 <= limit <= 1000: raise HTTPException(422,'limit must be 1..1000')
    return history(plant_id,metric,limit)

@router.post('/plants/{plant_id}/telemetry', status_code=201)
def ingest_plant_telemetry(
    plant_id: str,
    body: TelemetryIngest,
    x_device_token: str | None = Header(default=None, alias='X-Device-Token')
):
    get_plant_or_404(plant_id)
    if settings.device_upload_token and x_device_token != settings.device_upload_token:
        raise HTTPException(401, 'Invalid device upload token')
    recorded = []
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(422, 'No telemetry metrics provided')
    for metric, val in data.items():
        if val is not None:
            topic = f'plants/{plant_id}/{metric}'
            rec = record_reading(plant_id, metric, val, topic)
            recorded.append(rec)
    return {'status': 'recorded', 'plant_id': plant_id, 'count': len(recorded), 'readings': recorded}

@router.get('/plants/{plant_id}/weather')
def weather(plant_id: str, refresh: bool=False): get_plant_or_404(plant_id); return get_weather(plant_id,force=refresh)

@router.post('/plants/{plant_id}/decision')
def decision(plant_id: str, execute: bool=False):
    get_plant_or_404(plant_id)
    if execute and not settings.auto_decisions_enabled:
        raise HTTPException(403,'Pump execution is disabled. Bench-test first, then explicitly set AUTO_DECISIONS_ENABLED=true.')
    return evaluate_plant(plant_id,execute=execute)

@router.patch('/plants/{plant_id}/mode')
def set_mode(plant_id: str, body: ModeUpdate):
    get_plant_or_404(plant_id)
    with db_session() as db: db.execute('UPDATE plants SET mode=? WHERE plant_id=?',(body.mode,plant_id))
    return {'plant_id':plant_id,'mode':body.mode}

@router.post('/plants/{plant_id}/water')
def manual_water(plant_id: str, body: WaterRequest):
    get_plant_or_404(plant_id)
    # API schema clamps duration to 1..15 seconds; board firmware must keep its own hard cutoff.
    import uuid
    command_id=str(uuid.uuid4()); result=publish_water(plant_id,body.duration_seconds)
    estimated=round(body.duration_seconds*settings.flow_ml_per_second,1) if settings.flow_ml_per_second else None
    now=datetime.now(timezone.utc).isoformat()
    with db_session() as db:
        db.execute('INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,estimated_water_ml,command_id,status) VALUES(?,?,?,?,?,?,?)',(plant_id,now,'manual',body.duration_seconds,estimated,command_id,'queued' if result['published'] else 'not_sent'))
        db.execute('INSERT INTO decisions(plant_id,created_at,source,decision,reason,readings_json,command_id) VALUES(?,?,?,?,?,?,?)',(plant_id,now,'manual','water_requested',result['message'],'{}',command_id))
    return {'command_id':command_id,'plant_id':plant_id,'duration_seconds':body.duration_seconds,**result,'estimated_water_ml':estimated}

@router.get('/plants/{plant_id}/photos/latest')
def photo_latest(plant_id: str): get_plant_or_404(plant_id); p=latest_photo(plant_id); return p or {'photo':None}

@router.post('/plants/{plant_id}/photos/analyze')
def analyze_latest_photo(plant_id: str, request: Request):
    get_plant_or_404(plant_id)
    p=latest_photo(plant_id)
    if not p: raise HTTPException(404, 'No plant photo has been uploaded yet')
    with db_session() as db: row=db.execute('SELECT file_path FROM photos WHERE plant_id=? ORDER BY id DESC LIMIT 1',(plant_id,)).fetchone()
    client_platform = request.headers.get('x-greetopia-platform', 'web').lower()
    if client_platform not in ('android', 'ios', 'web'): client_platform = 'web'
    try: result=analyze_plant_photo(row['file_path'], plant_id, client_platform)
    except RuntimeError as exc: raise HTTPException(503, str(exc)) from exc
    with db_session() as db:
        db.execute('UPDATE photos SET vision_json=? WHERE plant_id=? AND capture_id=?',(json.dumps(result,ensure_ascii=False),plant_id,p['capture_id']))
        plant=db.execute('SELECT species,species_source FROM plants WHERE plant_id=?',(plant_id,)).fetchone()
        guess=result.get('species_guess') or result.get('common_name')
        confidence=result.get('confidence')
        if guess and confidence is not None and confidence >= 0.80 and plant and plant['species_source'] not in ('manual',):
            db.execute("UPDATE plants SET species=?,species_source='ai_suggested' WHERE plant_id=?",(str(guess)[:100],plant_id))
    return {'plant_id':plant_id,'vision':result,'species_updated':bool(guess and confidence is not None and confidence >= 0.80 and plant and plant['species_source'] != 'manual')}

@router.post('/upload',status_code=201)
async def upload_photo(request: Request, x_plant_id: str|None=Header(default=None,alias='X-Plant-Id'), x_device_token: str|None=Header(default=None,alias='X-Device-Token')):
    # Keep the original raw-JPEG + X-Plant-Id contract for the ESP32-CAM.
    if not x_plant_id: raise HTTPException(400,'Missing X-Plant-Id header')
    get_plant_or_404(x_plant_id)
    if settings.device_upload_token and x_device_token != settings.device_upload_token:
        raise HTTPException(401,'Invalid device upload token')
    content_type=request.headers.get('content-type','image/jpeg')
    chunks=[]; total=0
    async for chunk in request.stream():
        total += len(chunk)
        if total > settings.max_photo_bytes:
            raise HTTPException(413,'Image exceeds configured size limit')
        chunks.append(chunk)
    body=b''.join(chunks)
    try: result=save_photo(x_plant_id,body,content_type)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    # Vision analysis is deliberately opt-in: the ESP32-CAM sleeps for ~30 minutes,
    # so analyzing every upload could consume API quota without user confirmation.
    if settings.auto_vision_analysis and settings.gemini_enabled and (settings.gemini_api_key or settings.gemini_android_api_key or settings.gemini_ios_api_key).strip():
        try:
            image_path=str(Path(settings.photo_dir)/x_plant_id/Path(result['url']).name)
            vision=analyze_plant_photo(image_path, x_plant_id)
            with db_session() as db:
                db.execute('UPDATE photos SET vision_json=? WHERE plant_id=? AND capture_id=?',(json.dumps(vision,ensure_ascii=False),x_plant_id,result['capture_id']))
                plant=db.execute('SELECT species_source FROM plants WHERE plant_id=?',(x_plant_id,)).fetchone()
                guess=vision.get('species_guess') or vision.get('common_name'); confidence=vision.get('confidence')
                if guess and confidence is not None and confidence >= 0.80 and plant and plant['species_source'] != 'manual':
                    db.execute("UPDATE plants SET species=?,species_source='ai_suggested' WHERE plant_id=?",(str(guess)[:100],x_plant_id))
            result['vision']=vision
        except Exception as exc:
            # Keep camera ingestion working if AI is down or the provider quota is exhausted.
            result['vision_error']=str(exc)[:300]
    return {'status':'stored','vision_analysis_enabled':settings.auto_vision_analysis,**result}

@router.get('/photos/{plant_id}/{filename}')
def serve_photo(plant_id: str, filename: str):
    if not all(c.isalnum() or c in '_-' for c in plant_id) or Path(filename).name != filename or not filename.endswith('.jpg'): raise HTTPException(400,'Invalid path')
    path=Path(settings.photo_dir)/plant_id/filename
    if not path.is_file(): raise HTTPException(404,'Photo not found')
    return FileResponse(path,media_type='image/jpeg')

@router.get('/plants/{plant_id}/analytics')
def analytics(plant_id: str): get_plant_or_404(plant_id); return dashboard_summary(plant_id)

@router.get('/plants/{plant_id}/decisions')
def list_decisions(plant_id: str, limit: int=20):
    get_plant_or_404(plant_id)
    with db_session() as db: rows=db.execute('SELECT * FROM decisions WHERE plant_id=? ORDER BY id DESC LIMIT ?',(plant_id,max(1,min(limit,100)))).fetchall()
    return [dict(r) for r in rows]

@router.get('/plants/{plant_id}/diary')
def diary_list(plant_id: str):
    get_plant_or_404(plant_id)
    with db_session() as db: rows=db.execute('SELECT * FROM diary_entries WHERE plant_id=? ORDER BY day DESC LIMIT 30',(plant_id,)).fetchall()
    return [dict(r) for r in rows]

@router.post('/plants/{plant_id}/diary/generate')
def diary_generate(plant_id: str): get_plant_or_404(plant_id); return create_daily_entry(plant_id)

@router.post('/plants/{plant_id}/chat')
def chat(plant_id: str, body: ChatRequest):
    get_plant_or_404(plant_id)
    try: return ask_gemini_about_plant(plant_id,body.question)
    except ValueError as exc: raise HTTPException(404,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
