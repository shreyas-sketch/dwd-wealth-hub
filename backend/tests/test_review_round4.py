"""10 Nov review, round 4: giveaway scams are likely scams; a harmless unknown site is "unknown", not "risky"."""


async def test_send_crypto_to_double_it_is_likely_scam():
    from features.xray import run_xray
    for msg in ("send 0.1 BTC to double it, limited offer",
                "Deposit 500 USDT and we guarantee fixed daily profit",
                "Transfer ETH now, we double your coins in 24 hours"):
        assert (await run_xray(msg))["label"] == "likely_scam", msg
    assert (await run_xray("Hi, how are you doing today friend"))["label"] == "safe"


async def test_unknown_harmless_site_is_unknown_not_risky():
    from features.xray import run_xray
    out = await run_xray("sweetcrumbs-bakery.com")
    assert out["label"] == "unknown" and out["score"] == 30 and "don't know this site" in out["headline"]
    assert (await run_xray("secure-wallet-restore.com"))["label"] == "risky"       # bait word: still risky
    assert (await run_xray("binance.com"))["label"] == "safe"
