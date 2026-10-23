# Source audit (spec vs. firmware vs. code) - status after this revision

| Finding | Status |
|---|---|
| Spec lists leaf wetness; firmware has none | UI shows "not implemented"; backend accepts the metric only if hardware is added |
| Spec subscribes to `plants/+/+` (misses nested soil topics) | Explicit subscriptions in `mqtt_service.SUBSCRIPTIONS` |
| Two different sensor sketches exist (3000/1200 vs 4095/1500) | Both preserved in `firmware_reference/`; v2 follows the newer one |
| Soil probe type: guide says capacitive, sketch says resistive | Documented; verify your probe |
| No flow sensor | Volume is only an estimate from `FLOW_ML_PER_SECOND`; otherwise unavailable |
| Camera/telemetry had no authentication | `X-Device-Token` required |
| Public broker default | Refused unless dev flag; private broker ACL provided |
| 15 s cutoff could be starved by blocking reconnects | Hardware timer in v2 |
| Backend deployed on serverless | Unsupported; Render/Docker only |
