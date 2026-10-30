# Architecture

- **Sensor node (ESP32)** publishes independent values to a **private MQTT broker** (`plants/{id}/soil/{surface|mid|root}`, `temp`, `humidity`, `status`) and, with firmware v2, `availability`, `ack`, `fault`.
- **MQTT adapter** (`services/mqtt_service.py`): bounded queue + worker thread, strict topic/payload validation, quarantine table for rejected messages, retained telemetry ignored, public brokers refused.
- **Telemetry** (`services/telemetry.py`): history in `readings` (age-based retention, default 90 days) plus an O(1) `latest_readings` snapshot. Server receive time is used because the firmware sends no timestamps.
- **Device state** (`services/device_state.py`): online/stale/offline from the last valid message; reconciles commands with the observed `watering`/`idle` status; raises alerts for unconfirmed or unrequested pump activity.
- **Irrigation controller** (`services/irrigation.py`): the only code path that publishes pump commands (guards: 1-15 s, pending command, cooldown, daily caps).
- **Decision engine** (`services/decision_engine.py`): pure `decide()` + I/O wrapper. See `docs/DECISION_ENGINE.md`.
- **Camera**: `POST /upload` (device token) -> Pillow validation -> SHA-256 de-duplication -> files under `PHOTO_DIR/<plant>/`, DB stores a relative key. Optional AI analysis runs off the event loop and records failures on the photo row.
- **Auth** (`services/auth.py`): JWT (PyJWT), roles stored in the DB, device token for nodes, signed photo URLs.
- **SQLite** is used on one persistent disk with exactly one backend instance.
- **React dashboard** polls the API (15 s). It shows missing/stale values as unavailable and never presents "published" as "executed".

Not implemented (see `docs/NEXT_FEATURES_PROMPT.md`): WebSockets, PostgreSQL/Alembic, ML stress predictor, baseline-vs-adaptive experiments, flow sensor.
