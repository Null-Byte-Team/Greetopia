# Greetopia prototype readiness checklist

## Implemented in this revision

- [x] Offline-first plant catalog with 36 starter profiles, Arabic aliases, source metadata, and SQLite-backed search.
- [x] Optional importer for the upstream OpenPlantDB CC0 dataset (`backend/scripts/import_openplantdb.py`). The upstream file is downloaded on demand because it is large; it is not silently represented as bundled data.
- [x] Gemini API key stays on the backend and is sent in the `x-goog-api-key` header, not in the URL query string.
- [x] Camera upload works at both `/upload` (legacy ESP32-CAM URL) and `/api/v1/upload`.
- [x] Camera uploads are size-limited while streaming; plant ID must exist; JPEG signature and content type are checked.
- [x] Optional camera upload token (`DEVICE_UPLOAD_TOKEN` / `X-Device-Token`) with matching firmware variant.
- [x] Automatic Gemini vision on every camera upload is OFF by default. Latest-photo analysis can be triggered from the dashboard.
- [x] Manual species choice takes precedence over AI guesses.
- [x] Automatic pump execution is OFF by default; API execution requests are rejected unless explicitly enabled.
- [x] Irrigation cooldown to prevent repeated calls from immediately issuing another watering command.
- [x] Command results distinguish “published to MQTT” from “pump actually ran”; firmware acknowledgement/flow measurement is not implemented.
- [x] Python compilation and backend tests pass in the build environment.
- [x] Frontend TSX transpile/syntax check passes.

## Must be completed on the prototype hardware before a live watering demo

1. Rotate any Gemini key that was pasted into a chat or source file. Add the new key only to `backend/.env` and never to frontend config.
2. Confirm Wi-Fi, MQTT broker, credentials, TLS settings, plant ID and topics match on the sensor firmware and backend. A public MQTT broker is for temporary testing only.
3. Verify soil-sensor calibration using the actual growing medium at dry and wet reference points. Do not assume the example raw values work for every probe.
4. Verify the root sensor is installed at the intended root depth and that sensor values remain in the expected 0–100% range.
5. Test with the pump physically disconnected first. Confirm the decision engine skips missing/stale data, respects cooldown, and never sends a duration over 15 seconds.
6. Test manual watering with a safe test load before connecting the real pump. Confirm the board's own 15-second cutoff works independently of the backend.
7. Test the ESP32-CAM upload using both the original firmware URL (`/upload`) and the optional token-protected firmware variant.
8. Check Gemini chat and image analysis with a valid key, a missing key, provider quota errors, a timeout, and a malformed/uncertain image response.
9. Run `npm install` and `npm run build` in `frontend/` on a network-connected development machine. The full Vite build could not be verified in this environment because frontend dependencies were not available to install.
10. Keep the API on a trusted LAN only unless real authentication, HTTPS, and production deployment controls are added.

## Honest scope boundary

This is a demonstration prototype, not production-ready irrigation equipment. The database is informational and does not supply universal numeric moisture thresholds. The ML folder does not imply a trained or validated model. The system does not measure actual water volume without a calibrated flow sensor and does not receive pump execution acknowledgement from the existing firmware.
