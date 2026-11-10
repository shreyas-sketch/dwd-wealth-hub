"""11 Nov: the automatic Airdrop Finder (features/airdrop_auto.py) and the "top5" basket refresh. No network: the
research call, CoinGecko search, X-Ray and exchange listings are all replaced."""
from datetime import date, timedelta

import pytest

import market
import state
from features import airdrop_auto as aa
from features import baskets
from growth.clock import utcnow
from jobs.registry import Ctx

TODAY = date(2026, 11, 11)
SEEN = ["https://www.coindesk.com/aster-airdrop", "https://theblock.co/post/aster-s3"]


def cand(**kw):
    c = {"name": "Aster Season 3", "coin": "aster", "chain": "BNB Chain", "kind": "claim", "reward": "ASTER tokens",
         "deadline": (TODAY + timedelta(days=20)).isoformat(), "deadline_note": "12:00 UTC",
         "official_url": "https://www.asterdex.com/en/airdrop", "eligibility": "Traded on Aster in Season 3.",
         "steps": ["Connect the wallet you traded with.", "Open https://evil.example to claim", "Claim."],
         "sources": list(SEEN)}
    c.update(kw)
    return c


@pytest.fixture
def fakes(mdb, monkeypatch):
    state.set_db(mdb)
    info = {"ASTER": {"symbol": "ASTER", "homepage": "https://asterdex.com", "categories": ["Perpetuals"]}}
    xray = {"label": "looks_ok", "score": 20}

    async def search(q):
        return info.get((q or "").upper())

    async def run_xray(q):
        return dict(xray)
    import features.xray as xr
    monkeypatch.setattr(market, "search", search)
    monkeypatch.setattr(xr, "run_xray", run_xray)
    return {"info": info, "xray": xray}


async def test_check_passes_and_writes_the_safety_steps(fakes):
    f, why = await aa.check(cand(), SEEN, TODAY)
    assert why == "" and f["coin"] == "ASTER" and f["status"] == "live"
    steps = [s["text"] for s in f["steps"]]
    assert steps[0].startswith("Type asterdex.com into your browser yourself")
    assert steps[-1].startswith("Never pay a fee")
    assert not any("evil.example" in s for s in steps)              # the model's step with a link is dropped
    assert f["description"].startswith("Only if you already qualified.")
    assert len(f["sources"]) == 2


@pytest.mark.parametrize("change, reason", [
    ({"official_url": "https://asterdex-claim.com/airdrop"}, "official website"),
    ({"official_url": "http://www.asterdex.com/airdrop"}, "https"),
    ({"official_url": "https://bit.ly/abc"}, "shortener"),
    ({"deadline": (TODAY - timedelta(days=1)).isoformat()}, "deadline"),
    ({"deadline": (TODAY + timedelta(days=200)).isoformat()}, "deadline"),
    ({"deadline": "soon"}, "deadline"),
    ({"sources": ["https://www.coindesk.com/aster-airdrop"]}, "2 confirmed sources"),
    ({"sources": ["https://www.coindesk.com/aster-airdrop", "https://made-up.example/x"]}, "2 confirmed sources"),
    ({"sources": ["https://www.coindesk.com/a", "https://coindesk.com/b"]}, "2 confirmed sources"),
    ({"coin": "NOPE"}, "CoinGecko"),
    ({"name": "Aster prediction market drop"}, "excluded"),
    ({"coin": "XMR"}, "excluded"),
    ({"official_url": ""}, "missing"),
])
async def test_check_drops_anything_that_fails(fakes, change, reason):
    seen = SEEN + ["https://www.coindesk.com/a", "https://coindesk.com/b"]
    f, why = await aa.check(cand(**change), seen, TODAY)
    assert f is None and reason in why


async def test_check_drops_scam_coin_and_excluded_category(fakes):
    fakes["xray"]["label"] = "likely_scam"
    assert (await aa.check(cand(), SEEN, TODAY))[0] is None
    fakes["xray"]["label"] = "looks_ok"
    fakes["info"]["ASTER"]["categories"] = ["Prediction Markets"]
    assert "excluded" in (await aa.check(cand(), SEEN, TODAY))[1]


