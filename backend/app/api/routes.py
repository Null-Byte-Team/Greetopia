import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.core.config import settings
from app.db.database import db_session
from app.schemas import ChatRequest, ModeUpdate, PlantCreate, PlantUpdate, TelemetryIngest, WaterRequest
from app.services import device_state
from app.services.analytics import dashboard_summary
from app.services.auth import (current_user, rate_limit, require_admin, require_device, require_operator,
                               verify_photo_sig)
from app.services.chat import answer_question as answer_from_data
from app.services.decision_engine import evaluate_plant
from app.services.diary import create_daily_entry
from app.services.gemini import analyze_plant_photo, ask_gemini_about_plant
from app.services.irrigation import CommandRejected, request_watering
from app.services.mqtt_service import mqtt_status
from app.services.photos import latest_photo, resolve_photo_path, save_photo
from app.services.telemetry import IngestError, history, latest_readings, record_reading
from app.services.vpd import calculate_vpd, vpd_band
from app.services.weather import get_weather

# Public: health + device endpoints (own credential) + signed photo links. Everything else needs a signed-in user.
public = APIRouter()
router = APIRouter(dependencies=[Depends(current_user)])


def get_plant_or_404(plant_id):
    with db_session() as db:
        row = db.execute('SELECT * FROM plants WHERE plant_id=?', (plant_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Plant not found')
    return dict(row)


def _ai_available() -> bool:
    return settings.gemini_enabled and bool((settings.gemini_chat_api_key or settings.gemini_android_api_key
                                              or settings.gemini_ios_api_key or settings.gemini_api_key).strip())


# ------------------------------------------------------------------ public
@public.get('/health')
def health():
    """Minimal public status. Details are available to administrators at /health/details."""
    return {'status': 'ok', 'service': settings.app_name, 'mqtt_enabled': settings.mqtt_enabled,
            'mqtt': mqtt_status(), 'auto_decisions_enabled': settings.auto_decisions_enabled}


@router.get('/health/details')
def health_details(_: dict = Depends(require_admin)):
    from app.services.gemini import load_profiles
    profiles = load_profiles()
    with db_session() as db:
        quarantined = db.execute('SELECT COUNT(*) c FROM quarantine_messages').fetchone()['c']
    return {'mqtt': mqtt_status(include_details=True), 'ai_configured': _ai_available(), 'auto_vision_analysis': settings.auto_vision_analysis,
            'quarantined_messages': quarantined,
            'plant_profiles_count': sum(1 for k, v in profiles.items() if not k.startswith('_') and isinstance(v, dict))}


@public.get('/photos/{plant_id}/{filename}')
def serve_photo(plant_id: str, filename: str, exp: int = 0, sig: str = ''):
    if not all(c.isalnum() or c in '_-' for c in plant_id) or Path(filename).name != filename or not filename.endswith('.jpg'):
        raise HTTPException(400, 'Invalid path')
    if not verify_photo_sig(f'{plant_id}/{filename}', exp, sig):
        raise HTTPException(403, 'Photo link expired or invalid')
    path = resolve_photo_path(f'{plant_id}/{filename}')
    if path is None:
        raise HTTPException(404, 'Photo not found')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=300'})


@public.post('/plants/{plant_id}/telemetry', status_code=201, dependencies=[Depends(require_device)])
def ingest_plant_telemetry(plant_id: str, body: TelemetryIngest):
    """HTTP telemetry fallback for nodes that cannot use MQTT (one-way: this path cannot receive pump commands)."""
    get_plant_or_404(plant_id)
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(422, 'No telemetry metrics provided')
    recorded = []
    try:
        for metric, val in data.items():
            if val is None:
                continue
            if metric == 'device_status':
                device_state.record_status(plant_id, val)
                continue
            recorded.append(record_reading(plant_id, metric, val, f'http/{plant_id}/{metric}'))
    except IngestError as exc:
        raise HTTPException(422, exc.reason) from exc
    return {'status': 'recorded', 'plant_id': plant_id, 'count': len(recorded), 'readings': recorded}


async def upload_photo(request: Request, background: BackgroundTasks, x_plant_id: str | None = Header(default=None, alias='X-Plant-Id')):
    """ESP32-CAM contract: raw JPEG body + X-Plant-Id header (+ X-Device-Token)."""
    require_device(request.headers.get('x-device-token'))
    if not x_plant_id:
        raise HTTPException(400, 'Missing X-Plant-Id header')
    get_plant_or_404(x_plant_id)
    declared = request.headers.get('content-length')
    if declared and declared.isdigit() and int(declared) > settings.max_photo_bytes:
        raise HTTPException(413, 'Image exceeds configured size limit')
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > settings.max_photo_bytes:
            raise HTTPException(413, 'Image exceeds configured size limit')
        chunks.append(chunk)
    try:
        result = await asyncio.to_thread(save_photo, x_plant_id, b''.join(chunks), request.headers.get('content-type', 'image/jpeg'))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result.get('duplicate') and settings.auto_vision_analysis and _ai_available():
        background.add_task(_analyze_in_background, x_plant_id, result['capture_id'])
    return {'status': 'duplicate' if result.get('duplicate') else 'stored', 'vision_analysis_enabled': settings.auto_vision_analysis, **result}


def _analyze_in_background(plant_id: str, capture_id: str):
    """Runs outside the request/event loop; failures are recorded on the photo row, never lost."""
    with db_session() as db:
        row = db.execute('SELECT file_path FROM photos WHERE plant_id=? AND capture_id=?', (plant_id, capture_id)).fetchone()
        db.execute("UPDATE photos SET vision_status='processing' WHERE plant_id=? AND capture_id=?", (plant_id, capture_id))
    try:
        result = analyze_plant_photo(row['file_path'], plant_id)
        status, error, payload = 'done', None, json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        status, error, payload = 'failed', str(exc)[:300], None
    with db_session() as db:
        db.execute('UPDATE photos SET vision_status=?,vision_error=?,vision_json=COALESCE(?,vision_json) WHERE plant_id=? AND capture_id=?',
                   (status, error, payload, plant_id, capture_id))


# ------------------------------------------------------------------ authenticated: read
@router.get('/plants')
def list_plants():
    with db_session() as db:
        rows = db.execute('SELECT * FROM plants ORDER BY created_at').fetchall()
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
        haystack = ' '.join([item.get('slug', ''), item.get('common_name', ''), item.get('scientific_name', ''), *[str(a) for a in aliases]]).casefold()
        if term and term not in haystack:
            continue
        item['aliases'] = aliases
        item['profile'] = payload
        results.append(item)
        if len(results) >= limit:
            break
    return {'count': len(results), 'query': q, 'offline': True, 'results': results}


@router.get('/plant-knowledge/{slug}')
def plant_knowledge_detail(slug: str):
    with db_session() as db:
        row = db.execute('SELECT * FROM plant_knowledge WHERE slug=?', (slug,)).fetchone()
    if not row:
        raise HTTPException(404, 'Plant knowledge record not found')
    item = dict(row)
    item['aliases'] = json.loads(item.pop('aliases_json') or '[]')
    item['profile'] = json.loads(item.pop('data_json') or '{}')
    return item


@router.get('/plants/{plant_id}/overview')
def overview(plant_id: str):
    plant = get_plant_or_404(plant_id)
    readings = latest_readings(plant_id)
    temp, hum = readings.get('temperature_c'), readings.get('humidity_pct')
    vpd = calculate_vpd(temp['value'] if temp and temp['fresh'] else None, hum['value'] if hum and hum['fresh'] else None)
    with db_session() as db:
        last_event = db.execute('SELECT * FROM irrigation_events WHERE plant_id=? ORDER BY id DESC LIMIT 1', (plant_id,)).fetchone()
        alerts = db.execute('SELECT id,kind,severity,message,created_at FROM alerts WHERE plant_id=? AND resolved_at IS NULL ORDER BY id DESC LIMIT 5', (plant_id,)).fetchall()
    return {'plant': plant, 'readings': readings, 'vpd_kpa': vpd, 'vpd_band': vpd_band(vpd), 'weather': get_weather(plant_id),
            'photo': latest_photo(plant_id), 'analytics': dashboard_summary(plant_id), 'device': device_state.device_summary(plant_id),
            'last_event': dict(last_event) if last_event else None, 'alerts': [dict(a) for a in alerts],
            'ml': {'available': False, 'reason': 'No validated stress-prediction model has been trained on real data yet.'}}


@router.get('/plants/{plant_id}/readings/latest')
def readings_latest(plant_id: str):
    get_plant_or_404(plant_id)
    return latest_readings(plant_id)


@router.get('/plants/{plant_id}/readings/history')
def readings_history(plant_id: str, metric: str | None = None, limit: int = Query(default=200, ge=1, le=5000),
                     start: str | None = None, end: str | None = None):
    get_plant_or_404(plant_id)
    for value in (start, end):
        if value:
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(422, 'start/end must be ISO-8601 timestamps') from exc
    return history(plant_id, metric, limit, start, end)


@router.get('/plants/{plant_id}/weather')
def weather(plant_id: str, refresh: bool = False):
    get_plant_or_404(plant_id)
    return get_weather(plant_id, force=refresh)


@router.get('/plants/{plant_id}/device')
def device(plant_id: str):
    get_plant_or_404(plant_id)
    return device_state.device_summary(plant_id)


@router.get('/plants/{plant_id}/events')
def irrigation_events(plant_id: str, limit: int = Query(default=20, ge=1, le=200)):
    get_plant_or_404(plant_id)
    device_state.sweep_unconfirmed()
    with db_session() as db:
        rows = db.execute('SELECT * FROM irrigation_events WHERE plant_id=? ORDER BY id DESC LIMIT ?', (plant_id, limit)).fetchall()
    return [dict(r) for r in rows]


@router.get('/plants/{plant_id}/alerts')
def list_alerts(plant_id: str, limit: int = Query(default=20, ge=1, le=100)):
    get_plant_or_404(plant_id)
    with db_session() as db:
        rows = db.execute('SELECT * FROM alerts WHERE plant_id=? ORDER BY id DESC LIMIT ?', (plant_id, limit)).fetchall()
    return [dict(r) for r in rows]


@router.get('/plants/{plant_id}/photos/latest')
def photo_latest(plant_id: str):
    get_plant_or_404(plant_id)
    return latest_photo(plant_id) or {'photo': None}


@router.get('/plants/{plant_id}/analytics')
def analytics(plant_id: str):
    get_plant_or_404(plant_id)
    return dashboard_summary(plant_id)


@router.get('/plants/{plant_id}/decisions')
def list_decisions(plant_id: str, limit: int = Query(default=20, ge=1, le=100)):
    get_plant_or_404(plant_id)
    with db_session() as db:
        rows = db.execute('SELECT * FROM decisions WHERE plant_id=? ORDER BY id DESC LIMIT ?', (plant_id, limit)).fetchall()
    return [dict(r) for r in rows]


@router.get('/plants/{plant_id}/diary')
def diary_list(plant_id: str):
    get_plant_or_404(plant_id)
    with db_session() as db:
        rows = db.execute('SELECT * FROM diary_entries WHERE plant_id=? ORDER BY day DESC LIMIT 30', (plant_id,)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ authenticated: operator actions
@router.post('/plants', status_code=201)
def create_plant(body: PlantCreate, user: dict = Depends(require_operator)):
    if body.ideal_moisture_min >= body.ideal_moisture_max:
        raise HTTPException(422, 'Minimum moisture must be lower than maximum')
    now = datetime.now(timezone.utc).isoformat()
    try:
        with db_session() as db:
            db.execute('INSERT INTO plants(plant_id,name,species,growth_stage,species_source,ideal_moisture_min,ideal_moisture_max,light_needs,notes,mode,created_at,latitude,longitude) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (body.plant_id, body.name, body.species, body.growth_stage, 'manual' if body.species.strip() else 'unknown',
                        body.ideal_moisture_min, body.ideal_moisture_max, body.light_needs, body.notes, 'auto', now, body.latitude, body.longitude))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Plant ID already exists') from exc
    return get_plant_or_404(body.plant_id)


@router.patch('/plants/{plant_id}')
def update_plant(plant_id: str, body: PlantUpdate, user: dict = Depends(require_operator)):
    current = get_plant_or_404(plant_id)
    updates = body.model_dump(exclude_unset=True)
    merged = {**current, **updates}
    if 'species' in updates:  # species becomes authoritative only through an explicit user action
        updates['species_source'] = 'manual' if (updates.get('species') or '').strip() else 'unknown'
    if merged['ideal_moisture_min'] >= merged['ideal_moisture_max']:
        raise HTTPException(422, 'Minimum moisture must be lower than maximum')
    if not updates:
        return current
    with db_session() as db:
        db.execute('UPDATE plants SET ' + ','.join(f'{k}=?' for k in updates) + ' WHERE plant_id=?', (*updates.values(), plant_id))
    return get_plant_or_404(plant_id)


@router.patch('/plants/{plant_id}/mode')
def set_mode(plant_id: str, body: ModeUpdate, user: dict = Depends(require_operator)):
    get_plant_or_404(plant_id)
    with db_session() as db:
        db.execute('UPDATE plants SET mode=? WHERE plant_id=?', (body.mode, plant_id))
    return {'plant_id': plant_id, 'mode': body.mode}


@router.post('/plants/{plant_id}/decision')
def decision(plant_id: str, execute: bool = False, user: dict = Depends(require_operator)):
    get_plant_or_404(plant_id)
    if execute and not settings.auto_decisions_enabled:
        raise HTTPException(403, 'Pump execution is disabled. Bench-test first, then explicitly set AUTO_DECISIONS_ENABLED=true.')
    return evaluate_plant(plant_id, execute=execute, requested_by=user['email'])


@router.post('/plants/{plant_id}/water')
def manual_water(plant_id: str, body: WaterRequest, user: dict = Depends(require_operator)):
    get_plant_or_404(plant_id)
    try:
        result = request_watering(plant_id, body.duration_seconds, 'manual', user['email'], body.reason)
    except CommandRejected as exc:
        raise HTTPException(exc.http_status, {'code': exc.code, 'message': exc.message}) from exc
    with db_session() as db:
        db.execute('INSERT INTO decisions(plant_id,created_at,source,decision,reason,readings_json,command_id,engine_version,duration_s,executed) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (plant_id, datetime.now(timezone.utc).isoformat(), 'manual', 'water_requested', f"{user['email']}: {body.reason}. {result['message']}",
                    '{}', result['command_id'], 'manual', body.duration_seconds, int(result['published'])))
    return result


@router.post('/plants/{plant_id}/photos/analyze')
def analyze_latest_photo(plant_id: str, request: Request, user: dict = Depends(require_operator)):
    get_plant_or_404(plant_id)
    rate_limit(f'ai:{user["id"]}', settings.ai_rate_limit_per_minute)
    p = latest_photo(plant_id)
    if not p:
        raise HTTPException(404, 'No plant photo has been uploaded yet')
    with db_session() as db:
        row = db.execute('SELECT file_path FROM photos WHERE plant_id=? ORDER BY id DESC LIMIT 1', (plant_id,)).fetchone()
    platform = request.headers.get('x-greetopia-platform', 'web').lower()
    if platform not in ('android', 'ios', 'web'):
        platform = 'web'
    try:
        result = analyze_plant_photo(row['file_path'], plant_id, platform)
    except RuntimeError as exc:
        with db_session() as db:
            db.execute("UPDATE photos SET vision_status='failed',vision_error=? WHERE plant_id=? AND capture_id=?", (str(exc)[:300], plant_id, p['capture_id']))
        raise HTTPException(503, str(exc)) from exc
    with db_session() as db:
        db.execute("UPDATE photos SET vision_json=?,vision_status='done',vision_error=NULL WHERE plant_id=? AND capture_id=?",
                   (json.dumps(result, ensure_ascii=False), plant_id, p['capture_id']))
    # The species is a CANDIDATE only. It is never written to the plant profile without explicit user confirmation.
    return {'plant_id': plant_id, 'vision': result, 'species_updated': False}


@router.post('/plants/{plant_id}/diary/generate')
def diary_generate(plant_id: str, user: dict = Depends(require_operator)):
    get_plant_or_404(plant_id)
    return create_daily_entry(plant_id)


@router.post('/plants/{plant_id}/chat')
def chat(plant_id: str, body: ChatRequest, user: dict = Depends(current_user)):
    get_plant_or_404(plant_id)
    rate_limit(f'ai:{user["id"]}', settings.ai_rate_limit_per_minute)
    try:
        return {**ask_gemini_about_plant(plant_id, body.question), 'mode': 'llm'}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError:
        # AI provider missing/failing: answer from stored data only, and say so.
        return {**answer_from_data(plant_id, body.question), 'mode': 'rule_based'}
