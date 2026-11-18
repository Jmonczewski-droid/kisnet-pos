from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, devices, health, lookin, menu, orders, parties, reports, seats, tickets, timecard
from app.core.config import settings
from app.core.headers import SecurityHeadersMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json")

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth")
for module in (seats, parties, orders, tickets, menu, admin, devices, lookin, reports, timecard, health):
    app.include_router(module.router, prefix=settings.API_V1_STR)

app.add_middleware(SecurityHeadersMiddleware)


@app.get(f"{settings.API_V1_STR}/portal")
def portal_mode():
    """The full POS. (The look-in-only server answers "lookin" here.)"""
    return {"mode": "full"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def read_root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def read_health_root():
    return {"status": "OK"}
