"""Verdict text for beginners (QA 10 Nov content review): no indicator jargon, prices in dollars, no privacy coins."""
import re

import pytest

JARGON = re.compile(r"\b(RSI|EMA|SMA|MACD)\d*\b", re.I)
IND = {"price": 553.8, "rsi14": 39.9, "ema20": 594.9, "ema50": 570.5, "chg7": -3.1, "chg30": -8.2, "vol30_ann": 62.0,
       "drawdown90": -14.0, "daily_vol": 0.03, "drift": 0.0}


@pytest.mark.parametrize("text,want", [
    ("Price is below both the EMA20 (594.9) and EMA50 (570.5).", "Price is below both the 20-day average and the 50-day average."),
    ("RSI is 39.9, so buyers are tired.", "Weak momentum, so buyers are tired."),
    ("With an RSI of 75.2 the move looks stretched.", "With overheated momentum the move looks stretched."),
    ("Price of 553.8 is under the 20-day EMA.", "Price of $553.8 is under the 20-day average."),
    ("Price of $73,800 is near the high.", "Price of $73,800 is near the high."),
    ("Price fell 5% this week.", "Price fell 5% this week."),
])
def test_plain_words(text, want):
    from features.verdicts import plain_words
    assert plain_words(text) == want


def test_rule_text_and_prompt_data_have_no_jargon():
    from features.verdicts import PLAIN_RULES, plain_facts, rule_verdict
    _, _, bull, bear = rule_verdict(IND, rank=8)
    for s in bull + bear:
        assert not JARGON.search(s.point) and not JARGON.search(s.evidence), s
    facts = plain_facts(IND)
    assert not JARGON.search(facts) and "594.9" not in facts and "$553.80" in facts
    assert "RSI" in PLAIN_RULES          # the model is told not to use the names it might know


async def test_ai_committee_reply_is_cleaned(monkeypatch):
    import llm
    from features import verdicts

    async def fake_llm(**kw):
        assert "EMA" not in kw["prompt"] and "RSI" not in kw["prompt"] and "$553.80" in kw["prompt"]
        return {"bull": ["Price of 553.8 is above the EMA50 (570.5)."], "bear": ["RSI is 39.9."], "verdict": "Neutral",
                "confidence": 55, "summary": "EMA20 over EMA50.", "chair": "Neutral; RSI 39.9 is soft."}
    monkeypatch.setattr(llm, "complete_json", fake_llm)
    monkeypatch.setattr(llm, "mode", lambda: "live")
    out = await verdicts.committee("XYZ", "Xyz", IND)
    text = " ".join(out["bull"] + out["bear"] + [out["summary"], out["chair"]])
    assert not JARGON.search(text) and "570.5" not in text and "$553.8" in text and out["made_by"] == "ai"


def test_stored_verdict_text_is_cleaned_on_read():
    from features.verdicts import shape
    v = {"symbol": "XYZ", "verdict": "Bearish", "confidence": 60, "date": "2026-11-10", "summary": "Below the EMA20 (594.9).",
         "bull": ["RSI 28: oversold."], "bear": ["Price of 553.8."], "chair": "RSI is 39.9."}
    out = shape(v, details=True)
    assert out["bull"] == ["Very weak momentum: oversold."] and out["bear"] == ["Price of $553.8."]
    assert out["summary"] == "Below the 20-day average." and out["chair"] == "Weak momentum."


def test_privacy_coins_are_not_plain_coins():
    from market import is_plain_coin
    assert not is_plain_coin({"symbol": "XMR"}) and not is_plain_coin({"symbol": "zec"})
    assert is_plain_coin({"symbol": "BTC"})
