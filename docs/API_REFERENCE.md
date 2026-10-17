# API reference

Base path: `/api/v1` (interactive Swagger UI at `/docs`).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API and MQTT configuration status |
| GET/POST | `/plants` | List/create plant profiles |
| PATCH | `/plants/{id}` | Update species and care profile |
| GET | `/plants/{id}/overview` | Latest readings, VPD, weather, photo, analytics |
| GET | `/plants/{id}/readings/latest` | Latest readings with freshness flags |
| GET | `/plants/{id}/readings/history` | Reading history; optional `metric`, `limit` |
| GET | `/plants/{id}/weather` | Cached weather; `refresh=true` forces refresh |
| POST | `/plants/{id}/decision` | Evaluate safely; defaults to dry-run. `execute=true` permits command dispatch if watering is indicated |
| PATCH | `/plants/{id}/mode` | Set `auto` or `manual` |
| POST | `/plants/{id}/water` | Manual watering request, duration 1–15 seconds |
| GET | `/plants/{id}/photos/latest` | Latest photo metadata |
| POST | `/upload` | Firmware-compatible raw JPEG upload with `X-Plant-Id` |
| GET | `/photos/{id}/{filename}` via API prefix | Serve stored JPEG |
| GET | `/plants/{id}/analytics` | Events and water-volume caveat |
| GET | `/plants/{id}/decisions` | Recent decisions |
| GET/POST | `/plants/{id}/diary`, `/diary/generate` | Read/generate sensor-grounded diary entry |
| POST | `/plants/{id}/chat` | Data-grounded prototype answer |

No authentication is implemented. Keep this service on a trusted local network only.
