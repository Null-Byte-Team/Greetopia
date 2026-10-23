# Firmware v2: what changed and why

Based on the newer sensor sketch (`firmware_reference/plant_node_firmware_newer_original.ino`) and the original camera sketch. **Same pins, same topics, same payload formats, same `POST /upload` contract.**

| Problem in the previous firmware | v2 behaviour |
|---|---|
| The 15 s cutoff came after `while` loops that block on Wi-Fi/MQTT, so an outage during watering left the pump on | A one-shot `esp_timer` (separate task) switches the relay off at the deadline; reconnects are non-blocking with exponential backoff |
| "ready" variant dropped `!pumpRunning`, so repeated `ON` extended the run | A running pump is never extended; extra commands get `rejected:busy` |
| `startsWith("ON")` accepted `ONX`, `ON:abc`; invalid seconds became 15 s | Exact grammar `ON` or `ON:<1..4 digits>`; `0`, junk, trailing characters rejected; values > 15 capped to 15. Plain `ON` now runs **5 s** (was 15 s); the backend always sends `ON:<n>` |
| No defence if the broker is abused | 10 s minimum rest, 45 s/hour runtime budget, commands in the first 2.5 s after subscribing ignored (retained leftovers) |
| Public broker, no credentials | `MQTT_USER/PASS` + optional TLS (CA pinned); last-will `offline` and retained `online` on `plants/<id>/availability` |
| No acknowledgement | `plants/<id>/ack`: `accepted:<s>` / `rejected:<busy|invalid|rest|budget>` (old backends ignore it) |
| Shorted/open probes published as a plausible percentage | Implausible raw values are not published; `plants/<id>/fault` = `soil_root:shorted|open` |
| Camera: no auth, HTTP only, no retry | `X-Device-Token`, HTTPS with CA, 3 upload attempts, JPEG check, refuses placeholder config |

Unchanged limits: no timestamps, no heartbeat except availability, QoS 0 publishing (PubSubClient), no flow sensor, no OTA.
Hardware advice: 10 k pull-up on the active-low relay input; flyback diode across the pump; fuse the pump supply.
**Not compiled for ESP32 or run on hardware by the author.** The pure logic (`pump_logic.h`) is tested on a PC.
