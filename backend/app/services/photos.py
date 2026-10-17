from pathlib import Path
from datetime import datetime, timezone
import uuid
from app.core.config import settings
from app.db.database import db_session

def save_photo(plant_id: str, body: bytes, content_type: str | None):
    if not plant_id or len(plant_id)>48 or not all(c.isalnum() or c in '_-' for c in plant_id): raise ValueError('Invalid X-Plant-Id')
    if not body: raise ValueError('Empty image body')
    if len(body)>settings.max_photo_bytes: raise ValueError('Image exceeds configured size limit')
    if content_type and content_type.lower().split(';')[0].strip() not in {'image/jpeg','image/jpg','application/octet-stream'}: raise ValueError('Content-Type must be image/jpeg')
    # JPEG signature validation; no path component comes from an unchecked filename.
    if not body.startswith(b'\xff\xd8\xff'): raise ValueError('Body is not a valid JPEG stream')
    now=datetime.now(timezone.utc); capture_id=str(uuid.uuid4())
    folder=Path(settings.photo_dir)/plant_id; folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{now.strftime("%Y%m%dT%H%M%S_%fZ")}_{capture_id[:8]}.jpg'
    path.write_bytes(body)
    with db_session() as db:
        db.execute('INSERT INTO photos(plant_id,capture_id,file_path,received_at) VALUES(?,?,?,?)',(plant_id,capture_id,str(path),now.isoformat()))
    return {'plant_id':plant_id,'capture_id':capture_id,'received_at':now.isoformat(),'url':f'/api/v1/photos/{plant_id}/{path.name}'}

def latest_photo(plant_id: str):
    with db_session() as db: row=db.execute('SELECT * FROM photos WHERE plant_id=? ORDER BY id DESC LIMIT 1',(plant_id,)).fetchone()
    if not row: return None
    p=Path(row['file_path'])
    return {'plant_id':row['plant_id'],'capture_id':row['capture_id'],'received_at':row['received_at'],'url':f'/api/v1/photos/{plant_id}/{p.name}','vision':__import__('json').loads(row['vision_json']) if row['vision_json'] else None}
