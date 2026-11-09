"""Twelve Data client + the price-source router. Replies are copies of what the live API returned on 9 Nov 2026."""
import httpx
import pytest

from core.http import RateLimited

QUOTE_BTC = {"symbol": "BTC/USD", "name": "Bitcoin US Dollar", "exchange": "Binance", "datetime": "2026-11-09",
             "timestamp": 1794182400, "open": "74851.44", "high": "75599.22", "low": "74281.4", "close": "74389.02",
             "previous_close": "74851.44", "change": "-462.42000", "percent_change": "-0.61778371",
             "rolling_1d_change": "-1.92031", "rolling_7d_change": "-4.87340", "is_market_open": True,
             "fifty_two_week": {"low": "57800.19", "high": "107500"}}
SERIES_BTC = {"meta": {"symbol": "BTC/USD", "interval": "1day", "currency_base": "Bitcoin", "currency_quote": "US Dollar",
                       "exchange": "Binance", "type": "Digital Currency"},
              "values": [{"datetime": "2026-11-07", "open": "75844", "high": "76249.99", "low": "75571.08", "close": "75867.59"},
                         {"datetime": "2026-11-08", "open": "75867.58", "high": "76200", "low": "73510", "close": "74851.44"},
                         {"datetime": "2026-11-09", "open": "74851.44", "high": "75599.22", "low": "74281.4", "close": "74389.02"}],
              "status": "ok"}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_single_quote_parsed_and_key_sent_in_header():
    from market.twelvedata import TwelveDataMarket
    seen = {}

    def h(req):
        seen.update(path=req.url.path, auth=req.headers.get("authorization"), symbol=req.url.params.get("symbol"))
        return httpx.Response(200, json=QUOTE_BTC)
    px = await TwelveDataMarket("k123", _client(h)).prices(["btc"])
    assert seen == {"path": "/quote", "auth": "apikey k123", "symbol": "BTC/USD"}
    assert px == {"BTC": {"symbol": "BTC", "name": "Bitcoin", "price_usd": 74389.02, "change_24h": -1.92031,
                          "source": "twelvedata"}}


async def test_batch_keeps_good_items_and_remembers_unknown_symbols():
    from market import twelvedata as td
    calls = []

    def h(req):
        import json
        calls.append((req.method, req.url.path, json.loads(req.content or b"{}")))
        return httpx.Response(200, json={"code": 200, "status": "success", "data": {
            "BTC": {"status": "success", "response": QUOTE_BTC},
            "ETH": {"status": "success", "response": {**QUOTE_BTC, "symbol": "ETH/USD", "name": "Ethereum US Dollar",
                                                      "close": "3554.4", "rolling_1d_change": None, "percent_change": "2.3"}},
            "ZZZ": {"status": "error", "response": {"code": 400, "message": "**symbol** not found", "status": "error"}}}})
    m = td.TwelveDataMarket("k", _client(h))
    px = await m.prices(["BTC", "ETH", "ZZZ"])
    assert set(px) == {"BTC", "ETH"} and px["ETH"]["change_24h"] == 2.3 and px["ETH"]["name"] == "Ethereum"
    method, path, body = calls[0]
    assert method == "POST" and path == "/batch" and body["ZZZ"] == {"url": "/quote?symbol=ZZZ/USD"}
    await m.prices(["ZZZ"])                                      # remembered as unknown: no second request
    assert len(calls) == 1


async def test_history_ascending_utc_and_capped():
    from market.twelvedata import TwelveDataMarket
    seen = {}

    def h(req):
        seen.update(dict(req.url.params))
        return httpx.Response(200, json=SERIES_BTC)
    rows = await TwelveDataMarket("k", _client(h)).history("BTC", 9999)
    assert rows == [("2026-11-07", 75867.59), ("2026-11-08", 74851.44), ("2026-11-09", 74389.02)]
    assert seen["outputsize"] == "5000" and seen["order"] == "asc" and seen["interval"] == "1day" and seen["timezone"] == "UTC"


async def test_out_of_credits_in_body_cools_down_without_calling_again():
    from market.twelvedata import TwelveDataMarket
    n = {"calls": 0}

    def h(req):
        n["calls"] += 1                                          # Twelve Data can report errors with HTTP 200
        return httpx.Response(200, json={"code": 429, "message": "You have run out of API credits", "status": "error"})
    m = TwelveDataMarket("k", _client(h))
    with pytest.raises(RateLimited):
        await m.prices(["BTC"])
    with pytest.raises(RateLimited):
        await m.prices(["BTC"])
    assert n["calls"] == 1


async def test_budget_per_worker_and_oversized_batch(monkeypatch):
    from market import twelvedata as td
    monkeypatch.setenv("TWELVE_DATA_CREDITS_PER_MIN", "8")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    td.reset_state()
    assert td.BUCKET.rate == 4 and td.BUCKET.capacity == 4
    with pytest.raises(RateLimited):
        await td.BUCKET.acquire(0, cost=5)                       # 5 coins can never fit a 4-credit budget


def test_price_source_choice(monkeypatch):
    import market
    monkeypatch.setenv("MARKET_MODE", "live")
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_PRICE_SOURCE", raising=False)
    assert market.price_source() == "coingecko"
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "k")
    assert market.price_source() == "twelvedata"
    monkeypatch.setenv("MARKET_PRICE_SOURCE", "coingecko")
    assert market.price_source() == "coingecko"
    monkeypatch.setenv("MARKET_MODE", "fake")
    assert market.price_source() == "fake"


async def test_router_falls_back_to_coingecko_for_missing_coins(monkeypatch):
    import market

    class TD:
        async def prices(self, syms):
            return {"BTC": {"symbol": "BTC", "price_usd": 1.0, "source": "twelvedata"}}

        async def history(self, sym, days):
            raise RateLimited("out of credits")

    class CG:
        async def prices(self, syms):
            return {s: {"symbol": s, "price_usd": 2.0, "source": "coingecko"} for s in syms}

        async def history(self, sym, days):
            return [("2026-11-09", 2.0)]
    monkeypatch.setattr(market, "price_source", lambda: "twelvedata")
    monkeypatch.setattr(market, "td_provider", lambda: TD())
    monkeypatch.setattr(market, "provider", lambda: CG())
    market.clear_cache()
    px = await market.prices(["BTC", "PEPE"])
    assert px["BTC"]["source"] == "twelvedata" and px["PEPE"]["source"] == "coingecko"
    assert await market.history("BTC", 5) == [("2026-11-09", 2.0)]


async def test_pulse_cycle_uses_history_high_when_source_has_no_ath(monkeypatch, mdb):
    import market
    from features import verdicts

    async def prices(syms):
        return {s: {"symbol": s, "price_usd": 90.0, "change_24h": 0.0} for s in syms}

    async def history(sym, days):
        return [("2026-01-01", 120.0), ("2026-11-09", 90.0)]
    monkeypatch.setattr(market, "prices", prices)
    monkeypatch.setattr(market, "history", history)
    p = await verdicts.build_pulse(mdb)
    assert p["cycle"]["ath_usd"] == 120.0 and p["cycle"]["drawdown_from_ath_pct"] == -25.0
