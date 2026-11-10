"""Claude calls behind one helper, with a deterministic fake for tests and QA.

    await complete_json(task="xray_headline", system=..., prompt=..., fake=lambda: {...})

Every caller passes `fake`: the shape the feature expects, built from the same inputs,
so QA mode and tests run with no key and no network. Live mode asks for JSON only and
parses the first JSON object in the reply.

Models (env): LLM_MODEL_FAST (default claude-haiku-5-5), LLM_MODEL_STRONG
(claude-sonnet-5-5), LLM_MODEL_VISION (claude-opus-5-5).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Callable, Optional

from core.vendors import vendor_mode

log = logging.getLogger("llm")

MODELS = {
    "fast": lambda: os.environ.get("LLM_MODEL_FAST", "claude-haiku-5-5"),
    "strong": lambda: os.environ.get("LLM_MODEL_STRONG", "claude-sonnet-5-5"),
    "vision": lambda: os.environ.get("LLM_MODEL_VISION", "claude-opus-5-5"),
}


class LLMError(RuntimeError):
    pass


class AIBusy(LLMError):
    """The pool for this model class stayed full for the whole queue wait. `retry_after` (seconds) is a hint for
    the client; callers turn it into 503 + Retry-After and refund the member's use."""

    def __init__(self, msg: str, retry_after: int):
        super().__init__(msg)
        self.retry_after = retry_after


# ---- Bulkheads (load test, 3 Nov) -----------------------------------------------------------------------------
# A webinar puts hundreds of people on X-Ray, Ask and Chart Reader in the same minute. Each model class gets its
# own pool so a burst of slow vision calls (Chart Reader) can't starve the fast ones (X-Ray, Ask), and the other
# way round. In the hard-burst test one shared pool of 32 with a 15 s wait turned away 116 of 500 chart reads.
#
#   LLM_MAX_CONCURRENCY_<CLASS>   calls in flight per worker   (default: LLM_MAX_CONCURRENCY, 32)
#   LLM_QUEUE_WAIT_S_<CLASS>      how long a call may wait     (fast/strong 15 s; vision 45 s: the member is already
#                                                               watching an upload spinner, and a refund-and-retry
#                                                               costs them more time than waiting)
# Size the totals (× WEB_CONCURRENCY workers) against the Anthropic account's rate limits.
_QUEUE_DEFAULTS = {"fast": 15.0, "strong": 15.0, "vision": 45.0}


def _env_num(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, "") or default)
        return v if v > 0 else default
    except ValueError:
        return default


class _Pool:
    def __init__(self, name: str):
        self.name = name
        self.size = 0
        self.sem: Optional[asyncio.Semaphore] = None
        self.in_flight = 0
        self.waiting = 0
        self.rejected = 0

    def _configure(self) -> None:
        base = _env_num("LLM_MAX_CONCURRENCY", 32)
        n = int(_env_num(f"LLM_MAX_CONCURRENCY_{self.name.upper()}", base))
        if self.sem is None or n != self.size:
            self.sem, self.size = asyncio.Semaphore(n), n

    @property
    def wait_s(self) -> float:
        legacy = os.environ.get("LLM_QUEUE_WAIT_S")
        default = _env_num("LLM_QUEUE_WAIT_S", 15) if (legacy and self.name != "vision") else _QUEUE_DEFAULTS[self.name]
        return _env_num(f"LLM_QUEUE_WAIT_S_{self.name.upper()}", default)

    async def run(self, coro_fn, task: str):
        self._configure()
        sem = self.sem
        self.waiting += 1
        try:
            await asyncio.wait_for(sem.acquire(), timeout=self.wait_s)
        except (asyncio.TimeoutError, TimeoutError):
            self.rejected += 1
            log.warning("LLM task %s: %s pool full for %.0fs (size %d), giving up", task, self.name, self.wait_s, self.size)
            raise AIBusy("AI is busy right now.", retry_after=10 if self.name != "vision" else 20)
        finally:
            self.waiting -= 1
        self.in_flight += 1
        try:
            return await asyncio.wait_for(coro_fn(), timeout=_env_num("LLM_TIMEOUT_S", 25 if self.name != "vision" else 45))
        except (asyncio.TimeoutError, TimeoutError):
            log.warning("LLM task %s timed out", task)
            raise LLMError("AI took too long.")
        finally:
            self.in_flight -= 1
            sem.release()

    def stats(self) -> dict:
        self._configure()
        return {"pool": self.name, "size": self.size, "in_flight": self.in_flight, "waiting": self.waiting,
                "queue_wait_s": self.wait_s, "rejected": self.rejected}


_POOLS: dict[str, _Pool] = {}


def _pool(model: str) -> _Pool:
    key = model if model in _QUEUE_DEFAULTS else "fast"
    if key not in _POOLS:
        _POOLS[key] = _Pool(key)
    return _POOLS[key]


def pool_stats() -> list[dict]:
    """This worker's AI pools, for Admin › Vendors during a webinar."""
    return [_pool(m).stats() for m in _QUEUE_DEFAULTS]


def reset_pools() -> None:
    _POOLS.clear()


async def _guarded(coro_fn, task: str, model: str = "fast"):
    return await _pool(model).run(coro_fn, task)


