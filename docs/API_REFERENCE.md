# API reference

Base path `/api/v1` (Swagger UI at `/docs`). **Every endpoint except the ones marked public/device requires `Authorization: Bearer <token>`.**
Roles: `viewer` (read) < `operator` (control pump, edit plants, run AI) < `admin` (users, health details). The first registered account is admin.

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| POST | `/auth/signup`, `/auth/signin`, `/auth/google` | public (rate limited) | Obtain a token |
| GET | `/auth/me` | user | Current user and role |
| GET / PATCH | `/auth/users`, `/auth/users/{id}/role` | admin | Manage roles |
| GET | `/health` | public | Minimal status |
| GET | `/health/details` | admin | MQTT counters/errors, AI configured, quarantine count |
| GET | `/plants`, `/plants/{id}/overview` | user | Plants; snapshot incl. device state, last command, alerts |
| POST / PATCH | `/plants`, `/plants/{id}` | operator | Create/update (species only changes by explicit user edit) |
| GET | `/plants/{id}/readings/latest`, `/readings/history` | user | `history`: `metric`, `limit` (1-5000), ISO `start`/`end` |
| GET | `/plants/{id}/device` | user | `online` / `stale` / `offline` derived from telemetry |
| GET | `/plants/{id}/events`, `/alerts` | user | Irrigation commands with status; alerts |
| PATCH | `/plants/{id}/mode` | operator | `auto` / `manual` |
| POST | `/plants/{id}/water` | operator | 1-15 s. 409 `pending_command`/`pump_running`, 429 `cooldown`/`daily_*_limit`, 422 bad duration |
| POST | `/plants/{id}/decision?execute=` | operator | Evaluate (logged); `execute=true` only if `AUTO_DECISIONS_ENABLED` |
| GET | `/plants/{id}/decisions`, `/analytics`, `/diary`, `/weather` | user | History, totals (recorded data only), diary |
| POST | `/plants/{id}/photos/analyze` | operator, rate limited | Vision analysis; species is a **candidate only** |
| POST | `/plants/{id}/chat` | user, rate limited | Gemini answer, or `mode: rule_based` answer from stored data |
| GET | `/photos/{plant}/{file}?exp&sig` | signed link | Short-lived signed photo URL (returned by the API) |
| POST | `/upload` (also `/api/v1/upload`) | device token | ESP32-CAM raw JPEG + `X-Plant-Id`; Pillow-validated, de-duplicated by SHA-256 |
| POST | `/plants/{id}/telemetry` | device token | HTTP telemetry fallback (one way: no pump commands) |

Event `status` values: `published` -> `acknowledged` (new firmware) -> `observed_watering` -> `confirmed`;
`failed_publish`, `rejected`, `unconfirmed` (never seen `watering`; **never retried automatically**), `unconfirmed_end`, `unrequested`.
`published` means the broker accepted the command, not that the pump ran.
