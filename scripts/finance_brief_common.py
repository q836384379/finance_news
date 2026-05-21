from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

TIMEOUT_SECONDS = 20
USER_AGENT = "finance-news-action/2.0"
ASIA_SHANGHAI = dt.timezone(dt.timedelta(hours=8))

MARKET_SYMBOLS = [
    ("SPY", "标普500ETF"),
    ("QQQ", "纳指100ETF"),
    ("DIA", "道指ETF"),
    ("TLT", "美债ETF"),
    ("USO", "原油ETF"),
    ("BTC-USD", "比特币"),
    ("000001.SS", "上证综指"),
    ("399001.SZ", "深证成指"),
    ("^HSI", "恒生指数"),
    ("^HSTECH", "恒生科技指数"),
]

HEADLINE_FEEDS = [
    "https://finance.yahoo.com/news/rssindex",
    "https://news.google.com/rss/search?q=when:1d+finance+market&hl=en-US&gl=US&ceid=US:en",
]

TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


def fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_market_snapshot(symbol: str, label: str) -> dict[str, float | str]:
    query = urlencode(
        {
            "range": "5d",
            "interval": "1d",
            "includePrePost": "false",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    payload = fetch_json(url)
    result = payload["chart"]["result"][0]
    meta = result.get("meta", {})
    quote = result["indicators"]["quote"][0]
    closes = [value for value in quote.get("close", []) if value is not None]

    current = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose")

    if current is None and closes:
        current = closes[-1]
    if (previous is None or previous == 0) and len(closes) >= 2:
        previous = closes[-2]

    if current is None or previous in (None, 0):
        raise RuntimeError(f"Missing usable price data for {symbol}")

    change_pct = ((float(current) - float(previous)) / float(previous)) * 100
    return {
        "symbol": symbol,
        "label": label,
        "price": round(float(current), 2),
        "change_pct": round(change_pct, 2),
    }


def fetch_market_snapshots(symbols: list[tuple[str, str]]) -> list[dict[str, float | str]]:
    snapshots: list[dict[str, float | str]] = []
    for symbol, label in symbols:
        try:
            snapshots.append(fetch_market_snapshot(symbol, label))
        except Exception:
            continue
    return snapshots


def dedupe_headlines(entries: Iterable[str], limit: int = 4) -> list[str]:
    seen: set[str] = set()
    headlines: list[str] = []

    for entry in entries:
        normalized = " ".join(entry.split()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        headlines.append(normalized)
        if len(headlines) >= limit:
            break

    return headlines


def fetch_raw_headlines(limit: int = 4) -> list[str]:
    candidates: list[str] = []
    for feed_url in HEADLINE_FEEDS:
        try:
            request = Request(feed_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                xml_bytes = response.read()

            root = ET.fromstring(xml_bytes)
            for item in root.findall("./channel/item")[:10]:
                title = (item.findtext("title") or "").strip()
                if title:
                    candidates.append(title)
        except Exception:
            continue

    return dedupe_headlines(candidates, limit=limit)


def translate_to_chinese(text: str) -> str:
    params = urlencode(
        [
            ("client", "gtx"),
            ("sl", "auto"),
            ("tl", "zh-CN"),
            ("dt", "t"),
            ("q", text),
        ]
    )
    payload = fetch_json(f"{TRANSLATE_ENDPOINT}?{params}")

    translated_parts: list[str] = []
    for chunk in payload[0]:
        if chunk and chunk[0]:
            translated_parts.append(str(chunk[0]))

    translated = "".join(translated_parts).strip()
    if not translated:
        raise RuntimeError("Empty translation response")
    return translated


def translate_to_chinese_fallback(text: str) -> str:
    params = urlencode(
        {
            "sl": "auto",
            "tl": "zh-CN",
            "q": text,
        }
    )
    page = fetch_text(f"https://translate.google.com/m?{params}")
    match = re.search(r'class="result-container">(.+?)</div>', page, flags=re.S)
    if not match:
        raise RuntimeError("Fallback translation response did not contain a result")

    translated = html.unescape(match.group(1)).strip()
    if not translated:
        raise RuntimeError("Fallback translation response was empty")
    return translated


def translate_to_chinese_mymemory(text: str) -> str:
    params = urlencode(
        {
            "q": text,
            "langpair": "en|zh-CN",
        }
    )
    payload = fetch_json(f"https://api.mymemory.translated.net/get?{params}")
    translated = str(payload.get("responseData", {}).get("translatedText", "")).strip()
    if not translated:
        raise RuntimeError("MyMemory translation response was empty")
    return translated


def translate_headline(text: str) -> str:
    for fn in (translate_to_chinese, translate_to_chinese_fallback, translate_to_chinese_mymemory):
        try:
            return fn(text)
        except Exception:
            continue
    return "中文翻译暂不可用"


def fetch_headlines(limit: int = 4) -> list[dict[str, str]]:
    return [
        {"original": headline, "translated": translate_headline(headline)}
        for headline in fetch_raw_headlines(limit=limit)
    ]


def find_snapshot(
    snapshots: list[dict[str, float | str]], symbol: str
) -> dict[str, float | str] | None:
    for item in snapshots:
        if item["symbol"] == symbol:
            return item
    return None


def format_market_line(item: dict[str, float | str]) -> str:
    sign = "+" if float(item["change_pct"]) >= 0 else ""
    return (
        f"- {item['label']} {item['symbol']}: "
        f"{float(item['price']):.2f} ({sign}{float(item['change_pct']):.2f}%)"
    )


def overall_risk_tone(snapshots: list[dict[str, float | str]]) -> str:
    qqq = find_snapshot(snapshots, "QQQ")
    tlt = find_snapshot(snapshots, "TLT")
    uso = find_snapshot(snapshots, "USO")

    qqq_change = float(qqq["change_pct"]) if qqq else 0.0
    tlt_change = float(tlt["change_pct"]) if tlt else 0.0
    uso_change = float(uso["change_pct"]) if uso else 0.0

    if qqq_change >= 0.8 and tlt_change >= 0:
        return "风险偏好修复，成长板块相对占优。"
    if qqq_change <= -0.8 and uso_change > 1:
        return "风险偏好承压，油价与利率因素对成长股不利。"
    if qqq_change <= -0.8:
        return "科技股承压，市场更偏防御。"
    return "市场仍在等待更明确的宏观与盈利线索。"


def today_in_shanghai() -> dt.datetime:
    return dt.datetime.now(ASIA_SHANGHAI)


def write_brief(path: str, brief: dict[str, str]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(brief, handle, ensure_ascii=True, indent=2)
