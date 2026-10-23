import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.db.database import db_session
from app.services.auth import sign_photo

PLANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
Image.MAX_IMAGE_PIXELS = settings.max_photo_pixels


def photo_root() -> Path:
    return Path(settings.photo_dir).resolve()


def resolve_photo_path(file_path: str) -> Path | None:
    """Resolve a stored key (relative 'plant/file.jpg', or a legacy absolute path) strictly inside the photo root."""
    root = photo_root()
    candidate = Path(file_path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        # legacy rows stored absolute paths: accept only if the file name lives under <root>/<plant>/
        legacy = root / candidate.parent.name / candidate.name
        return legacy if legacy.is_file() else None
    return resolved if resolved.is_file() else None


def photo_url(plant_id: str, filename: str) -> str:
    return f"/api/v1/photos/{plant_id}/{filename}?{sign_photo(f'{plant_id}/{filename}')}"


def save_photo(plant_id: str, body: bytes, content_type: str | None):
    if not PLANT_ID_RE.fullmatch(plant_id or ""):
        raise ValueError("Invalid X-Plant-Id")
    if not body:
        raise ValueError("Empty image body")
    if len(body) > settings.max_photo_bytes:
        raise ValueError("Image exceeds configured size limit")
    if content_type and content_type.lower().split(";")[0].strip() not in {"image/jpeg", "image/jpg", "application/octet-stream"}:
        raise ValueError("Content-Type must be image/jpeg")
    if not body.startswith(b"\xff\xd8\xff"):
        raise ValueError("Body is not a JPEG stream")
    try:  # decode fully: magic bytes alone prove nothing
        with Image.open(io.BytesIO(body)) as img:
            if img.format != "JPEG":
                raise ValueError("Body is not a JPEG image")
            width, height = img.size
            img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Image could not be decoded as a valid JPEG") from exc
    digest = hashlib.sha256(body).hexdigest()
    now = datetime.now(timezone.utc)
    with db_session() as db:
        dup = db.execute("SELECT * FROM photos WHERE plant_id=? AND sha256=?", (plant_id, digest)).fetchone()
        if dup:  # camera retry of the same capture: do not store or analyze twice
            name = Path(dup["file_path"]).name
            return {"plant_id": plant_id, "capture_id": dup["capture_id"], "received_at": dup["received_at"],
                    "url": photo_url(plant_id, name), "duplicate": True}
    capture_id = str(uuid.uuid4())
    folder = photo_root() / plant_id
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{now.strftime('%Y%m%dT%H%M%S_%fZ')}_{capture_id[:8]}.jpg"
    (folder / name).write_bytes(body)
    key = f"{plant_id}/{name}"
    with db_session() as db:
        db.execute("INSERT INTO photos(plant_id,capture_id,file_path,received_at,sha256,width,height,vision_status) VALUES(?,?,?,?,?,?,?,?)",
                   (plant_id, capture_id, key, now.isoformat(), digest, width, height, "none"))
    return {"plant_id": plant_id, "capture_id": capture_id, "received_at": now.isoformat(), "url": photo_url(plant_id, name),
            "width": width, "height": height, "capture_time_source": "server_receive", "duplicate": False}


def latest_photo(plant_id: str):
    with db_session() as db:
        row = db.execute("SELECT * FROM photos WHERE plant_id=? ORDER BY id DESC LIMIT 1", (plant_id,)).fetchone()
    if not row:
        return None
    return {"plant_id": row["plant_id"], "capture_id": row["capture_id"], "received_at": row["received_at"],
            "capture_time_source": "server_receive", "url": photo_url(plant_id, Path(row["file_path"]).name),
            "vision_status": row["vision_status"], "vision_error": row["vision_error"],
            "vision": json.loads(row["vision_json"]) if row["vision_json"] else None}