def test_site_handles_country_domains():
    assert aa.site("https://app.foo.co.uk/x") == "foo.co.uk"
    assert aa.site("https://www.asterdex.com/en") == "asterdex.com"
    assert aa.site("asterdex.com") == "asterdex.com"


async def _job(mdb, monkeypatch, cands, now=None):
    import llm
    import plans

    async def research(**kw):
        return {"airdrops": cands}, list(SEEN)

    async def users_with(d, feature, now=None):
        return ["u1"]
    monkeypatch.setattr(llm, "research_json", research)
    monkeypatch.setattr(plans, "users_with", users_with)
    return await aa.job_run(Ctx(mdb, now or utcnow()))


async def test_job_publishes_verified_listing_and_alerts(mdb, fakes, monkeypatch):
    bad = cand(name="Fake Drop", official_url="https://asterdex-claim.com/x")
    r = await _job(mdb, monkeypatch, [cand(), bad])
    assert r["status"] == "ok" and r["added"] == ["Aster Season 3"]
    assert r["dropped"][0]["name"] == "Fake Drop"
    a = await mdb.airdrops.find_one({"name": "Aster Season 3"})
    assert a["source"] == "auto" and a["link_verified"] is True and a["hidden"] is False
    assert await mdb.airdrops.count_documents({}) == 1                     # the failing one is never stored
    assert await mdb.inbox.count_documents({"user_id": "u1"}) == 1
    # Run again: same listing is updated, not duplicated, and nobody is alerted twice.
    r = await _job(mdb, monkeypatch, [cand(name="aster season 3")])
    assert r["added"] == [] and r["updated"] == 1
    assert await mdb.airdrops.count_documents({}) == 1
    assert await mdb.inbox.count_documents({"user_id": "u1"}) == 1


async def test_job_leaves_team_listings_alone_and_respects_cap(mdb, fakes, monkeypatch):
    await mdb.airdrops.insert_one({"_id": "team1", "name": "Aster Season 3", "coin": "ASTER", "source": "admin",
                                   "status": "live", "steps": []})
    monkeypatch.setenv("AIRDROP_AUTO_MAX_NEW", "1")
    r = await _job(mdb, monkeypatch, [cand(), cand(name="Aster Bonus"), cand(name="Aster Extra")])
    assert {"name": "Aster Season 3", "why": "the team already lists it"} in r["dropped"]
    assert r["added"] == ["Aster Bonus"]
    assert {"name": "Aster Extra", "why": "daily limit reached"} in r["dropped"]
    assert (await mdb.airdrops.find_one({"_id": "team1"}))["source"] == "admin"


async def test_job_off_flag_and_failed_research(mdb, fakes, monkeypatch):
    import llm
    from core import flags
    flags._cache["values"] = {"AIRDROP_AUTO": False}
    assert (await aa.job_run(Ctx(mdb, utcnow())))["status"] == "off"
    flags._cache["values"] = {}

    async def boom(**kw):
        raise llm.LLMError("no key")
    monkeypatch.setattr(llm, "research_json", boom)
    assert (await aa.job_run(Ctx(mdb, utcnow())))["status"] == "research_failed"


