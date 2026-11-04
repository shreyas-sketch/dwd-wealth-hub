"""Central runtime settings (from Bullzeye core).

Everything that differs between local, staging and production is read here,
once, from the environment. New modules import from this file instead of
calling os.environ directly. (Legacy modules still read os.environ; they are
migrated as they are touched.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [p.strip() for p in (os.environ.get(name) or default).split(",") if p.strip()]


BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "development"))
    public_base_url: str = field(
        default_factory=lambda: os.environ.get("PUBLIC_BASE_URL", "http://localhost:8765").rstrip("/")
    )
    mongo_url: str = field(default_factory=lambda: os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_name: str = field(default_factory=lambda: os.environ.get("DB_NAME", "coinzeye"))

    # Auth cookies. Frontend and API share one origin on Railway, so Lax is right.
    cookie_secure: bool = field(default_factory=lambda: env_bool("COOKIE_SECURE", True))
    cookie_samesite: str = field(default_factory=lambda: os.environ.get("COOKIE_SAMESITE", "lax").lower())
    cookie_domain: str | None = field(default_factory=lambda: os.environ.get("COOKIE_DOMAIN") or None)

    # Observability
    sentry_dsn: str = field(default_factory=lambda: os.environ.get("SENTRY_DSN", ""))
    sentry_traces_rate: float = field(
        default_factory=lambda: float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05") or 0.05)
    )
    release: str = field(default_factory=lambda: os.environ.get("RAILWAY_GIT_COMMIT_SHA", "dev")[:12])

    # Static frontend (built React app) served by FastAPI in production.
    frontend_build_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("FRONTEND_BUILD_DIR", str(REPO_DIR / "frontend" / "build")))
    )

    brand_name: str = field(default_factory=lambda: os.environ.get("BRAND_NAME", "Coinzeye"))
    # In-process scheduler runs every job on its schedule. Turn off when an external cron calls /api/jobs/tick.
    inprocess_scheduler: bool = field(default_factory=lambda: env_bool("INPROCESS_SCHEDULER", True))
    qa_mode: bool = field(default_factory=lambda: env_bool("QA_MODE", False))

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
