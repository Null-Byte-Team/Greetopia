# Bench test (pump DISCONNECTED, relay LED or multimeter only)

1. `CALIBRATION_MODE = true`: record raw dry/wet values per probe; enter them; set `false`; flash.
2. Start the backend with `MQTT_ENABLED=true` and `AUTO_DECISIONS_ENABLED=false`. Check the dashboard shows the node `online` within ~45 s.
3. Pull the probe wires one at a time: expect `plants/<id>/fault` and a stale root reading (no automatic watering).
4. Manual watering 3 s: relay closes ~3 s; event goes `published -> acknowledged -> observed_watering -> confirmed`.
5. Send `ON:5` twice quickly (mosquitto_pub): second gets `rejected:busy`. Send `ON:99`: runs 15 s only. Send `ONX`: `rejected:invalid`.
6. **Outage test:** start a 15 s run, then switch off the Wi-Fi router or stop the broker. The relay must still release at 15 s.
7. Power-cycle during a run: the relay must be off after boot.
8. Publish `ON:5` from a non-backend MQTT user: the broker ACL must refuse it.
9. Stop the node during a command: the event must become `unconfirmed` after 45 s and must not be re-sent.
10. Only then connect the pump with a dummy container; keep `AUTO_DECISIONS_ENABLED=false` for the first days and read the logged decisions.
