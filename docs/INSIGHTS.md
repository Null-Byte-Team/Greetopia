# Insights (derived from the data the hardware already sends)

All endpoints are read-only, under `/api/v1/plants/{id}/insights/...`, need a signed-in user, and **can never publish a pump command** (a test enforces this).
Every result is labelled `derived`, carries its window and sample count, and returns `available: false` with a reason when its minimum-data rule is not met. A gap longer than 120 s is "unknown", never interpolated.

| Metric | Formula / method | Minimum data | Cannot tell you |
|---|---|---|---|
| Stress KPIs (`kpis`) | Time-weighted: each sample holds until the next one (gaps > 120 s excluded). Time in range, hours below min / above max, saturation (>= 95%), **stress integral** = sum of (min - value) x hours below the plant minimum, std, IQR | >= 1 h continuous coverage | Why moisture was low |
| Response fingerprint (`response`) | For each *confirmed* watering: baseline = median of the 5 min before; gain = peak - baseline within 90 min; delay = first time >= baseline + 2 points | >= 3 confirmed events with all three depths covered | Diagnoses; hypotheses are prompts to inspect |
| Microclimate | Hours with T > 35 C; VPD < 0.4 or > 1.6 kPa; fungal-risk hours (RH >= 85% and 15-28 C) and index = share of covered time | >= 100 temp + humidity samples, >= 1 h paired | Disease presence (leaf wetness is not measured) |
| Integrity | Per probe: stuck (no change while others change), jumps >= 25 points, median step (noise), coverage; score 0-100. Connectivity from inter-arrival gaps | >= 50 samples (20 for connectivity) | Whether the probe is correctly calibrated |
| Pump health | commanded vs confirmed, observed/requested time, streak of waterings with no response at any probe | >= 3 sent commands | Flow or volume (no flow sensor); efficiency only with a configured flow rate and labelled *estimated* |
| Demand model | Hourly dry-down (hours without watering) regressed on VPD; chronological 70/30 split; shown only if it beats the mean and persistence baselines on held-out hours | >= 48 dry-down hours, VPD range >= 0.3 kPa | Anything under conditions outside the training range |
| Growth proxy (`growth`) | Photo green-pixel fraction from the excess-green index on chromatic coordinates; slope per day | >= 10 photos spanning >= 2 days | Biomass; needs constant camera position and lighting |
| Weekly report | Deterministic EN/AR templates over the numbers above (no LLM) | - | - |

Alerts generated hourly (deduplicated for 30 min): sustained saturation, sustained dry, pump no-response, unhealthy probe.
