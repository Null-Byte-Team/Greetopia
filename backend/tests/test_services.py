import os, tempfile
from pathlib import Path

# Use an isolated database for tests before app imports initialize settings.
tmp=Path(tempfile.mkdtemp())
os.environ['DATABASE_PATH']=str(tmp/'test.db')
os.environ['PHOTO_DIR']=str(tmp/'photos')
os.environ['MQTT_ENABLED']='false'
from app.db.database import init_db
from app.core.config import settings
from app.services.vpd import calculate_vpd, vpd_band
from app.services.telemetry import ingest_mqtt, latest_readings
from app.services.decision_engine import evaluate_plant


def setup_function():
    global tmp
    tmp = Path(tempfile.mkdtemp())
    settings.database_path = str(tmp / 'test.db')
    settings.photo_dir = str(tmp / 'photos')
    init_db()

def test_vpd_valid_and_invalid():
    assert calculate_vpd(25,50) is not None
    assert calculate_vpd(None,50) is None
    assert vpd_band(None)=='unavailable'

def test_ingest_nested_soil_topic():
    ingest_mqtt('plants/plant01/soil/root',b'42')
    assert latest_readings('plant01')['soil_root']['value']==42

def test_invalid_soil_rejected():
    try: ingest_mqtt('plants/plant01/soil/root',b'120')
    except ValueError: pass
    else: raise AssertionError('out of range reading should be rejected')

def test_decision_fails_safe_without_root_data():
    result=evaluate_plant('plant01',execute=False)
    assert result['decision']=='skip'
    assert 'missing or stale' in result['reason']


def test_local_plant_profiles():
    from app.services.gemini import find_profile, load_profiles
    profiles = load_profiles()
    assert "tomato" in profiles
    assert find_profile("طماطم")["common_name"] == "Tomato"
    assert find_profile("Basil")["key"] == "basil"
    assert find_profile("made-up-species") is None

def test_plant_knowledge_catalog_seeded_and_searchable():
    with __import__('app.db.database', fromlist=['db_session']).db_session() as db:
        row = db.execute("SELECT common_name, source_name, source_url FROM plant_knowledge WHERE slug='tomato'").fetchone()
    assert row is not None
    assert row['common_name'] == 'Tomato'
    assert row['source_name']
    assert row['source_url'].startswith(('https://', 'local://'))


def test_irrigation_cooldown_fails_safe():
    from datetime import datetime, timezone
    from app.db.database import db_session
    from app.services.decision_engine import evaluate_plant
    from app.services.telemetry import record_reading
    settings.root_moisture_threshold = 28
    settings.irrigation_cooldown_minutes = 30
    record_reading('plant01', 'soil_root', 10, 'plants/plant01/soil/root')
    with db_session() as db:
        db.execute("INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,estimated_water_ml,command_id,status) VALUES(?,?,?,?,?,?,?)", ('plant01', datetime.now(timezone.utc).isoformat(), 'manual', 5, None, 'test-command', 'not_sent'))
    result = evaluate_plant('plant01', execute=False)
    assert result['decision'] == 'skip'
    assert 'cooldown is active' in result['reason']


def test_camera_upload_legacy_route_is_registered():
    from app.main import app
    paths = {route.path for route in app.routes if hasattr(route, 'path')}
    for route in app.routes:
        if hasattr(route, 'original_router'):
            prefix = getattr(getattr(route, 'include_context', None), 'prefix', '') or ''
            for sub in route.original_router.routes:
                paths.add(f"{prefix}{getattr(sub, 'path', '')}")
    assert '/upload' in paths
    assert '/api/v1/upload' in paths
    assert '/api/v1/plant-knowledge' in paths


def test_health_endpoints_report_service_and_mqtt_state():
    from app.main import health_live, health_ready
    live = health_live()
    ready = health_ready()
    assert live['status'] == 'alive'
    assert ready['status'] == 'ready'
    assert ready['database']['ok'] is True
    assert 'connected' in ready['mqtt']


def test_http_telemetry_ingestion():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.post('/api/v1/plants/plant01/telemetry', json={
        'soil_surface': 45.5,
        'soil_root': 32.0,
        'temperature_c': 24.2,
        'humidity_pct': 58.0,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data['status'] == 'recorded'
    assert data['count'] == 4
    readings = latest_readings('plant01')
    assert readings['soil_root']['value'] == 32.0
    assert readings['temperature_c']['value'] == 24.2


def test_auth_flow_signup_signin_me():
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    # 1. Sign up new user
    signup_resp = client.post('/api/v1/auth/signup', json={
        'name': 'Test Botanist',
        'email': 'botanist@example.com',
        'password': 'SecurePassword123!',
    })
    assert signup_resp.status_code == 201
    auth_data = signup_resp.json()
    assert 'token' in auth_data
    assert auth_data['user']['email'] == 'botanist@example.com'
    assert auth_data['user']['name'] == 'Test Botanist'
    token = auth_data['token']

    # 2. Duplicate email should be rejected with 400
    dup_resp = client.post('/api/v1/auth/signup', json={
        'name': 'Another Person',
        'email': 'botanist@example.com',
        'password': 'AnotherPassword123!',
    })
    assert dup_resp.status_code == 400

    # 3. Sign in with valid credentials
    signin_resp = client.post('/api/v1/auth/signin', json={
        'email': 'botanist@example.com',
        'password': 'SecurePassword123!',
    })
    assert signin_resp.status_code == 200
    assert 'token' in signin_resp.json()

    # 4. Sign in with invalid password
    bad_signin = client.post('/api/v1/auth/signin', json={
        'email': 'botanist@example.com',
        'password': 'WrongPassword123!',
    })
    assert bad_signin.status_code == 401

    # 5. Access /me with token
    me_resp = client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data['email'] == 'botanist@example.com'
    assert me_data['name'] == 'Test Botanist'

    # 6. Access /me without token should return 401
    no_token_resp = client.get('/api/v1/auth/me')
    assert no_token_resp.status_code == 401

