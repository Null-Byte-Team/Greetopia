# Persistent backend deployment

The backend must run as **one long-lived container** with a persistent disk (SQLite database and photos live there).
It holds an MQTT connection and a scheduler, so serverless platforms (Vercel Functions, Lambda) are **not supported** and the app logs an error if it detects one.

## Render
`render.yaml` is ready: set `DEVICE_UPLOAD_TOKEN`, `ADMIN_EMAILS` and (optionally) MQTT/Gemini variables in the dashboard. `JWT_SECRET` is generated. The service refuses to start in production without them.

## Docker Compose
```
cp backend/.env.example backend/.env   # fill in JWT_SECRET, DEVICE_UPLOAD_TOKEN, ...
docker compose up -d --build           # backend + nginx frontend on :8080
docker compose --profile mqtt up -d    # optional private Mosquitto (see deploy/mosquitto/README.md)
```
Back up `backend/storage/` (database + photos).

## Frontend on Vercel
Static build only. Set `VITE_API_BASE=https://<backend-host>/api/v1` in the Vercel project settings and add the Vercel URL to `CORS_ORIGINS`.
