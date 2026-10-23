# Readiness checklist

## Done in code (verified by automated tests)
- [x] Authentication on every data/control endpoint, roles, rate-limited sign-in, no hard-coded secrets, JWT secret required in production.
- [x] Device token required for camera uploads and HTTP telemetry.
- [x] Telemetry validation (finite numbers, ranges, strict payload grammar), quarantine of rejected MQTT messages, duplicate suppression.
- [x] Per-plant decision engine with hysteresis, trend, sensor-sanity check, weather (missing forecast is not "no rain"), cooldown, daily caps, pending/unconfirmed-command blocking.
- [x] Command lifecycle: requested vs. observed; unconfirmed commands are flagged, never repeated.
- [x] Photo validation (decoded with Pillow), SHA-256 de-duplication, relative storage keys, signed URLs, AI analysis off the event loop, species is a candidate only.
- [x] Age-based history retention instead of a 5000-row cap.

## Must be done on real hardware before a live demo
1. Rotate every API key that ever sat in a `.env` that was shared or archived (Gemini keys, OpenWeather key).
2. Run `docs/BENCH_TEST.md` with the pump **disconnected**, then with a dummy load.
3. Calibrate each probe in your own soil (`CALIBRATION_MODE`), and measure the pump flow before setting `FLOW_ML_PER_SECOND`.
4. Use a private broker with the ACL in `deploy/mosquitto/`.
5. Keep `AUTO_DECISIONS_ENABLED=false` until step 2 passes.

## Scope boundary
A research prototype. There is no trained ML model, no flow sensor, and no measured water-saving result; the UI and API never claim one.
