from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore', env_ignore_empty=True)
    app_name: str = 'Greetopia API'
    api_prefix: str = '/api/v1'
    database_path: str = 'storage/smart_irrigation.db'
    photo_dir: str = 'storage/photos'
    max_photo_bytes: int = 5_000_000
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173,http://localhost,capacitor://localhost'
    mqtt_enabled: bool = False
    mqtt_host: str = '127.0.0.1'
    mqtt_port: int = 1883
    mqtt_username: str = ''
    mqtt_password: str = ''
    mqtt_tls: bool = False
    mqtt_keepalive: int = 45
    default_plant_id: str = 'plant01'
    decision_interval_minutes: int = 15
    irrigation_cooldown_minutes: int = 30
    auto_decisions_enabled: bool = False
    sensor_stale_minutes: int = 5
    root_moisture_threshold: float = 28
    rain_skip_probability: float = 0.65
    default_water_seconds: int = 5
    flow_ml_per_second: float | None = None
    # Backend-only Gemini credentials. Never embed these in web/mobile client bundles.
    gemini_api_key: str = ''
    gemini_chat_api_key: str = ''
    gemini_android_api_key: str = ''
    gemini_ios_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    gemini_enabled: bool = True
    auto_vision_analysis: bool = False
    device_upload_token: str = ''
    plant_profiles_path: str = 'data/plant_profiles.json'
    openweather_api_key: str = ''
    openweather_lat: float | None = None
    openweather_lon: float | None = None

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]

settings = Settings()
Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
Path(settings.photo_dir).mkdir(parents=True, exist_ok=True)
