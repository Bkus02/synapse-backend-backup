from contextlib import asynccontextmanager

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
from app.api.routes.users import router as users_router
from app.db.database import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Verify DB connectivity on startup.
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
    yield


app = FastAPI(title="Synapse Backend", lifespan=lifespan)

# Local dev (e.g. Flutter web on Chrome). Tighten origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return "Synapse system is running"


# Hexagonal-style layout:
# - inbound adapters: app/api/routes/*
# - application services: app/application/services/*
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(environments_router)
app.include_router(devices_router)
app.include_router(behavior_logs_router)
app.include_router(habits_router)
