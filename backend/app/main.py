import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend root is on sys.path regardless of execution directory
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth_routes import auth_router
from app.api.routes import public, router, upload_photo
from app.core.config import is_serverless, settings, validate_settings
from app.db.database import db_session, init_db
from app.services import device_state
from app.services.decision_engine import evaluate_plant
from app.services.mqtt_service import mqtt_status, start_mqtt, stop_mqtt
from app.services.telemetry import prune_old_readings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger(__name__)


async def automatic_decision_loop():
    """Evaluates every Auto plant. Pump commands are only sent when AUTO_DECISIONS_ENABLED=true."""
    await asyncio.sleep(30)
    while True:
        try:
            with db_session() as db:
                plants = db.execute("SELECT plant_id FROM plants WHERE mode='auto'").fetchall()
            for row in plants:
                # Decisions are always logged (advisory); commands are executed only when explicitly enabled.
                await asyncio.to_thread(evaluate_plant, row['plant_id'], settings.auto_decisions_enabled)
        except Exception:
            log.exception('Automatic decision cycle failed')
        await asyncio.sleep(max(1, settings.decision_interval_minutes) * 60)


async def maintenance_loop():
    """Marks unconfirmed commands and applies age-based retention. Never re-sends a command."""
    last_prune = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        try:
            await asyncio.to_thread(device_state.sweep_unconfirmed)
            if (datetime.now(timezone.utc) - last_prune).total_seconds() > 86400:
                await asyncio.to_thread(prune_old_readings)
                last_prune = datetime.now(timezone.utc)
        except Exception:
            log.exception('Maintenance cycle failed')
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_settings()
    if is_serverless:
        log.error('Serverless runtime detected: MQTT, the scheduler and SQLite persistence will NOT work. Deploy as a long-running service.')
    init_db()
    start_mqtt()
    tasks = [asyncio.create_task(automatic_decision_loop()), asyncio.create_task(maintenance_loop())]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        stop_mqtt()


app = FastAPI(title=settings.app_name, version='1.0.0', description='Greetopia smart irrigation API.', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False,
                   allow_methods=['GET', 'POST', 'PATCH', 'OPTIONS'], allow_headers=['Authorization', 'Content-Type', 'X-Greetopia-Platform'])
app.include_router(public, prefix=settings.api_prefix)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
# Device-facing endpoints (ESP32-CAM contract: POST /upload with X-Plant-Id). Authenticated with X-Device-Token.
app.add_api_route('/upload', upload_photo, methods=['POST'], status_code=201, include_in_schema=False)
app.add_api_route(settings.api_prefix + '/upload', upload_photo, methods=['POST'], status_code=201, include_in_schema=False)


@app.get('/')
def root():
    return {'service': settings.app_name, 'api_prefix': settings.api_prefix, 'health': '/health/ready'}


@app.get('/health/live', tags=['health'])
def health_live():
    return {'status': 'alive', 'service': settings.app_name}


@app.get('/health/ready', tags=['health'])
def health_ready():
    try:
        with db_session() as db:
            db.execute('SELECT 1').fetchone()
    except Exception:
        log.exception('Readiness database check failed')
        return JSONResponse(status_code=503, content={'status': 'not_ready', 'database': {'ok': False}})
    return {'status': 'ready', 'service': settings.app_name, 'database': {'ok': True}, 'mqtt': mqtt_status(),
            'checked_at': datetime.now(timezone.utc).isoformat()}
