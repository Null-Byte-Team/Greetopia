# Firmware contract (v2 and legacy)

## Sensor node
| Item | Value |
|---|---|
| Topics (device -> backend) | `plants/{id}/soil/surface|mid|root` (integer text 0-100), `temp`, `humidity` (decimal text), `status` (`watering`/`idle`) |
| New in v2 (optional) | `availability` (`online`/`offline`, retained, last-will), `ack`, `fault` |
| Command | `plants/{id}/water`: `ON` (5 s) or `ON:<1..15>`; larger values capped to 15 s |
| Pins | soil ADC 34/35/32, probe power 25/27/14, DHT22 4, relay 26 (active low) |
| Interval | readings every 10 s |
| Calibration | per-probe arrays; newer sketch defaults 4095/1500, older sketch 3000/1200 (placeholders) |
| Not provided | timestamps, command IDs, flow data, leaf wetness, light |

## Camera node
`POST /upload`, raw JPEG body, `Content-Type: image/jpeg`, `X-Plant-Id`, **`X-Device-Token` (required by the backend)**; SVGA 800x600, 2 warm-up frames, deep sleep 30 min. Periodic stills, no video, no on-device AI.
