"""All series below are SYNTHETIC and exist only to test the code. They are never presented as results."""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import db_session
from app.services import insights
from app.services.insights import kpis_from_points, response_for_event, probe_health, fit_demand

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def pts(values, step=10, start=T0):
    return [(start + timedelta(seconds=i * step), v) for i, v in enumerate(values)]


def seed(metric, points, plant="plant01"):
    with db_session() as db:
        db.executemany("INSERT INTO readings(plant_id,metric,value,received_at,topic) VALUES(?,?,?,?,?)", [(plant, metric, v, t.isoformat(), "test") for t, v in points])


def seed_event(start, seconds=5, status="confirmed"):
    with db_session() as db:
        db.execute("INSERT INTO irrigation_events(plant_id,created_at,source,duration_seconds,command_id,status,observed_start_at,observed_end_at) VALUES(?,?,?,?,?,?,?,?)",
                   ("plant01", start.isoformat(), "auto", seconds, "c", status, start.isoformat(), (start + timedelta(seconds=seconds)).isoformat()))


def test_kpis_hand_checked():
    values = [50] * 361 + [20] * 360  # 1 h in range then 1 h below min 35
    k = kpis_from_points(pts(values), low=35, high=65)
    assert k["available"] and abs(k["time_in_range_pct"] - 50) < 1 and abs(k["below_min_hours"] - 1) < 0.01
    assert abs(k["stress_integral_pct_hours"] - 15) < 0.2  # (35-20) points x 1 h


def test_kpis_do_not_bridge_gaps_or_invent_coverage():
    a, b = pts([50] * 400), pts([20] * 400, start=T0 + timedelta(hours=10))
    k = kpis_from_points(a + b, 35, 65)
    assert k["covered_hours"] < 2.5 and k["below_min_hours"] < 1.2  # the 10 h gap is unknown, not "20%"
    assert kpis_from_points(pts([50] * 100), 35, 65)["available"] is False  # < 1 h of coverage


def test_response_for_event_delay_gain_and_no_response():
    start = T0 + timedelta(minutes=10)
    vals = [30] * 61 + [30] * 30 + [36] * 100  # rise 5 minutes after the event start
    out = response_for_event(start, {"root": pts(vals), "surface": pts([40] * 200)})
    assert out["root"]["responded"] and out["root"]["gain"] == 6 and 290 <= out["root"]["delay_s"] <= 320
    assert out["surface"]["responded"] is False
    assert response_for_event(start, {"root": pts([30] * 3)})["root"]["available"] is False


def build_events(n, root_gain):
    for i in range(n):
        st = T0 + timedelta(hours=3 * i + 1)
        base = T0 + timedelta(hours=3 * i)
        seed_event(st)
        for metric, g in (("soil_surface", 8), ("soil_mid", 4), ("soil_root", root_gain)):
            vals = [30.0] * 361 + [30.0 + g] * 400   # 1 h before the event, then a step at the event
            seed(metric, pts(vals, start=base))


def test_fingerprint_available_and_unavailable(env, monkeypatch):
    assert insights.response_fingerprint("plant01", days=3650)["available"] is False
    build_events(4, root_gain=6)
    monkeypatch.setattr(insights, "_now", lambda: T0 + timedelta(days=2))
    out = insights.response_fingerprint("plant01", days=30)
    assert out["available"] and out["events_used"] == 4 and out["aggregate"]["root"]["response_rate"] == 1.0
    assert out["hypotheses"] == []


def test_fingerprint_hypothesis_when_root_never_responds(env, monkeypatch):
    build_events(4, root_gain=0)
    monkeypatch.setattr(insights, "_now", lambda: T0 + timedelta(days=2))
    out = insights.response_fingerprint("plant01", days=30)
    assert any("root probe does not" in h for h in out["hypotheses"])


