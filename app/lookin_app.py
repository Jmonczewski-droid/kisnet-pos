"""The look-in portal on its own.

Run this as a second, separate server and point the outside world (a tunnel or reverse proxy) at it:

    venv/bin/python -m uvicorn app.lookin_app:app --port 8001

It serves the look-in page and its read-only feed and nothing else. Ordering, employees, recipes,
devices, reports and clock-outs do not exist on this server, so they cannot be reached from outside
whatever address someone types.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import lookin
from app.core.config import settings
from app.core.headers import SecurityHeadersMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=f"{settings.PROJECT_NAME} look-in", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(lookin.router, prefix=settings.API_V1_STR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get(f"{settings.API_V1_STR}/portal")
def portal_mode():
    """Tells the page it is running as the look-in portal only."""
    return {"mode": "lookin"}


@app.get("/")
def read_root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def read_health_root():
    return {"status": "OK"}
