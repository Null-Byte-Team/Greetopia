# Architecture

- ESP32 sensor node publishes independent telemetry values to MQTT.
- Optional MQTT adapter validates topic and payload, then records each reading with server receive time.
- FastAPI exposes plant profiles, latest readings, history, decisions, manual control, photos, weather, chat, and diary endpoints.
- SQLite stores plant profiles, readings, decision logs, irrigation requests, photos, weather snapshots, chat, and diary entries.
- ESP32-CAM posts raw JPEG bytes to `POST /upload` with `X-Plant-Id`. Images are stored on disk; vision analysis is not yet connected.
- The React dashboard reads the API and shows missing/stale sensor values as unavailable.
- Automatic decision scheduling is opt-in through `AUTO_DECISIONS_ENABLED=true`; it must remain off until tested with the pump disconnected.

## Data integrity choices
- Server receive timestamps are used because current firmware payloads do not contain timestamps.
- Soil percentages are validated to 0–100. Temperature and humidity have basic range validation.
- MQTT commands use `ON:<seconds>` explicitly because plain `ON` activates the firmware's default 15-second duration.
- Water volume is not reported as measured. It remains unavailable unless a calibrated `FLOW_ML_PER_SECOND` is configured, and even then is an estimate.
