# Greetopia — AI-Powered Smart Irrigation & Plant Care System

A prototype full-stack control panel for the existing ESP32 sensor node and ESP32-CAM. Backend: FastAPI + SQLite + optional MQTT. Frontend: React + TypeScript + Vite.

## Firmware contract preserved
- Sensor MQTT topics: `plants/{plant_id}/soil/surface`, `/soil/mid`, `/soil/root`, `/temp`, `/humidity`, `/status`; optional `/leaf_wetness` is accepted if a future firmware publishes it.
- Commands: `plants/{plant_id}/water`, payload `ON` or `ON:<seconds>` (bounded to 1–15 seconds by this backend). The board must retain its own hard 15-second cutoff.
- Camera: `POST /upload`, JPEG body, `X-Plant-Id` header. This endpoint remains compatible with the provided ESP32-CAM firmware.

The uploaded firmware currently publishes the three soil metrics and DHT22 temperature/humidity/status; the spec mentions leaf wetness, but the sensor firmware provided does not implement it. The UI therefore displays it as unavailable unless a reading actually arrives. No flow sensor is present, so water volume is explicitly estimated only when a configured flow rate exists.

## Quick start (Windows/macOS/Linux)
1. Install Python 3.11+ and Node.js 20+.
2. Copy `backend/.env.example` to `backend/.env` and adjust settings if needed.
3. Backend:
   ```bash
   cd backend
   python -m venv .venv
   # Windows: .venv\\Scripts\\activate | macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
   ```
4. Frontend in a second terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open the Vite URL shown in the terminal. The frontend defaults to `http://localhost:5000` for the API.
5. Optional MQTT: set `MQTT_ENABLED=true`, `MQTT_HOST`, credentials and TLS options in `.env`. Keep MQTT disabled until you have a private broker configured. Public brokers are for isolated testing only.

## Camera configuration
The provided ESP32-CAM currently posts to `http://192.168.1.50:5000/upload`. Change the firmware's server IP to the computer running the backend on your LAN. The backend stores images under `backend/storage/photos/<plant_id>/`. Do not expose this prototype endpoint to the public internet; add authentication and HTTPS before deployment. This upload route is intentionally compatible with the current firmware and therefore does not require an auth header in prototype mode.

## Important safety notes
- This is a prototype, not a certified irrigation controller. Bench-test with the pump disconnected first.
- Backend manual command duration is clamped to 1–15 seconds; the firmware's independent hardware cutoff must remain enabled.
- Automatic decisions are opt-in (`AUTO_DECISIONS_ENABLED=true`) and run on the configured interval. The decision engine never sends an automatic command if root moisture is absent/stale, the plant is in Manual mode, or configured forecast rain probability is high. Defaults are conservative and must be calibrated for the actual plant/soil.
- MQTT is unauthenticated unless configured at the broker. Use private MQTT + credentials + TLS in real deployment.
- No user authentication is implemented yet. Keep the API and dashboard on a trusted local network only.
- No AI provider is called by default. Image upload/storage is implemented, but plant-image vision inference is not wired yet; chat and diary use transparent, data-grounded prototype logic rather than fabricated AI results.

## Tests
```bash
cd backend
pip install -r requirements.txt
pytest
```

## Main structure
- `backend/app/api/`: REST API routes
- `backend/app/core/`: settings and validation
- `backend/app/db/`: SQLite connection and schema
- `backend/app/services/mqtt_service.py`: optional MQTT subscriber/publisher
- `backend/app/services/`: telemetry, decisions, VPD, weather, photos, diary, analytics
- `frontend/src/`: dashboard UI and API client
- `docs/`: architecture and API notes
- `simulator/`: MQTT telemetry simulator for testing without hardware
- `ml/`: future model-training notes; no trained model is claimed
- `firmware_reference/`: copies of the three user-provided source files, unchanged

## Gemini AI and manual plant identification

