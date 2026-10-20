# Security notes

- **Secrets:** never commit or archive `backend/.env` or `firmware/**/secrets.h`. Rotate any key that has been shared. Provider keys exist only on the backend.
- **Auth:** JWT (HS256) from `JWT_SECRET` (>= 32 chars, required in production), 7-day expiry, roles in the DB. PBKDF2-SHA256 600k iterations; older hashes are upgraded on sign-in. Sign-in/up and AI endpoints are rate limited (in-memory, single process).
- **Roles:** first account = admin; others are viewers until promoted (`ADMIN_EMAILS`, `OPERATOR_EMAILS`, or `PATCH /auth/users/{id}/role`).
- **Devices:** shared `X-Device-Token`. Rotate by changing the env var and re-flashing.
- **MQTT:** private broker + ACL (only the backend may publish `plants/+/water`). Public brokers are refused unless `MQTT_DEV_PUBLIC_BROKER=true`.
- **Photos:** decoded with Pillow, size/pixel limited, stored under generated names, served through short-lived signed URLs.
- **Browser storage:** the session token is in `localStorage` (XSS would expose it); keep the CSP/dependency hygiene in mind or move to HttpOnly cookies.
- **Known limits:** rate limiting is per process; SQLite means one backend instance; Google sign-in verification uses Google's tokeninfo endpoint.
