from app.db.database import db_session
from app.core.config import settings

def dashboard_summary(plant_id: str):
    with db_session() as db:
        plant=db.execute('SELECT * FROM plants WHERE plant_id=?',(plant_id,)).fetchone()
        events=db.execute('SELECT * FROM irrigation_events WHERE plant_id=? ORDER BY id DESC LIMIT 20',(plant_id,)).fetchall()
        decisions=db.execute('SELECT * FROM decisions WHERE plant_id=? ORDER BY id DESC LIMIT 20',(plant_id,)).fetchall()
        count=db.execute("SELECT COUNT(*) n FROM irrigation_events WHERE plant_id=? AND source='auto' AND status NOT IN ('not_sent','failed_publish','rejected')",(plant_id,)).fetchone()['n']
    if not plant: return None
    with db_session() as db:
        st=db.execute("SELECT COUNT(*) n, COALESCE(SUM(duration_seconds),0) s, SUM(status='confirmed') c, SUM(status IN ('unconfirmed','unconfirmed_end')) u FROM irrigation_events WHERE plant_id=? AND source IN ('auto','manual') AND status NOT IN ('failed_publish','not_sent','rejected')",(plant_id,)).fetchone()
    totals={'commands_sent':st['n'],'requested_seconds':st['s'],'confirmed_by_telemetry':st['c'] or 0,'unconfirmed':st['u'] or 0,
            'note':'Counts come from recorded commands and device status only; no water-saving claim is made without a measured baseline experiment.'}
    estimated=sum(e['estimated_water_ml'] or 0 for e in events)
    known=all(e['estimated_water_ml'] is not None for e in events) if events else False
    # Baseline is illustrative and only shown as a configurable estimate, not measured water savings.
    baseline_ml=count*settings.default_water_seconds*(settings.flow_ml_per_second or 0)
    return {'plant':dict(plant),'recent_events':[dict(e) for e in events],'recent_decisions':[dict(d) for d in decisions], 'estimated_water_ml':round(estimated,1) if known else None,'water_saved_ml':None,'totals':totals,'baseline_estimate_ml':round(baseline_ml,1) if settings.flow_ml_per_second else None,'water_volume_note':'No calibrated flow rate configured; water volume and savings are unavailable.' if not settings.flow_ml_per_second else 'Volume is estimated from configured flow rate, not measured by a flow sensor.'}
