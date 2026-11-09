"""MedIAData API: FastAPI app assembly.

Modules:
    config     settings from .env
    db         SQLite schema & migrations
    records    record helpers (names, statuses, project state, late)
    shotgrid   ShotGrid client
    sync       full/incremental sync, scheduler, audit
    retrieval  question -> scoped records + exact stats (assistant)
    assistant  streamed assistant endpoint
    auth       Google OAuth
    api        read API for the UI
"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend import api, assistant, auth, config, sync
from backend.db import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A sync cannot survive a server restart, so any run still "running" is dead.
    connection = database()
    try:
        sync.fail_stale_sync_runs(connection, older_than=None)
    finally:
        connection.close()
    scheduler = asyncio.create_task(sync.scheduler_loop())
    try:
        yield
    finally:
        scheduler.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler


app = FastAPI(title="MedIAData Dashboard API", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.settings.app_secret,
    same_site="lax",
    https_only=config.settings.app_base_url.startswith("https://"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        config.settings.app_base_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api.router)
app.include_router(assistant.router)
app.include_router(auth.router)

# Static frontend: only ever serve the Vite build output. Never fall back to the
# project root, which holds .env (credentials) and the SQLite database.
DIST_DIR = config.PROJECT_ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
else:
    @app.get("/")
    async def frontend_missing() -> dict[str, str]:
        raise HTTPException(
            status_code=503,
            detail="Frontend non compilé : lancez `npm run build` dans frontend/.",
        )
