"""Shared outbound HTTP: one pooled httpx client per event loop, plus small resilience helpers.

Hot paths (market data, OTP delivery, WhatsApp alerts) used to open a new client, so a new TCP+TLS handshake,
for every call. In a webinar burst (500 OTPs and thousands of price reads in a minute) that adds latency and
sockets for nothing. `shared_client()` keeps connections alive and reuses them.

    client = shared_client()
    r = await client.get(url, timeout=10)      # per-request timeouts still apply

The client is keyed by event loop (httpx pools are loop-bound; tests run many loops) and closed on app shutdown
by `aclose_all()`.

Also here:
  TokenBucket     async rate limiter for one upstream (e.g. CoinGecko's ~30 calls/min free tier)
  CircuitBreaker  skip a failing upstream for a cool-down instead of making every caller wait for its timeout
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
from contextlib import contextmanager
import os
import time
from typing import Optional

import httpx

log = logging.getLogger("core.http")

_clients: dict[int, httpx.AsyncClient] = {}


def shared_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    c = _clients.get(id(loop))
    if c is None or c.is_closed:
        c = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=int(os.environ.get("HTTP_MAX_CONNECTIONS", "100") or 100),
                                max_keepalive_connections=20, keepalive_expiry=30),
            headers={"user-agent": f"{os.environ.get('BRAND_NAME', 'Coinzeye')}/1.0"})
        _clients[id(loop)] = c
    return c


async def aclose_all() -> None:
    for k, c in list(_clients.items()):
        try:
            await c.aclose()
        except Exception:  # noqa: BLE001
            pass
        _clients.pop(k, None)


# How long a call may wait for an upstream's rate budget. Page requests use each source's short default (a member is
# waiting); scheduled jobs run inside `patient()` and wait as long as it takes, so a burst of radar X-Rays queues for
# CoinGecko's budget instead of failing (QA 10 Nov: radar coins shown as failed checks).
_patience: contextvars.ContextVar[float] = contextvars.ContextVar("api_patience", default=0.0)


@contextmanager
def patient(seconds: float):
    token = _patience.set(seconds)
    try:
        yield
    finally:
        _patience.reset(token)


def wait_budget(default: float) -> float:
    return max(default, _patience.get())


class RateLimited(RuntimeError):
    """Raised instead of calling an upstream that is over its budget or cooling down after a 429."""


class TokenBucket:
    """`rate` calls per `per` seconds, bursts up to `burst`. `acquire(max_wait)` waits for a token up to max_wait
    seconds, else raises RateLimited, so callers can serve a cached value instead of queueing forever.
    `cool_down(seconds)` blocks all calls (e.g. after the upstream answered 429 with Retry-After)."""

    def __init__(self, rate: float, per: float = 60.0, burst: Optional[float] = None, name: str = "upstream"):
        self.rate, self.per, self.name = float(rate), float(per), name
        self.capacity = float(burst if burst is not None else max(5.0, rate / 2))
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self.blocked_until = 0.0
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[int] = None

    def _refill(self, now: float) -> None:
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate / self.per)
        self.updated = now

    def _get_lock(self) -> asyncio.Lock:
        loop = id(asyncio.get_running_loop())
        if self._lock is None or self._lock_loop != loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    def reset(self) -> None:
        self.tokens, self.updated, self.blocked_until = self.capacity, time.monotonic(), 0.0

    def cool_down(self, seconds: float) -> None:
        self.blocked_until = max(self.blocked_until, time.monotonic() + max(0.0, seconds))
        log.warning("%s: cooling down for %.0fs", self.name, seconds)

    async def acquire(self, max_wait: float = 5.0, cost: float = 1.0) -> None:
        """Take `cost` tokens (a Twelve Data batch of N coins costs N credits). A cost above the bucket's capacity
        can never be paid, so it fails at once instead of waiting."""
        deadline = time.monotonic() + max_wait
        if cost > self.capacity:
            raise RateLimited(f"{self.name}: a request costing {cost:g} exceeds the budget of {self.capacity:g}")
        async with self._get_lock():
            while True:
                now = time.monotonic()
                if now < self.blocked_until:
                    raise RateLimited(f"{self.name} is cooling down")
                self._refill(now)
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                wait = (cost - self.tokens) * self.per / self.rate
                if now + wait > deadline:
                    raise RateLimited(f"{self.name} rate budget used up")
                await asyncio.sleep(wait)


class CircuitBreaker:
    """After `threshold` failures in a row, `open` stays True for `cool_s` seconds; one success closes it."""

    def __init__(self, threshold: int = 5, cool_s: float = 60.0, name: str = "upstream"):
        self.threshold, self.cool_s, self.name = threshold, cool_s, name
        self.failures = 0
        self.open_until = 0.0

    @property
    def open(self) -> bool:
        return time.monotonic() < self.open_until

    def success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.monotonic() + self.cool_s
            log.warning("%s: %d failures in a row, skipping it for %.0fs", self.name, self.failures, self.cool_s)
