# What changed in this revision

**Backend:** auth on every endpoint + roles, device tokens, JWT secret required, `/debug` removed, strict telemetry validation (the temperature/humidity check never ran before), quarantine + duplicate suppression, age-based retention, per-plant decision engine with hysteresis/trend/sensor-sanity/daily caps, command lifecycle with reconciliation (never auto-retry), alerts, device online/stale/offline, Pillow-validated de-duplicated photos with signed URLs, AI off the event loop with bounded retries, species never auto-written, rule-based chat fallback, per-plant weather location, bounded MQTT queue, TLS, public-broker guard, PyJWT instead of python-jose.
**Firmware:** v2 sensor and camera nodes (see `docs/FIRMWARE_CHANGES.md`); the unsafe "ready" sketch is deprecated.
**Frontend:** explicit API base (no hard-coded production URL), no guest mode, read-only role handling, device state and last command shown, "use as confirmed species" button, error messages for structured API errors.
**Deployment:** Render config hardened, Vercel = static frontend only, nginx frontend image, optional private Mosquitto with ACL, `.gitignore` for secrets/APK/builds, Android backup disabled.
**Tests:** 105 backend tests + PC firmware logic tests.

Upgrade: existing SQLite databases are migrated automatically (new columns/tables). Existing users keep their password hashes but become read-only `viewer`s (the role column is new): set `ADMIN_EMAILS` before the first start so someone can control the pump and promote others.

## 2026-10-20 verification attempt

- Reviewed the project architecture, decision rules, firmware contract/change notes, security notes, bench procedure, source audit, and the v2 sketches plus their reference origins. Existing code includes MQTT worker-queue ingestion, command acknowledgement/status reconciliation, retained offline availability handling, and an ACL that grants the node no write access to pump commands.
- Tooling observed: Arduino CLI 1.5.1, Arduino-ESP32 core 3.3.12, and the required sensor-node libraries are installed. The ESP32 Dev Module (`esp32:esp32:esp32`) and AI Thinker ESP32-CAM (`esp32:esp32:esp32cam`) FQBNs are present.
- **Not verified:** neither firmware compile result was obtainable: Arduino CLI commands returned no output through the available terminal channel, including when run with absolute sketch paths. No source-level compatibility fix was made without compiler diagnostics.
- Docker CLI 29.7.2 and Compose 5.5.0 are installed, but Docker Engine is unavailable (`docker info` could not connect to `dockerDesktopLinuxEngine`). Therefore the Mosquitto-container integration test and `docker compose build` were not run. No new integration test was added because it could not be executed here.
- Backend test dependencies are not installed in the selected Python interpreter, and the terminal did not provide an observable result for the retry from the backend directory; backend tests were not run. The claimed 105-test baseline was not independently re-verified in this session.
