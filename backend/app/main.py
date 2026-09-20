import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.getLogger("app").setLevel(logging.INFO)

from app.core.config import settings
from app.core.database import SessionLocal
from app.routers import auth, bills, export, stats
from app.services.reminder_job import send_catchup_reminders, send_daily_reminders
from app.services.snapshot_cleanup import cleanup_old_snapshots


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_daily_reminders,
        "cron",
        minute="0,30",
        args=[SessionLocal],
    )
    scheduler.add_job(
        cleanup_old_snapshots,
        "cron",
        hour=3,
        args=[SessionLocal],
    )
    scheduler.start()
    # Run once on startup (non-blocking) so the current hour's reminders aren't missed after a restart
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, send_catchup_reminders, SessionLocal)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Pay Tracker API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(bills.router)
app.include_router(export.router)
app.include_router(stats.router)


@app.get("/health")
def health():
    return {"status": "ok"}