def _effort() -> str:
    """Thinking depth for these short, structured tasks. The current models think before answering by default and
    that thinking counts toward max_tokens; at the default effort a 1,200-token JSON reply could be cut off and the
    feature silently fell back to its rule-based answer (QA 10 Nov: every verdict used the backup wording).
    LLM_EFFORT=low|medium|high|xhigh|max; empty sends nothing (the model's default)."""
    v = (os.environ.get("LLM_EFFORT") or "low").strip().lower()
    return v if v in ("low", "medium", "high", "xhigh", "max") else ""


async def _call_text(*, model: str, max_tokens: int, system: str, content) -> str:
    extra = {"output_config": {"effort": _effort()}} if _effort() else None
    # output_config goes through extra_body: the pinned SDK (anthropic 0.51) predates the named parameter.
    resp = await _client().messages.create(model=MODELS[model](), max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": content}], extra_body=extra)
    stop = getattr(resp, "stop_reason", None)
    if stop == "max_tokens":
        raise LLMError(f"reply cut off at max_tokens={max_tokens}")
    if stop == "refusal":
        raise LLMError("the model declined this request")
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text" and getattr(b, "text", None))


def mode() -> str:
    return vendor_mode("anthropic")


# Per-worker record of how AI calls went, for Admin › Vendors: a feature that keeps falling back to its rule-based
# answer is visible there with the reason (bad key, model refused, reply cut off, busy), instead of only in logs.
_STATS: dict[str, dict] = {}


def _record(task: str, ok: bool, error: Optional[str] = None) -> None:
    s = _STATS.setdefault(task, {"task": task, "ok": 0, "failed": 0, "last_error": None, "last_error_at": None})
    if ok:
        s["ok"] += 1
    else:
        import time
        s["failed"] += 1
        s["last_error"], s["last_error_at"] = (error or "")[:200], time.time()


def call_stats() -> list[dict]:
    from datetime import datetime, timezone
    out = []
    for s in sorted(_STATS.values(), key=lambda x: x["task"]):
        at = s["last_error_at"]
        out.append({**s, "last_error_at": datetime.fromtimestamp(at, tz=timezone.utc).isoformat() if at else None})
    return out


_CLIENT: dict = {"c": None}


def _client():
    """One shared client per worker (connection pooling) instead of a new one per call."""
    if _CLIENT["c"] is None:
        import anthropic
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip("\"'").strip()
        _CLIENT["c"] = anthropic.AsyncAnthropic(api_key=key, max_retries=1)
    return _CLIENT["c"]


def _parse(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise LLMError("no JSON in reply")
    return json.loads(text[start:end + 1])


async def complete_json(*, task: str, system: str, prompt: str, fake: Callable[[], Any], model: str = "fast",
                        max_tokens: int = 4000, images: Optional[list[tuple[str, bytes]]] = None,
                        fallback_on_error: bool = False) -> dict:
    """images: [(media_type, bytes)] for vision tasks. fallback_on_error: return fake() instead of raising."""
    try:
        out = await _complete_json(task=task, system=system, prompt=prompt, fake=fake, model=model,
                                   max_tokens=max_tokens, images=images)
    except LLMError as e:
        if mode() != "fake":
            _record(task, False, str(e))
        if fallback_on_error:
            return fake()
        raise
    if mode() != "fake":
        _record(task, True)
    return out


async def _fake_with_latency(fake: Callable[[], Any], task: str, model: str = "fast"):
    """LLM_FAKE_LATENCY_MS (load tests only): make fake answers take as long as real ones and go through the
    same concurrency guard, so a load test shows what the real Anthropic latency does to queues."""
    ms = int(os.environ.get("LLM_FAKE_LATENCY_MS", "0") or 0)
    if ms <= 0:
        return fake()

    async def slow():
        await asyncio.sleep(ms / 1000)
        return fake()
    return await _guarded(slow, task, model)


async def _complete_json(*, task, system, prompt, fake, model, max_tokens, images) -> dict:
    m = mode()
    if m == "fake":
        return await _fake_with_latency(fake, task, model)
    if m == "off":
        raise LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    content: list = []
    for media, data in images or []:
        import base64
        content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                    "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": prompt + "\n\nReply with one JSON object only."})
    try:
        text = await _guarded(lambda: _call_text(model=model, max_tokens=max_tokens, system=system, content=content), task, model)
        return _parse(text)
    except LLMError as e:
        log.warning("LLM task %s: %s", task, e)
        raise
    except Exception as e:  # noqa: BLE001 — e.g. AuthenticationError (bad key), NotFoundError (model), JSON errors
        log.warning("LLM task %s failed: %s: %s", task, type(e).__name__, str(e)[:300])
        raise LLMError(f"{type(e).__name__}: {str(e)[:160]}") from e


async def complete_text(*, task: str, system: str, prompt: str, fake: Callable[[], str], model: str = "strong",
                        max_tokens: int = 4000) -> str:
    m = mode()
    if m == "fake":
        return await _fake_with_latency(fake, task, model)
    if m == "off":
        raise LLMError("AI is not configured (ANTHROPIC_API_KEY).")
    try:
        text = await _guarded(lambda: _call_text(model=model, max_tokens=max_tokens, system=system, content=prompt), task, model)
        return text.strip()
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("LLM task %s failed: %s", task, e)
        raise LLMError(f"AI call failed: {type(e).__name__}") from e
