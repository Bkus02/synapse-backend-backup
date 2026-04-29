import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlmodel import Session

from app.api.routes.auth import router as auth_router
from app.api.routes.behavior_logs import router as behavior_logs_router
from app.api.routes.devices import router as devices_router
from app.api.routes.environments import router as environments_router
from app.api.routes.habits import router as habits_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.users import router as users_router
from app.application.services import smart_home_service
from app.db.database import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Uygulama açılırken veritabanına bağlanabildiğimizi doğrula.
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
    stop_event = asyncio.Event()

    async def _habit_matrix_scheduler() -> None:
        while not stop_event.is_set():
            now = datetime.now()
            next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run + timedelta(days=1)
            wait_sec = (next_run - now).total_seconds()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_sec)
                break
            except TimeoutError:
                with Session(engine) as bg_session:
                    smart_home_service.rebuild_habit_matrix(bg_session)

    task = asyncio.create_task(_habit_matrix_scheduler())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except Exception:
            pass


app = FastAPI(title="Synapse Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return "Synapse Sistemi Aktif"


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/readyz", response_class=PlainTextResponse)
def readyz() -> str:
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
    return "ready"


# Hexagonal yaklaşım:
# - inbound adapter: app/api/routes/*
# - application service: app/application/services/*
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(environments_router)
app.include_router(devices_router)
app.include_router(behavior_logs_router)
app.include_router(habits_router)
app.include_router(recommendations_router)
