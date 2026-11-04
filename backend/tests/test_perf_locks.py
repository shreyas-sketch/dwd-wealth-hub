"""Multi-worker safety and the perf helpers added for the 500-user load test."""
import asyncio

from growth.clock import utcnow


def run(coro):
    return asyncio.run(coro)


def test_lease_lock_one_holder(mdb):
    from jobs.registry import claim_lock, release_lock

    async def go():
        now = utcnow()
        a = await claim_lock(mdb, "job_x", now, owner="w1")
        b = await claim_lock(mdb, "job_x", now, owner="w2")          # held by w1 → refused
        await release_lock(mdb, "job_x", owner="w2")                 # not the holder: no effect
        c = await claim_lock(mdb, "job_x", now, owner="w2")
        await release_lock(mdb, "job_x", owner="w1")
        d = await claim_lock(mdb, "job_x", now, owner="w2")          # free again
        return a, b, c, d
    assert run(go()) == (True, False, False, True)


def test_two_workers_tick_runs_each_job_once(mdb, monkeypatch):
    """Two schedulers ticking at the same moment (two uvicorn workers) must not run a job twice."""
    from jobs import registry
    calls = []

    async def fake_job(ctx):
        calls.append(ctx.now)
        await asyncio.sleep(0.01)          # let the other worker interleave
        return {"ok": 1}

    monkeypatch.setattr(registry, "JOBS", {"only_job": ("Test", ("every", 60), "x:y")})
    monkeypatch.setattr(registry, "_fn", lambda path: fake_job)

    async def go():
        now = utcnow()
        await asyncio.gather(registry.tick(mdb, now), registry.tick(mdb, now), registry.tick(mdb, now))
        n_runs = await mdb.job_runs.count_documents({"name": "only_job"})
        await registry.tick(mdb, now)      # same slot: already done, not due
        return n_runs, await mdb.job_runs.count_documents({"name": "only_job"})
    assert run(go()) == (1, 1)
    assert len(calls) == 1


def test_market_cache_single_flight(monkeypatch):
    """500 requests hitting a cold cache make ONE upstream call (CoinGecko free tier is ~30 calls/min)."""
    import market
    market.clear_cache()
    n = {"calls": 0}

    async def slow():
        n["calls"] += 1
        await asyncio.sleep(0.05)
        return {"v": 1}

    async def go():
        return await asyncio.gather(*[market._cached("k", 60, slow) for _ in range(500)])
    out = run(go())
    assert n["calls"] == 1 and all(o == {"v": 1} for o in out)


def test_llm_concurrency_limit_and_fallback(monkeypatch):
    """Live LLM calls go through a semaphore and fall back to the rule-based answer on timeout/overload."""
    import llm
    monkeypatch.setattr(llm, "mode", lambda: "live")
    state = {"active": 0, "peak": 0}

    async def fake_call(**kw):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return '{"a": 1}'
    monkeypatch.setattr(llm, "_call_text", fake_call)
    monkeypatch.setattr(llm, "_SEM", {"sem": None, "n": None})
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "4")

    async def go():
        return await asyncio.gather(*[llm.complete_json(task="t", system="s", prompt="p", fake=lambda: {"a": 0},
                                                        fallback_on_error=True) for _ in range(20)])
    out = run(go())
    assert state["peak"] <= 4 and all(o == {"a": 1} for o in out)

    async def boom(**kw):
        raise TimeoutError("slow")
    monkeypatch.setattr(llm, "_call_text", boom)

    async def go2():
        return await llm.complete_json(task="t", system="s", prompt="p", fake=lambda: {"a": 0}, fallback_on_error=True)
    assert run(go2()) == {"a": 0}
