from __future__ import annotations
import sys
import os
import traceback
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Greetopia API")

@app.get("/api/v1/health")
@app.get("/health")
def _fallback_health():
    return {
        "status": "ok",
        "service": "Greetopia API",
        "python": sys.version,
        "mode": "standalone_fallback"
    }

_startup_error = None
try:
    from app.main import app as full_app
    app = full_app
except BaseException:
    _startup_error = traceback.format_exc()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"])
    def _report_error(path: str = ""):
        return JSONResponse(
            status_code=503,
            content={"error": "startup_failed", "detail": _startup_error}
        )

__all__ = ["app"]
