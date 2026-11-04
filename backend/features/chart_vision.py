"""Chart Reader: read a price-chart screenshot with Claude vision (adapted from Bullzeye bullbear/vision.py).

The model first decides whether the image is a price chart at all; anything else is refused
(is_chart false) and the use is refunded. The image is analysed in memory and never stored.
"""
from __future__ import annotations

MAX_BYTES = 5 * 1024 * 1024
MEDIA = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp", b"GIF8": "image/gif"}


class ChartError(Exception):
    def __init__(self, code: str, msg: str, retry_after: int | None = None):
        super().__init__(msg)
        self.code, self.msg, self.retry_after = code, msg, retry_after


def sniff(data: bytes) -> str:
    """The real image type from the file's first bytes (never trust the browser's label)."""
    if len(data) > MAX_BYTES:
        raise ChartError("too_large", "The image is larger than 5 MB. Try a smaller screenshot.")
    for magic, media in MEDIA.items():
        if data.startswith(magic) and (media != "image/webp" or data[8:12] == b"WEBP"):
            return media
    raise ChartError("not_image", "Upload a PNG, JPG, WebP or GIF screenshot of a price chart.")


PROMPT = """You read crypto price charts for Indian beginners. Look at the attached image.

First decide whether it is a price chart (candles, bars or a price line, with or without indicators) for a coin, token,
stock or index. If it is anything else, set is_chart to false and leave the other fields empty.

If it is a chart{symbol_hint}: describe only what is visible — the coin if shown, the timeframe if you can tell, the
trend (up, down or sideways), support and resistance levels read off the price axis (as short strings like "$58,000"),
what RSI shows if an RSI panel is visible (else say it isn't shown), recognisable patterns in plain words, a 2–3
sentence summary, and what to watch next. This is education, not advice: never tell the user to buy or sell and
never give price targets as promises. If something is too blurry to read, leave it out and say so in the summary.

Return {{"is_chart": bool, "symbol": str, "timeframe": str, "trend": "up|down|sideways", "summary": str,
"support": [str], "resistance": [str], "rsi_read": str, "patterns": [str], "what_to_watch": [str]}}"""


def fake_read(symbol: str) -> dict:
    return {"is_chart": True, "symbol": symbol or "BTC", "timeframe": "Daily", "trend": "up",
            "summary": "Sample reading (QA mode): price is making higher highs and higher lows and sits above its "
                       "moving average, so buyers have the edge for now.",
            "support": ["$86,500", "$82,000"], "resistance": ["$95,000", "$99,800"],
            "rsi_read": "RSI around 61 — positive momentum, not overheated.",
            "patterns": ["Higher highs and higher lows (uptrend)", "Recent pullback held above support"],
            "what_to_watch": ["A daily close above $95,000", "A close below $86,500 would weaken the trend"]}


async def analyze_chart(data: bytes, symbol: str = "") -> dict:
    import llm
    media = sniff(data)
    hint = f" (the user says it is {symbol})" if symbol else ""
    try:
        out = await llm.complete_json(task="chart", system="You are a careful chart reader. Reply in JSON only.",
                                      prompt=PROMPT.format(symbol_hint=hint), fake=lambda: fake_read(symbol),
                                      model="vision", max_tokens=1500, images=[(media, data)])
    except llm.AIBusy as e:
        raise ChartError("unavailable", "Lots of people are reading charts right now. Try again in a moment.",
                         retry_after=e.retry_after) from e
    except llm.LLMError as e:
        raise ChartError("unavailable", "The chart reader didn't respond. Try again in a minute.", retry_after=15) from e
    if out.get("trend") not in ("up", "down", "sideways"):
        out["trend"] = "sideways"
    return out
