"""FastAPI app: /api routes, the daily scheduler, and the built frontend."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mhs.api import auth, routes
from mhs.config import settings

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if settings.scheduler_enabled and settings.environment != "test":
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        from mhs.cycle import run_cycle
        from mhs.db.engine import session_factory

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(run_cycle, CronTrigger(hour=settings.cycle_hour_utc, minute=0),
                          args=[session_factory()], id="daily-cycle", coalesce=True, max_instances=1)
        scheduler.start()
        log.info("scheduler: daily cycle at %02d:00 UTC", settings.cycle_hour_utc)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Horizont-Scanner Landkreis Miesbach", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes.open_router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(routes.router, prefix="/api")

if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = STATIC / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC / "index.html")
