from datetime import datetime, timezone
from app.db.database import db_session
from app.services.telemetry import latest_readings
from app.services.vpd import calculate_vpd, vpd_band

def answer_question(plant_id: str, question: str):
    readings=latest_readings(plant_id)
    with db_session() as db:
        plant=db.execute('SELECT * FROM plants WHERE plant_id=?',(plant_id,)).fetchone()
        decisions=db.execute('SELECT decision,reason,created_at FROM decisions WHERE plant_id=? ORDER BY id DESC LIMIT 3',(plant_id,)).fetchall()
    if not plant: return {'answer':'This plant is not registered yet. Add it in Plant Profiles first.','grounded':True}
    root=readings.get('soil_root'); temp=readings.get('temperature_c'); hum=readings.get('humidity_pct')
    parts=[f"Plant profile: {plant['name']} ({plant['species'] or 'species not confirmed'}), stage: {plant['growth_stage'] or 'not set'}."]
    if root: parts.append(f"Latest root-zone moisture: {root['value']}%, {'fresh' if root['fresh'] else 'stale'} reading.")
    else: parts.append('No root-zone moisture reading is available.')
    if temp and hum:
        vpd=calculate_vpd(temp['value'],hum['value']); parts.append(f"Latest temperature {temp['value']} °C, humidity {hum['value']}%, VPD {vpd} kPa ({vpd_band(vpd)}).")
    parts.append(f"Configured ideal moisture range: {plant['ideal_moisture_min']}–{plant['ideal_moisture_max']}%.")
    if decisions: parts.append(f"Most recent decision: {decisions[0]['decision']}. Reason: {decisions[0]['reason']}")
    parts.append('This prototype answers from stored profile and sensor data only; it does not call an LLM or diagnose disease. If a reading is stale or missing, verify the sensor before acting.')
    answer=' '.join(parts); now=datetime.now(timezone.utc).isoformat()
    with db_session() as db:
        db.execute('INSERT INTO chat_messages(plant_id,role,content,created_at) VALUES(?,?,?,?)',(plant_id,'user',question,now))
        db.execute('INSERT INTO chat_messages(plant_id,role,content,created_at) VALUES(?,?,?,?)',(plant_id,'assistant',answer,now))
    return {'answer':answer,'grounded':True,'llm_used':False}
