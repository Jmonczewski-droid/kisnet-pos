from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, auth, health, menu, orders, parties, reports, seats, tickets
from app.core.config import settings

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json")

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth")
for module in (seats, parties, orders, tickets, menu, admin, reports, health):
    app.include_router(module.router, prefix=settings.API_V1_STR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def read_root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def read_health_root():
    return {"status": "OK"}
