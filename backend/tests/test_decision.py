from app.services.decision_engine import Inputs, Params, decide

P = Params()


def inp(**kw):
    base = dict(mode="auto", low_pct=35, target_pct=65, root=20, root_age_s=10, mid=40, surface=40)
    base.update(kw)
    return Inputs(**base)


def test_waters_when_below_profile_minimum():
    d = decide(inp(), P)
    assert d.action == "water" and 3 <= d.duration_s <= 15


def test_uses_plant_profile_not_a_global_threshold():
    assert decide(inp(root=45, low_pct=60, target_pct=80, mid=50, surface=50), P).action == "water"
    assert decide(inp(root=45, low_pct=30, target_pct=50), P).code == "moisture_ok"


def test_hysteresis_band_waits_without_corroboration():
    d = decide(inp(root=37), P)  # 35..40 band
    assert d.action == "skip" and d.code == "within_hysteresis"


def test_preemptive_watering_needs_trend_and_corroboration():
    assert decide(inp(root=37, trend_pct_per_hour=-8), P).action == "skip"
    assert decide(inp(root=37, trend_pct_per_hour=-8, vision_wilting=True, vision_confidence=0.9), P).action == "water"
    assert decide(inp(root=37, vision_wilting=True, vision_confidence=0.9), P).action == "skip"


def test_fail_safe_on_missing_or_stale_data():
    assert decide(inp(root=None, root_age_s=None), P).code == "no_root_reading"
    assert decide(inp(root_age_s=500), P).code == "stale_root_reading"


def test_disconnected_probe_pattern_does_not_water():
    d = decide(inp(root=0, mid=80, surface=80), P)
    assert d.action == "skip" and d.code == "sensor_suspect"
    assert decide(inp(root=100, mid=5, surface=5), P).code == "sensor_suspect"


def test_manual_mode_blocks_auto():
    assert decide(inp(mode="manual"), P).code == "manual_mode"


def test_safety_blocks():
    assert decide(inp(pump_status="watering", pump_status_age_s=3), P).code == "pump_running"
    assert decide(inp(pending_command=True), P).code == "pending_command"
    assert decide(inp(seconds_since_last_command=60), P).code == "cooldown"
    assert decide(inp(commands_24h=6), P).code == "daily_command_limit"
    assert decide(inp(runtime_24h_s=59), P).code == "daily_runtime_limit"


def test_duration_respects_firmware_limit_and_remaining_budget():
    assert decide(inp(root=0.5, mid=1, surface=1), Params(seconds_per_deficit_pct=10)).duration_s <= 15
    assert decide(inp(runtime_24h_s=55), P).duration_s == 5


def test_weather_missing_is_not_zero_rain():
    d = decide(inp(rain_probability=None), P)
    assert d.action == "water" and any("unavailable" in r for r in d.reasons)


def test_rain_defers_unless_critical():
    assert decide(inp(root=30, rain_probability=0.9), P).code == "rain_expected"
    assert decide(inp(root=10, rain_probability=0.9), P).action == "water"


def test_ml_is_reported_unavailable_not_invented():
    assert any("ML stress predictor unavailable" in r for r in decide(inp(), P).reasons)


def test_engine_logs_reconstructable_inputs(env):
    import json
    from app.db.database import db_session
    from app.services.decision_engine import evaluate_plant
    from app.services.telemetry import record_reading
    record_reading("plant01", "soil_root", 10.0, "t")
    res = evaluate_plant("plant01", execute=False)
    assert res["decision"] == "water" and res["executed"] is False
    with db_session() as db:
        row = db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
    assert row["engine_version"] and json.loads(row["inputs_json"])["root"] == 10.0
