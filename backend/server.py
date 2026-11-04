"""App entry point: `uvicorn server:app`.

create_app(db=None) builds the FastAPI app; tests pass a mongomock database.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import APIRouter, FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("server")

ROUTER_MODULES = [
    "auth", "accounts.routes", "misc_routes", "notify.service", "billing.routes", "jobs.routes", "admin.routes",
    "features.whatif", "features.xray", "features.verdicts", "features.plan", "features.paper", "features.airdrops",
    "features.autopilot", "features.chart", "features.ask", "features.baskets", "features.radar", "features.calendar",
    "features.p2p", "features.news",
]


def create_app(db=None, *, start_jobs: bool | None = None, seed: bool | None = None, serve_spa: bool = True) -> FastAPI:
    import importlib

    import state
    from core.health import bind_db as bind_health, router as health_router
    from core.observability import init_sentry
    from core.settings import settings
    from growth import events

    init_sentry("api")
    if db is None:
        from motor.motor_asyncio import AsyncIOMotorClient
        db = AsyncIOMotorClient(settings.mongo_url, tz_aware=True)[settings.db_name]
    state.set_db(db)

    app = FastAPI(title=f"{settings.brand_name} API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = [o.strip() for o in (os.environ.get("CORS_ORIGINS") or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    api = APIRouter(prefix="/api")
    api.include_router(health_router)
    bind_health(db)
    events.bind_db(db)
    api.include_router(events.router)
    for name in ROUTER_MODULES:
        mod = importlib.import_module(name)
        if hasattr(mod, "bind_db"):
            mod.bind_db(db)
        if hasattr(mod, "bind"):
            mod.bind(db)
        api.include_router(mod.router)
    app.include_router(api)

    run_jobs = settings.inprocess_scheduler if start_jobs is None else start_jobs
    do_seed = settings.qa_mode if seed is None else seed

    @app.on_event("startup")
    async def _startup():
        import asyncio

        from auth import seed_admin
        from core import flags
        from indexes import ensure_indexes
        await ensure_indexes(db)
        await flags.refresh(db, force=True)
        # With several workers (WEB_CONCURRENCY > 1) every worker runs this startup at the same moment:
        # only the one that wins the Mongo lease seeds, so nothing is inserted twice.
        from jobs.registry import claim_lock, release_lock
        if await claim_lock(db, "_startup_seed", minutes=5):
            try:
                await seed_admin(db)
                from features.calendar import ensure_seed
                await ensure_seed(db)
                if do_seed:
                    from seed import seed_demo
                    await seed_demo(db)
            finally:
                await release_lock(db, "_startup_seed")

        async def _keep_flags_fresh():
            while True:
                await asyncio.sleep(flags.REFRESH_SECONDS)
                await flags.refresh(db, force=True)
        app.state.flag_task = asyncio.get_event_loop().create_task(_keep_flags_fresh())
        if run_jobs:
            from jobs.registry import start_scheduler
            app.state.scheduler = start_scheduler(db)
            log.info("in-process scheduler started")

    @app.on_event("shutdown")
    async def _shutdown():
        t = getattr(app.state, "flag_task", None)
        if t:
            t.cancel()
        s = getattr(app.state, "scheduler", None)
        if s:
            s.shutdown(wait=False)

    if serve_spa:
        from core.spa import mount_spa
        mount_spa(app)
    return app


def _default_app():
    if os.environ.get("APP_LAZY") == "1":
        return None
    return create_app()


app = _default_app()