async def test_upkeep_ends_hides_and_pulls(mdb, fakes):
    now = utcnow()
    old = now - timedelta(days=40)
    await mdb.airdrops.insert_many([
        {"_id": "past", "name": "Past", "coin": "ASTER", "link": "https://asterdex.com", "source": "auto",
         "status": "live", "deadline": (TODAY - timedelta(days=1)).isoformat()},
        {"_id": "stale", "name": "Stale", "coin": "ASTER", "source": "auto", "status": "ended", "updated_at": old},
        {"_id": "moved", "name": "Moved", "coin": "ASTER", "link": "https://aster-new.com/claim", "source": "auto",
         "status": "live", "deadline": (TODAY + timedelta(days=5)).isoformat()},
        {"_id": "fine", "name": "Fine", "coin": "ASTER", "link": "https://www.asterdex.com/x", "source": "auto",
         "status": "live", "deadline": (TODAY + timedelta(days=5)).isoformat()},
        {"_id": "team", "name": "Team", "coin": "ASTER", "link": "https://elsewhere.com", "source": "admin",
         "status": "live", "deadline": (TODAY + timedelta(days=5)).isoformat()}])
    await mdb.airdrop_progress.insert_one({"_id": "u9:moved", "user_id": "u9", "airdrop_id": "moved", "done_steps": []})
    r = await aa._upkeep(mdb, TODAY, now)
    assert r == {"ended": 1, "hidden": 1, "pulled": 1}
    assert (await mdb.airdrops.find_one({"_id": "past"}))["status"] == "ended"
    assert (await mdb.airdrops.find_one({"_id": "stale"}))["hidden"] is True
    moved = await mdb.airdrops.find_one({"_id": "moved"})
    assert moved["hidden"] is True and "official website" in moved["pulled_reason"]
    assert await mdb.inbox.count_documents({"user_id": "u9"}) == 1
    assert (await mdb.airdrops.find_one({"_id": "fine"})).get("checked_at")
    assert "hidden" not in await mdb.airdrops.find_one({"_id": "team"})       # team listings are never touched


def test_hidden_listing_not_shown_and_fields_public(client, mdb):
    from conftest import qa_login, run
    qa_login(client, plan="lite")
    run(mdb.airdrops.insert_many([
        {"_id": "a1", "name": "Shown", "status": "live", "steps": [], "source": "auto", "link_verified": True},
        {"_id": "a2", "name": "Pulled", "status": "ended", "steps": [], "source": "auto", "hidden": True}]))
    items = client.get("/api/airdrops").json()["items"]
    assert [i["name"] for i in items] == ["Shown"]
    assert items[0]["link_verified"] is True and items[0]["source"] == "auto"


async def test_admin_save_takes_ownership(mdb, fakes):
    from features import airdrops
    await mdb.airdrops.insert_one({"_id": "x1", "name": "Aster", "coin": "ASTER", "source": "auto",
                                   "link_verified": True, "status": "live", "steps": []})
    await airdrops.save(airdrops.AirdropIn(name="Aster", coin="ASTER", link="https://asterdex.com"), "x1")
    a = await mdb.airdrops.find_one({"_id": "x1"})
    assert a["source"] == "admin" and a["link_verified"] is False


# ------------------------------------------------------------------------------------------------ baskets ----
def coin(sym, cats=None):
    return {"symbol": sym, "categories": cats or []}


