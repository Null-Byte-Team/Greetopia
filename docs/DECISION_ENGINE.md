# Decision engine (v2.0)

`decide(inputs, params)` is a pure function; every decision stores its full inputs (`decisions.inputs_json`) and `engine_version`, so it can be reconstructed.
Thresholds come from the **plant profile** (`ideal_moisture_min` = trigger, `ideal_moisture_max` = satisfied level); the global `ROOT_MOISTURE_THRESHOLD` is only a fallback.
The values below are **initial experimental defaults, not universal agronomic facts**; tune them per plant.

| # | Rule | Outcome |
|---|---|---|
| 1 | Root reading missing, or older than `DECISION_MAX_AGE_S` (90 s) | skip (fail-safe) |
| 1 | Sensor sanity: root ~0% while mid/surface >= 30%, or root ~100% while both <= 15% | skip (probable disconnected/shorted probe) |
| 2 | Plant in Manual mode | skip |
| 3 | Pump reported `watering`; a command is pending/unconfirmed (1 h); cooldown (30 min); 6 commands or 60 s runtime in 24 h | skip |
| 4 | Root >= min + `HYSTERESIS_PCT` (5) | skip. Root < min -> candidate. Inside the band -> wait unless a falling trend **and** corroboration (vision wilting >= 0.7 confidence, or ML) justify pre-emptive watering |
| 5 | Trend = least-squares slope over 60 min (needs >= 6 points covering a third of the window), otherwise "unavailable" and none assumed | informs rule 4 |
| 6 | Rain probability >= 0.65 and root not critical (> min - 10 pts) | skip. Unknown forecast = no adjustment (never treated as 0% rain) |
| 7 | ML stress probability | not used: no validated model exists; reported as unavailable |
| 8 | Vision | secondary evidence only; can never trigger watering alone |
| 9-11 | Duration = 3 s + 0.4 s per % below the band top, bounded by 15 s and the remaining daily budget | water |

Execution: only when `AUTO_DECISIONS_ENABLED=true`; otherwise the decision is logged as advisory (`executed=0`). A missing acknowledgement never causes a repeat command.
