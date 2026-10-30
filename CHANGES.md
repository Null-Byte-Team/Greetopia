# What changed in this revision

**Backend:** auth on every endpoint + roles, device tokens, JWT secret required, `/debug` removed, strict telemetry validation (the temperature/humidity check never ran before), quarantine + duplicate suppression, age-based retention, per-plant decision engine with hysteresis/trend/sensor-sanity/daily caps, command lifecycle with reconciliation (never auto-retry), alerts, device online/stale/offline, Pillow-validated de-duplicated photos with signed URLs, AI off the event loop with bounded retries, species never auto-written, rule-based chat fallback, per-plant weather location, bounded MQTT queue, TLS, public-broker guard, PyJWT instead of python-jose.
**Firmware:** v2 sensor and camera nodes (see `docs/FIRMWARE_CHANGES.md`); the unsafe "ready" sketch is deprecated.
**Frontend:** explicit API base (no hard-coded production URL), no guest mode, read-only role handling, device state and last command shown, "use as confirmed species" button, error messages for structured API errors.
**Deployment:** Render config hardened, Vercel = static frontend only, nginx frontend image, optional private Mosquitto with ACL, `.gitignore` for secrets/APK/builds, Android backup disabled.
**Tests:** 105 backend tests + PC firmware logic tests.

Upgrade: existing SQLite databases are migrated automatically (new columns/tables). Existing users keep their password hashes but become read-only `viewer`s (the role column is new): set `ADMIN_EMAILS` before the first start so someone can control the pump and promote others.


# Second pass: features and verification

**Added (all with automated tests):** WebSocket live updates (`/api/v1/ws`, first-message auth, bounded queues, resync on overflow, client re-fetch on reconnect); data-driven insights (`docs/INSIGHTS.md`); randomised A/B experiment engine with fixed-schedule / fixed-threshold control arms, exact/asymptotic Mann-Whitney, bootstrap CI, report + zip export (`docs/EXPERIMENTS.md`); camera green-area growth proxy; ML stress-predictor pipeline with registry, checksum-verified loading and refusal to approve unless it beats a baseline (`docs/ML.md`); optional HMAC-signed pump commands with replay protection (backend + firmware logic); dashboard charts, Insights / Experiments / Users views, live badge; CI workflow; real-Mosquitto integration test (ACL, last-will, exact `ON:5`, reconciliation).

**Bugs found and fixed by those tests:** pandas 3 stores timestamps in microseconds (`asi8` mismatch would have corrupted labels and the "minutes since watering" feature); inference used the still-filling 10-minute bin; a gray-world colour correction erased the green signal in leaf-dominated photos.

**Verified here:** backend `pytest` (see README for the count), real broker round trip, firmware logic and SHA-256/HMAC (RFC 4231 + backend cross-check) on a PC with `g++ -Werror`, frontend `tsc` + Vite build, chart maths against the backend VPD.

**NOT verified / not done:** ESP32 compilation and hardware runs (CI job `firmware-compile` exists but has not been executed); browser rendering of the new views (build only); Docker image builds; Google sign-in; Gemini/OpenWeather live calls; PostgreSQL/SQLAlchemy/Alembic migration (still SQLite); flow-sensor, OTA, NTP/store-and-forward, Telegram alerts, offline PWA, multi-user plant ownership; per-photo "apparent stress threshold" learning; no real experiment data exists yet, so no result of any kind is claimed.
