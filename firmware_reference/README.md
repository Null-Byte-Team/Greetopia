Original source files supplied for integration reference. They are copied unchanged. Do not overwrite them with generated code. The firmware and backend MQTT/HTTP contracts must be changed together if the board protocol changes.

`esp32_cam_greetopia_ready.ino` is the prototype-ready camera variant. It preserves the original `/upload`, `Content-Type: image/jpeg`, and `X-Plant-Id` contract, and optionally sends `X-Device-Token` if the backend's `DEVICE_UPLOAD_TOKEN` is configured. If you enable the token on the backend, set the same value in this firmware and flash the board. The original firmware file is preserved unchanged for reference.

`sensor_node_greetopia_ready.ino` is the prototype-ready sensor & pump node firmware. It supports:
1. **Authenticated MQTT**: Configure `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USERNAME`, and `MQTT_PASSWORD` directly in the sketch to connect securely to your private or cloud MQTT broker (e.g. HiveMQ, EMQX, Mosquitto).
2. **Direct HTTP Telemetry API**: Set `USE_HTTP = true` to post telemetry directly to `POST /api/v1/plants/{plant_id}/telemetry` (e.g. on Vercel) with optional `X-Device-Token` matching `DEVICE_UPLOAD_TOKEN`, eliminating the requirement for an external MQTT broker.
