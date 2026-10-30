from datetime import datetime, timezone, date
from app.db.database import db_session
from app.services.telemetry import latest_readings

def create_daily_entry(plant_id: str, day: date | None=None):
    day=day or datetime.now(timezone.utc).date(); readings=latest_readings(plant_id)
    root=readings.get('soil_root'); temp=readings.get('temperature_c'); hum=readings.get('humidity_pct')
    # Transparent template, not an LLM-generated claim.
    lines=[f"Today, my care system checked my condition on {day.isoformat()}."]
    lines.append(f"My latest root-zone moisture was {root['value']:.1f}% (fresh: {'yes' if root['fresh'] else 'no'})." if root else 'My root-zone moisture reading was unavailable.')
    lines.append(f"The latest temperature was {temp['value']:.1f} °C." if temp else 'Temperature data was unavailable.')
    lines.append(f"The latest air humidity was {hum['value']:.1f}%." if hum else 'Air humidity data was unavailable.')
    lines.append('These are sensor observations, not a diagnosis of plant health.')
    content=' '.join(lines); now=datetime.now(timezone.utc).isoformat()
    with db_session() as db:
        db.execute('INSERT INTO diary_entries(plant_id,day,content,created_at) VALUES(?,?,?,?) ON CONFLICT(plant_id,day) DO UPDATE SET content=excluded.content,created_at=excluded.created_at',(plant_id,day.isoformat(),content,now))
    return {'plant_id':plant_id,'day':day.isoformat(),'content':content,'created_at':now}
