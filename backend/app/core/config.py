import logging
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

FIRMWARE_MAX_PUMP_S = 15  # hard limit in the sensor-node firmware (MAX_PUMP_RUN_MS)

# Informational only: this backend needs ONE long-running process (MQTT consumer + scheduler
# + SQLite on a persistent disk). Serverless platforms are not a supported target.
is_serverless = bool(
    os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("LAMBDA_TASK_ROOT")
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    app_name: str = "Greetopia API"
    app_env: str = "development"  # development | production
    api_prefix: str = "/api/v1"
    database_path: str = "storage/smart_irrigation.db"
    photo_dir: str = "storage/photos"
    max_photo_bytes: int = 5_000_000
    max_photo_pixels: int = 12_000_000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost,capacitor://localhost"

    # ---- auth ----
    jwt_secret: str = ""  # REQUIRED in production (>= 32 chars). Dev: random per-process secret.
    jwt_expire_days: int = 7
    google_client_id: str = "355615741600-5tfd5st7gr7ihnl81k78794u853u32qc.apps.googleusercontent.com"
    admin_emails: str = ""  # comma separated; always admin
    operator_emails: str = ""  # comma separated; may control pumps. First registered user becomes admin.
    device_upload_token: str = ""  # shared secret for ESP32 nodes (X-Device-Token)
    allow_insecure_devices: bool = False  # dev only: accept device calls without a token
    photo_url_ttl_s: int = 3600

    # ---- MQTT ----
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_tls: bool = False
    mqtt_ca_file: str = ""
    mqtt_keepalive: int = 45
    mqtt_queue_size: int = 1000
    mqtt_dev_public_broker: bool = False  # must be true to connect to a public test broker

    default_plant_id: str = "plant01"

    # ---- device freshness (derived from telemetry; firmware has no independent heartbeat) ----
    sensor_stale_minutes: int = 5
    device_online_max_age_s: int = 45
    device_stale_max_age_s: int = 300
    decision_max_age_s: int = 90  # critical readings older than this block automatic watering

    # ---- decision engine / safety (initial experimental defaults, documented in docs/DECISION_ENGINE.md) ----
    decision_interval_minutes: int = 15
    auto_decisions_enabled: bool = False
    irrigation_cooldown_minutes: int = 30
    manual_cooldown_seconds: int = 60
    max_daily_runtime_seconds: int = 60
    max_commands_per_day: int = 6
    confirm_timeout_seconds: int = 45
    hysteresis_pct: float = 5.0
    root_moisture_threshold: float = 28  # fallback only when a plant has no profile range
    rain_skip_probability: float = 0.65
    rain_critical_margin_pct: float = 10.0
    default_water_seconds: int = 5
    min_water_seconds: int = 3
    seconds_per_deficit_pct: float = 0.4
    trend_window_minutes: int = 60
    trend_horizon_minutes: int = 60
    flow_ml_per_second: float | None = None
    readings_retention_days: int = 90  # 0 = keep everything

    # ---- AI providers (backend only) ----
    gemini_api_key: str = ""
    gemini_chat_api_key: str = ""
    gemini_android_api_key: str = ""
    gemini_ios_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_enabled: bool = True
    gemini_max_retries: int = 2
    auto_vision_analysis: bool = False
    ai_rate_limit_per_minute: int = 10
    plant_profiles_path: str = "data/plant_profiles.json"
    openweather_api_key: str = ""
    openweather_lat: float | None = None
    openweather_lon: float | None = None

    @property
    def cors_list(self) -> list[str]:
        origins = [x.strip() for x in self.cors_origins.split(",") if x.strip()]
        if "*" in origins:
            log.warning("CORS wildcard ignored; list explicit origins in CORS_ORIGINS")
            origins = [o for o in origins if o != "*"]
        return origins

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def csv(self, value: str) -> set[str]:
        return {x.strip().lower() for x in value.split(",") if x.strip()}


settings = Settings()


def validate_settings() -> None:
    """Fail fast on unsafe production configuration."""
    if settings.is_production:
        if len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set (>= 32 characters) when APP_ENV=production")
        if not settings.device_upload_token and not settings.allow_insecure_devices:
            raise RuntimeError("DEVICE_UPLOAD_TOKEN must be set when APP_ENV=production")
        if settings.allow_insecure_devices:
            raise RuntimeError("ALLOW_INSECURE_DEVICES is not permitted when APP_ENV=production")


def _ensure_dir(path: str) -> None:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # never silently fall back to a temp dir: that loses data
        raise RuntimeError(f"Storage path is not writable: {path} ({exc.strerror})") from exc


_ensure_dir(str(Path(settings.database_path).parent))
_ensure_dir(settings.photo_dir)
