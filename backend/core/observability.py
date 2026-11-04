"""Sentry wiring. No-op when SENTRY_DSN is empty (local, tests)."""
from __future__ import annotations

import logging

from .settings import settings

log = logging.getLogger("core.observability")
_initialised = False

# Never ship these to Sentry.
_SCRUB_KEYS = {"otp", "code", "password", "access_token", "refresh_token", "authorization", "cookie", "pan", "phone"}


def _scrub(event, _hint):
    req = event.get("request") or {}
    for bucket in ("headers", "cookies", "data"):
        data = req.get(bucket)
        if isinstance(data, dict):
            for k in list(data.keys()):
                if k.lower() in _SCRUB_KEYS:
                    data[k] = "[scrubbed]"
    return event


def init_sentry(component: str = "api") -> bool:
    global _initialised
    if _initialised or not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:  # pragma: no cover
        log.warning("sentry-sdk not installed; skipping Sentry init")
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.release,
        traces_sample_rate=settings.sentry_traces_rate,
        send_default_pii=False,
        before_send=_scrub,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    sentry_sdk.set_tag("component", component)
    _initialised = True
    log.info("Sentry initialised (env=%s, release=%s)", settings.env, settings.release)
    return True