The backend can use Google's Gemini API for grounded plant-care chat and visual observations from uploaded ESP32-CAM JPEG images. The API key belongs only in `backend/.env`; never put it in the React frontend or commit it to source control.

1. Copy `backend/.env.example` to `backend/.env` if you have not already done so.
2. Set `GEMINI_ENABLED=true` and configure `GEMINI_CHAT_API_KEY` for chat, plus optional `GEMINI_ANDROID_API_KEY` / `GEMINI_IOS_API_KEY` for app-originated photo analysis. `GEMINI_API_KEY` is the general fallback. `GEMINI_MODEL=gemini-2.5-flash` is the default.
3. Restart the backend. Internet access is required for Gemini calls.
4. Upload a camera photo, or use **Analyze latest photo** in the dashboard. The backend stores the visual result alongside the image. Image-based species guesses are suggestions, not verified identifications.
5. In **Plant profile**, enter the plant type yourself and click **Save species**. A manual choice is marked as user-confirmed and is not overwritten by Gemini image guesses. This is useful when the camera image is ambiguous.
6. Ask the assistant to analyze current conditions. It receives the saved plant profile, recent sensor readings/history, VPD, recent decisions, and watering events as context.

The local knowledge base is `backend/data/plant_profiles.json`. It contains starter reference notes for a small number of species, not a complete botanical database and not validated numeric watering thresholds. Add or review species entries using trusted horticultural sources. The dashboard's configured moisture range remains a user-configured sensor threshold, not an AI-verified universal value.

Gemini is called on demand and when a camera image is uploaded, not on every sensor packet. This avoids unnecessary API usage and latency. The deterministic decision engine remains separate from Gemini and the pump's firmware cutoff remains an independent safety layer. Do not enable automatic pump execution until the readings, relay wiring, and fail-safe behavior have been tested with the pump disconnected.

Relevant API routes: `GET /api/v1/plant-profiles`, `POST /api/v1/plants/{plant_id}/photos/analyze`, and `POST /api/v1/plants/{plant_id}/chat`.

## Plant knowledge database and Gemini controls

Greetopia ships an offline-first catalog of 36 curated starter plant profiles. It is seeded into SQLite (`plant_knowledge`) and searchable through `GET /api/v1/plant-knowledge?q=tomato`. The catalog includes source metadata and avoids pretending that a single moisture percentage is correct for every species, pot, substrate, and sensor. An optional OpenPlantDB CC0 importer is documented in `backend/data/README.md`; the upstream dataset is large and is downloaded on demand rather than copied into this ZIP.

Gemini keys must be stored only in `backend/.env`. Never put the key in frontend variables or source control. `AUTO_VISION_ANALYSIS=false` is the default so camera uploads do not call Gemini automatically every time the ESP32-CAM wakes up; users can analyze the latest photo manually. Automatic irrigation remains disabled by default. `DEVICE_UPLOAD_TOKEN` can optionally protect the camera upload route, but enabling it requires adding the matching `X-Device-Token` header in the ESP32-CAM firmware. Until that firmware change and local network controls are in place, keep the API restricted to the trusted local network.

### Deployment and secrets

Never commit or share `backend/.env`. Use `backend/.env.example` as a template and store real secrets only in local ignored files or the hosting provider's secret environment settings. If a real key was shared or bundled into an archive, revoke/rotate it before deployment. See [`docs/PERSISTENT_BACKEND_DEPLOYMENT.md`](docs/PERSISTENT_BACKEND_DEPLOYMENT.md) for a single-instance persistent backend deployment plan.


## Mobile apps (Android + iOS)

The `frontend/` app is shared by the website and Capacitor mobile wrappers. See [`mobile/README.md`](mobile/README.md) for Android Studio and Xcode build steps, native platform styling, HTTPS API configuration, and safe Gemini key setup. The website has a **Download app** dialog. Release download links are configured with `VITE_ANDROID_DOWNLOAD_URL` and `VITE_IOS_DOWNLOAD_URL` only after signed release artifacts are published. This source archive does not include signed APK/IPA binaries.
