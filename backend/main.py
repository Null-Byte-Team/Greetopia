import sys
import traceback
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

_import_error: str | None = None

try:
    from app.main import app  # noqa: F401
except Exception as _exc:  # pragma: no cover
    _import_error = traceback.format_exc()
    from fastapi import FastAPI
    app = FastAPI(title="Greetopia API – startup error")

    @app.get("/{path:path}")
    def _startup_error(path: str = ""):  # type: ignore[misc]
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"error": "startup_import_failed", "detail": _import_error},
        )

__all__ = ["app"]