@pytest.fixture
def mkt(mdb, monkeypatch):
    state.set_db(mdb)
    data = {"rows": [coin(s) for s in ("BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "TRX", "ADA", "LINK")],
            "listed": ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "TRX", "ADA", "LINK"]}

    async def listings(venue):
        return data["listed"]

    async def top_coins(n=10, exclude_stables=True, tradable=True):
        return data["rows"][:n]
    monkeypatch.setattr(market, "listings", listings)
    monkeypatch.setattr(market, "top_coins", top_coins)
    return data


async def test_top5_mix_skips_memes_and_keeps_nearby_coins(mkt):
    mix = await baskets.top5_mix([])
    assert [c["symbol"] for c in mix] == ["BTC", "ETH", "XRP", "BNB", "SOL"]
    assert [c["weight_pct"] for c in mix] == [35, 20, 15, 15, 15]
    # SOL has slipped to 7th (DOGE is 6th but a meme): a current holding in the top 7 stays.
    mkt["rows"] = [coin(s) for s in ("BTC", "ETH", "XRP", "BNB", "TRX", "ADA", "SOL", "LINK")]
    mix = await baskets.top5_mix(["BTC", "ETH", "XRP", "BNB", "SOL"])
    assert [c["symbol"] for c in mix] == ["BTC", "ETH", "XRP", "BNB", "SOL"]
    mkt["rows"] = [coin(s) for s in ("BTC", "ETH", "XRP", "BNB", "TRX", "ADA", "LINK", "SOL")]   # now 8th: out
    assert "SOL" not in [c["symbol"] for c in await baskets.top5_mix(["BTC", "ETH", "XRP", "BNB", "SOL"])]
    mkt["rows"] = [coin("BTC"), coin("ETH"), coin("WIF", ["Meme"])]
    assert await baskets.top5_mix([]) is None                                   # too few: never guess


async def test_basket_auto_refresh_changes_and_alerts(mdb, mkt):
    await mdb.baskets.insert_one({"_id": "b5", "name": "Big Five", "auto_rule": "top5", "active": True,
                                  "coins": [{"symbol": s, "weight_pct": w} for s, w in
                                            zip(("BTC", "ETH", "XRP", "BNB", "LINK"), (35, 20, 15, 15, 15))]})
    await mdb.baskets.insert_one({"_id": "b6", "name": "Hand made", "active": True,
                                  "coins": [{"symbol": "BTC", "weight_pct": 100}]})
    await mdb.basket_holders.insert_one({"_id": "h1", "basket_id": "b5", "user_id": "u7"})
    first_monday = utcnow().replace(day=3, hour=4)
    r = await baskets.job_auto_refresh(Ctx(mdb, first_monday))
    assert r["baskets"] == [{"basket": "Big Five", "status": "changed", "coins": ["BTC", "ETH", "XRP", "BNB", "SOL"]}]
    b = await mdb.baskets.find_one({"_id": "b5"})
    assert b["auto_rule"] == "top5" and "Removed LINK" in b["change_note"]
    assert await mdb.inbox.count_documents({"user_id": "u7", "kind": "basket_change"}) == 1
    assert (await mdb.baskets.find_one({"_id": "b6"}))["coins"] == [{"symbol": "BTC", "weight_pct": 100}]
    r = await baskets.job_auto_refresh(Ctx(mdb, first_monday))
    assert r["baskets"][0]["status"] == "unchanged"
    # Later in the month the weekly job does nothing, unless an admin presses "Run now".
    mid = utcnow().replace(day=17, hour=4)
    assert (await baskets.job_auto_refresh(Ctx(mdb, mid)))["status"] == "not_this_week"
    assert (await baskets.job_auto_refresh(Ctx(mdb, mid, manual=True)))["status"] == "ok"


async def test_admin_basket_save_keeps_auto_rule(mdb, mkt):
    await mdb.baskets.insert_one({"_id": "b5", "name": "Big Five", "auto_rule": "top5", "active": True,
                                  "coins": [{"symbol": "BTC", "weight_pct": 100}]})
    await baskets.save(baskets.BasketIn(name="Big Five", coins=[baskets.CoinW(symbol="BTC", weight_pct=100)]), "b5")
    assert (await mdb.baskets.find_one({"_id": "b5"}))["auto_rule"] == "top5"
    await baskets.save(baskets.BasketIn(name="Big Five", coins=[baskets.CoinW(symbol="BTC", weight_pct=100)],
                                        auto_rule=None), "b5")
    assert (await mdb.baskets.find_one({"_id": "b5"}))["auto_rule"] is None    # explicitly turned off


def test_min_inr_covers_the_smallest_weight():
    assert baskets.min_inr([{"symbol": "BTC", "weight_pct": 60}, {"symbol": "ETH", "weight_pct": 40}]) == 2500
    assert baskets.min_inr([{"symbol": "BTC", "weight_pct": 50}, {"symbol": "ETH", "weight_pct": 50}]) == 2000
    assert baskets.min_inr([{"symbol": s, "weight_pct": w} for s, w in
                            zip("ABCDE", (35, 20, 15, 15, 15))]) == 6667
    assert baskets.min_inr([]) == 0
