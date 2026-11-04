"""Live adapters parse the providers' documented shapes (mocked HTTP — no network)."""
import json

import httpx
import pytest

from market.live import LiveMarket


def _client(routes):
    def handler(req: httpx.Request):
        for frag, body in routes.items():
            if frag in str(req.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_coingecko_markets_history_search():
    lm = LiveMarket(_client({
        "/coins/markets": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1, "current_price": 90000,
                            "market_cap": 1.8e12, "total_volume": 4e10, "price_change_percentage_24h": 1.5, "ath": 125000}],
        "/market_chart": {"prices": [[1761955200000, 89000.0], [1762041600000, 90000.0]]},
        "/coins/bitcoin?": {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "market_cap_rank": 1,
                            "market_data": {"current_price": {"usd": 90000}, "market_cap": {"usd": 1.8e12},
                                            "total_volume": {"usd": 4e10}, "price_change_percentage_24h": 1.5,
                                            "ath": {"usd": 125000}},
                            "platforms": {"": ""}, "genesis_date": "2009-01-03", "description": {"en": "Digital money."}},
    }))
    top = await lm.top_coins(1)
    assert top[0]["symbol"] == "BTC" and top[0]["price_usd"] == 90000
    px = await lm.prices(["BTC"])
    assert px["BTC"]["market_cap_usd"] == 1.8e12
    h = await lm.history("BTC", 2)
    assert h == [("2025-11-01", 89000.0), ("2025-11-02", 90000.0)]
    c = await lm.search("btc")
    assert c["name"] == "Bitcoin" and c["genesis_date"] == "2009-01-03"


async def test_fng_and_listings():
    lm = LiveMarket(_client({
        "alternative.me": {"data": [{"value": "23", "value_classification": "Extreme Fear"}]},
        "exchangeInfo": {"symbols": [{"baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
                                     {"baseAsset": "OLD", "quoteAsset": "USDT", "status": "BREAK"},
                                     {"baseAsset": "ETH", "quoteAsset": "BTC", "status": "TRADING"}]},
        "/api/v2/symbols": {"data": [{"baseCurrency": "SOL", "quoteCurrency": "USDT", "enableTrading": True}]},
    }))
    assert await lm.fear_greed() == {"value": 23, "label": "Extreme Fear"}
    assert await lm.listings("binance") == ["BTC"]
    assert await lm.listings("kucoin") == ["SOL"]


async def test_p2p_binance_parse():
    from features.p2p import _binance
    c = _client({"p2p.binance.com": {"data": [{"adv": {"price": "91.50", "minSingleTransAmount": "500",
                                                       "maxSingleTransAmount": "100000",
                                                       "tradeMethods": [{"tradeMethodName": "UPI"}]},
                                               "advertiser": {"nickName": "Trusty", "monthFinishRate": 0.991,
                                                              "monthOrderCount": 1200}}]}})
    v = await _binance(5000, c)
    assert v["best_price"] == 91.5 and v["offers"][0]["safety"] == "high" and v["offers"][0]["payment"] == ["UPI"]


def test_rss_parse():
    from features.news import parse_rss
    xml = b"""<rss><channel><item><title>Bitcoin hits new high</title><link>https://x.test/a</link>
    <description>&lt;p&gt;BTC and Ethereum rally&lt;/p&gt;</description><pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>"""
    rows = parse_rss("CoinDesk", xml)
    assert rows[0]["coins"] == ["BTC", "ETH"] and rows[0]["published_at"].year == 2026


def test_xray_classify():
    from features.xray import classify
    assert classify("BTC") == "coin"
    assert classify("Bitcoin") == "coin"
    assert classify("binance.com") == "link"
    assert classify("https://bit.ly/abc") == "link"
    assert classify("0x1234567890abcdef1234567890abcdef12345678") == "coin"
    assert classify("Sir please join this group for 5% daily profit") == "message"


def test_rate_safety_rules():
    from features.p2p import safety
    assert safety(99, 1000) == "high" and safety(96, 150) == "medium" and safety(90, 5000) == "low"
