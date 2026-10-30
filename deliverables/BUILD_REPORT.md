# Build & verification report (this revision)

| Check | Result |
|---|---|
| Backend tests | `cd backend && python -m pytest tests` -> 152 passed (Python 3.12; includes a real Mosquitto round trip, WebSocket, insights, experiments, ML, signing) |
| Firmware logic tests (PC, g++ -std=c++17 -Werror) | passed: command grammar, 15 s cap, rest/budget limits, retained-message guard, millis() rollover, soil plausibility, SHA-256/HMAC (RFC 4231 + backend cross-check), signed-command replay/tamper |
| Frontend | `npm ci && npm run build` (tsc + Vite) passed; React 18.3, TypeScript 5.6, Vite 6 |
| Firmware compiled for ESP32 / run on hardware | **NOT done** (no Arduino toolchain in the build environment) |
| Android APK | **Not rebuilt**; the old APK is obsolete (see mobile/RELEASE_STATUS.md) |
| Not verified | Real MQTT broker round trip, Google sign-in against Google, Gemini/OpenWeather live calls |
