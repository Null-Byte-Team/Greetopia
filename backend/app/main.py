from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.db.database import init_db
from app.api.routes import router, upload_photo
from app.services.mqtt_service import start_mqtt, stop_mqtt, mqtt_status
from pathlib import Path
from app.db.database import db_session
from app.services.decision_engine import evaluate_plant

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s')

async def automatic_decision_loop():
    # Deliberately opt-in: no automatic pump commands until AUTO_DECISIONS_ENABLED=true.
    while True:
        await asyncio.sleep(max(1, settings.decision_interval_minutes) * 60)
        if not settings.auto_decisions_enabled:
            continue
        try:
            with db_session() as db:
                plants = db.execute("SELECT plant_id FROM plants WHERE mode='auto'").fetchall()
            for row in plants:
                await asyncio.to_thread(evaluate_plant, row['plant_id'], True)
        except Exception:
            logging.exception('Automatic decision cycle failed')

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); start_mqtt()
    task = asyncio.create_task(automatic_decision_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    stop_mqtt()

app=FastAPI(title=settings.app_name,version='0.1.0',description='Prototype API for ESP32 smart irrigation.',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_list,allow_credentials=False,allow_methods=['GET','POST','PATCH','OPTIONS'],allow_headers=['*'])
app.include_router(router,prefix=settings.api_prefix)
# Backwards-compatible root path required by the original ESP32-CAM firmware.
app.add_api_route('/upload', upload_photo, methods=['POST'], status_code=201, include_in_schema=False)
@app.get('/')
def root():
    return {'service': settings.app_name, 'docs': '/docs', 'api_prefix': settings.api_prefix, 'health': '/health/ready'}

@app.get('/health/live', tags=['health'])
def health_live():
    """Liveness probe: process is running. Does not depend on external services."""
    return {'status': 'alive', 'service': settings.app_name}

@app.get('/health/ready', tags=['health'])
def health_ready():
    """Readiness probe: verify the database works; report MQTT as a dependency status."""
    from datetime import datetime, timezone
    database = {'ok': False}
    try:
        with db_session() as db:
            db.execute('SELECT 1').fetchone()
        database = {'ok': True}
    except Exception:
        logging.getLogger(__name__).exception('Readiness database check failed')
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={
            'status': 'not_ready', 'database': database,
            'mqtt': mqtt_status(), 'checked_at': datetime.now(timezone.utc).isoformat(),
        })
    mqtt = mqtt_status()
    # MQTT degradation is reported, not used to restart the API endlessly while a broker is offline.
    return {
        'status': 'ready', 'service': settings.app_name,
        'database': database, 'mqtt': mqtt,
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
