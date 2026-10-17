# Greetopia persistent backend deployment

This project needs more than a static Vercel site. The FastAPI service starts an MQTT subscriber and a scheduled decision loop in the same long-running process. Deploy it as **one always-on container instance** until the MQTT consumer and scheduler are separated into independent workers. Do not deploy this current process model as serverless functions or scale it horizontally.

## Suggested layout

- **Vercel:** React/Vite frontend only.
- **Render Docker web service:** FastAPI API plus its MQTT client and scheduled loop, on one always-on instance. `render.yaml` configures a Starter service and a 1 GB persistent disk mounted at `/app/storage`. Persistent disks and always-on service plans may incur charges; check the current provider pricing before deploying.
- **Persistent storage:** SQLite database and uploaded photos live under `/app/storage`. The disk is tied to this single service instance. Back up the database and photos separately; a persistent disk is not itself a backup.
- **MQTT broker:** Use a private broker with username/password and TLS. Leave `MQTT_ENABLED=false` until those credentials and the broker are configured. Do not use a public broker for production pump control.
- **Gemini:** `GEMINI_ENABLED` is deliberately false in the deployment template. Do not enable it or add Gemini keys to a publicly accessible API until proper user authentication and rate limiting are implemented, otherwise strangers could consume your API quota. Never commit `.env` or place keys in `VITE_*` variables.
- **Public API safety:** This prototype does not yet implement user authentication. The template keeps MQTT and Gemini disabled for this reason. Do not enable remote pump commands or public AI calls until authentication, authorization, and rate limiting are implemented and tested.

## Deploy using Render Blueprint

1. Push the project to a private Git repository. Confirm `backend/.env` is not present in the repository.
2. In Render, create a Blueprint from the repository and review `render.yaml`.
3. Update `CORS_ORIGINS` to the exact deployed Vercel URL. Include the origin only, without an API path. Add any custom domain used by the frontend.
4. Enter secret environment values in Render's dashboard. Blank secret fields are intentional until you configure them.
5. Keep `MQTT_ENABLED=false` and `GEMINI_ENABLED=false` for the initial public deployment. This prototype has no user authentication, so enabling pump commands or paid AI calls would expose them to unauthenticated internet traffic. Add and test authentication/authorization/rate limiting before enabling either.
6. Keep `AUTO_DECISIONS_ENABLED=false` until authentication, sensor freshness, relay wiring, cooldown, and hardware cutoff have been tested with the pump disconnected.
7. After deployment, open `/health/live` and `/health/ready`. The ready response checks database access and reports MQTT state without restarting the API repeatedly when the broker is temporarily offline.
8. Set the frontend `VITE_API_BASE` to `https://<your-render-service>/api/v1`, rebuild the frontend, and redeploy it to Vercel. Set `VITE_API_BASE` in Vercel project environment variables, not only in a local file.

## Operational constraints

- Keep `numInstances: 1` and Uvicorn `--workers 1`. The MQTT client ID is shared and SQLite is on a single-instance disk. Horizontal scaling would create duplicate consumers/schedulers and unsafe state behavior.
- Render restarts a crashed process, and Paho retries MQTT connections after transient disconnects. Neither removes the need for uptime monitoring and logs.
- `/health/live` says the process responds. `/health/ready` verifies database access and reports MQTT status. A healthy API does not prove the ESP32 is sending fresh readings; monitor the timestamps of the latest sensor readings separately.
- SQLite is suitable for this single-instance prototype. If Greetopia later needs multiple backend instances or higher write concurrency, migrate to a managed PostgreSQL database and move MQTT/scheduled jobs into dedicated workers before scaling.
- The persistent disk can incur a monthly charge and may limit deploy strategies. Confirm provider pricing and backup behavior before going live.

## Local Docker Compose

1. Copy `backend/.env.example` to `backend/.env` and add local values.
2. Run `docker compose up --build -d`.
3. Check `http://localhost:5000/health/ready` and logs with `docker compose logs -f backend`.
4. Data is stored in `backend/storage/` on the host. Keep that folder out of Git.

## Secrets incident note

Never include `backend/.env` in a ZIP or repository. If real API keys have already been shared in chat or bundled into an archive, revoke/rotate them at the provider, then enter the replacements only in the deployment provider's secret settings.