def test_pump_health_flags_no_delivery_streak(env, monkeypatch):
    for i in range(4):
        st = T0 + timedelta(hours=3 * i + 1)
        seed_event(st)
        for metric in ("soil_surface", "soil_mid", "soil_root"):
            seed(metric, pts([30.0] * 761, start=T0 + timedelta(hours=3 * i)))
    monkeypatch.setattr(insights, "_now", lambda: T0 + timedelta(days=2))
    out = insights.pump_health("plant01", 30)
    assert out["available"] and out["no_response_streak"] >= 3 and any("empty tank" in f for f in out["flags"])


def test_microclimate_indicators(env, monkeypatch):
    n = 400 * 3  # ~3.3 h
    seed("temperature_c", pts([25.0] * n)); seed("humidity_pct", pts([90.0] * n))
    monkeypatch.setattr(insights, "_now", lambda: T0 + timedelta(days=1))
    m = insights.microclimate("plant01", 7)
    assert m["available"] and m["fungal_risk_hours"] > 3 and m["fungal_risk_index"] > 95 and m["heat_stress_hours"] == 0
    assert "diagnosis" in m["note"]
    assert insights.microclimate("plant02", 7)["available"] is False


def test_probe_health_detects_stuck_and_spikes():
    stuck = probe_health(pts([40.0] * 300), 1, other_ranges=[5.0])
    assert stuck["stuck"] and stuck["score"] <= 60 and stuck["reasons"]
    spiky = probe_health(pts([40, 90] * 150), 1, other_ranges=[5.0])
    assert spiky["spikes"] >= 100 and spiky["score"] < 50
    assert probe_health(pts([40.0] * 10), 1, [5.0])["available"] is False


def test_fit_demand_real_relation_vs_noise():
    import random
    rnd = random.Random(1)
    good = [(v := 0.4 + 1.2 * rnd.random(), -0.3 - 0.8 * v + rnd.gauss(0, 0.05), i) for i in range(120)]
    fit = fit_demand(good)
    assert fit["available"] and fit["slope_per_kpa"] < -0.5 and fit["mae_model"] < fit["mae_baseline_persistence"]
    noise = [(0.4 + 1.2 * rnd.random(), rnd.gauss(-0.5, 0.4), i) for i in range(120)]
    assert fit_demand(noise)["available"] is False  # does not beat the baselines -> hidden, not shown as a forecast
    assert fit_demand(good[:10])["available"] is False


def test_weekly_report_both_languages_without_data(env):
    en, ar = insights.weekly_report("plant01", "en"), insights.weekly_report("plant01", "ar")
    assert en["lines"][0] == "Not enough recorded data for this section yet." and ar["title"] == "التقرير الأسبوعي" and "no LLM" in en["source"]


def test_insights_never_send_pump_commands(env, monkeypatch):
    from app.services import irrigation
    monkeypatch.setattr(irrigation, "publish_water", lambda *a, **k: (_ for _ in ()).throw(AssertionError("insights tried to publish a command")))
    insights.summary("plant01", 7)
    insights.run_alert_rules("plant01")
    insights.weekly_report("plant01")


def test_insight_endpoints_auth_and_limits(client, admin):
    assert client.get("/api/v1/plants/plant01/insights/summary").status_code == 401
    assert client.get("/api/v1/plants/plant01/insights/summary?days=500", headers=admin).status_code == 422
    r = client.get("/api/v1/plants/plant01/insights/summary", headers=admin)
    assert r.status_code == 200 and r.json()["kpis"]["label"] == "derived"
    assert client.get("/api/v1/plants/plant01/insights/weekly?lang=ar", headers=admin).json()["lang"] == "ar"
    assert client.get("/api/v1/plants/plant01/insights/weekly?lang=xx", headers=admin).status_code == 422


def test_alert_rule_saturation(env, monkeypatch):
    seed("soil_root", pts([97.0] * 2400))  # ~6.7 h saturated
    monkeypatch.setattr(insights, "_now", lambda: T0 + timedelta(hours=8))
    assert insights.run_alert_rules("plant01") >= 1
    with db_session() as db:
        assert db.execute("SELECT 1 FROM alerts WHERE kind='sustained_saturation'").fetchone()
