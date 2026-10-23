import sqlite3, json
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from app.core.config import settings

SCHEMA = """\
CREATE TABLE IF NOT EXISTS plants (
 plant_id TEXT PRIMARY KEY, name TEXT NOT NULL, species TEXT DEFAULT '', growth_stage TEXT DEFAULT '', species_source TEXT DEFAULT 'unknown',
 ideal_moisture_min REAL DEFAULT 30, ideal_moisture_max REAL DEFAULT 65,
 light_needs TEXT DEFAULT '', notes TEXT DEFAULT '', mode TEXT DEFAULT 'auto', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL,
 received_at TEXT NOT NULL, topic TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_plant_metric_time ON readings(plant_id, metric, received_at);
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, created_at TEXT NOT NULL,
 source TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL, readings_json TEXT NOT NULL,
 vpd_kpa REAL, weather_json TEXT, vision_json TEXT, command_id TEXT
);
CREATE TABLE IF NOT EXISTS photos (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, capture_id TEXT NOT NULL,
 file_path TEXT NOT NULL, received_at TEXT NOT NULL, vision_json TEXT
);
CREATE TABLE IF NOT EXISTS irrigation_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, created_at TEXT NOT NULL,
 source TEXT NOT NULL, duration_seconds INTEGER NOT NULL, estimated_water_ml REAL, command_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued'
);
CREATE TABLE IF NOT EXISTS weather_snapshots (
 plant_id TEXT PRIMARY KEY, checked_at TEXT NOT NULL, rain_probability REAL, rain_mm REAL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diary_entries (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, day TEXT NOT NULL, content TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(plant_id, day)
);
CREATE TABLE IF NOT EXISTS chat_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plant_knowledge (
 slug TEXT PRIMARY KEY, common_name TEXT NOT NULL, scientific_name TEXT DEFAULT '', category TEXT DEFAULT 'unknown',
 aliases_json TEXT NOT NULL DEFAULT '[]', data_json TEXT NOT NULL, source_name TEXT NOT NULL, source_url TEXT NOT NULL, license TEXT DEFAULT '', updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plant_knowledge_name ON plant_knowledge(common_name);
CREATE TABLE IF NOT EXISTS latest_readings (
 plant_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL, received_at TEXT NOT NULL,
 PRIMARY KEY (plant_id, metric)
);
CREATE TABLE IF NOT EXISTS device_status (
 plant_id TEXT PRIMARY KEY, pump_status TEXT, pump_observed_at TEXT, availability TEXT, availability_at TEXT,
 last_ack TEXT, last_ack_at TEXT, last_fault TEXT, last_fault_at TEXT, last_message_at TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT, kind TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'warning',
 message TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_plant ON alerts(plant_id, created_at);
CREATE TABLE IF NOT EXISTS quarantine_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, payload_preview TEXT NOT NULL, reason TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_plant_time ON irrigation_events(plant_id, created_at);
"""

_initialized = False

def _seed_knowledge(conn):
    """Seed the local searchable knowledge table from the bundled, offline-first catalog."""
    try:
        profiles_path = Path(__file__).resolve().parents[2] / 'data' / 'plant_profiles.json'
        if not profiles_path.is_file():
            profiles_path = Path(__file__).resolve().parents[1] / 'data' / 'plant_profiles.json'
        if not profiles_path.is_file():
            profiles_path = Path('data/plant_profiles.json')
        if not profiles_path.is_file():
            return
        profiles = json.loads(profiles_path.read_text(encoding='utf-8'))
        meta = profiles.get('_meta', {})
        sources = {item.get('id'): item for item in meta.get('sources', [])}
        now = datetime.now(timezone.utc).isoformat()
        for slug, profile in profiles.items():
            if slug.startswith('_') or not isinstance(profile, dict):
                continue
            refs = profile.get('source_refs', [])
            source = sources.get(refs[0], {}) if refs else {}
            conn.execute(
                '''INSERT INTO plant_knowledge(slug,common_name,scientific_name,category,aliases_json,data_json,source_name,source_url,license,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(slug) DO UPDATE SET
                       common_name=excluded.common_name,
                       aliases_json=excluded.aliases_json,
                       data_json=excluded.data_json,
                       updated_at=excluded.updated_at
                   WHERE plant_knowledge.source_name != 'OpenPlantDB' ''',
                (slug,
                 profile.get('common_name', slug.title()),
                 profile.get('scientific_name', ''),
                 profile.get('category', 'unknown'),
                 json.dumps(profile.get('aliases', []), ensure_ascii=False),
                 json.dumps(profile, ensure_ascii=False),
                 source.get('name', 'Greetopia curated starter catalog'),
                 source.get('url', 'local://greetopia/backend/data/plant_profiles.json'),
                 source.get('license', 'Greetopia-authored starter notes'),
                 now))
        conn.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Could not seed plant knowledge table')


# Additive, idempotent column migrations for databases created by earlier versions.
_COLUMNS = {
    'plants': {'latitude': 'REAL', 'longitude': 'REAL'},
    'decisions': {'engine_version': 'TEXT', 'duration_s': 'INTEGER DEFAULT 0', 'executed': 'INTEGER DEFAULT 0', 'inputs_json': 'TEXT'},
    'photos': {'sha256': 'TEXT', 'width': 'INTEGER', 'height': 'INTEGER', 'vision_status': "TEXT DEFAULT 'none'", 'vision_error': 'TEXT'},
    'irrigation_events': {'requested_by': 'TEXT', 'reason': 'TEXT', 'observed_start_at': 'TEXT', 'observed_end_at': 'TEXT', 'measured_water_ml': 'REAL'},
}


def _migrate(conn):
    for table, cols in _COLUMNS.items():
        existing = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        for name, ddl in cols.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_photos_plant_sha ON photos(plant_id, sha256) WHERE sha256 IS NOT NULL')


def init_db():
    global _initialized
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.executescript(SCHEMA)
        plant_columns = {row['name'] for row in conn.execute('PRAGMA table_info(plants)').fetchall()}
        if 'species_source' not in plant_columns:
            conn.execute("ALTER TABLE plants ADD COLUMN species_source TEXT DEFAULT 'unknown'")
        _migrate(conn)
        conn.execute(
            'INSERT OR IGNORE INTO plants (plant_id,name,species,growth_stage,created_at) VALUES (?,?,?,?,?)',
            (settings.default_plant_id, 'My Plant', 'Unknown', 'Unknown', datetime.now(timezone.utc).isoformat()))
        conn.commit()
        _seed_knowledge(conn)
        _initialized = True
    finally:
        conn.close()


def ensure_db():
    global _initialized
    if not _initialized or not Path(settings.database_path).is_file():
        init_db()


def connect():
    ensure_db()
    conn = sqlite3.connect(settings.database_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn

@contextmanager
def db_session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
