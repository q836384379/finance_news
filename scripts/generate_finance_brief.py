from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

TIMEOUT_SECONDS = 20
USER_AGENT = "finance-news-action/1.1"
ASIA_SHANGHAI = dt.timezone(dt.timedelta(hours=8))

MARKET_SYMBOLS = [
    ("SPY", "标普500ETF"),
    ("QQQ", "纳指100ETF"),
    ("DIA", "道指ETF"),
    ("TLT", "美债ETF"),
    ("USO", "原油ETF"),
    ("BTC-USD", "比特币"),
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


def dedupe_headlines(entries: Iterable[str], limit: int = 3) -> list[str]:
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


def fetch_raw_headlines() -> list[str]:
    candidates: list[str] = []
    for feed_url in HEADLINE_FEEDS:
        try:
            request = Request(feed_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                xml_bytes = response.read()

            root = ET.fromstring(xml_bytes)
            for item in root.findall("./channel/item")[:8]:
                title = (item.findtext("title") or "").strip()
                if title:
                    candidates.append(title)
        except Exception:
            continue

    return dedupe_headlines(candidates, limit=3)


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
    url = f"{TRANSLATE_ENDPOINT}?{params}"
    payload = fetch_json(url)

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


def fetch_headlines() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for headline in fetch_raw_headlines():
        translated = ""
        try:
            translated = translate_to_chinese(headline)
        except Exception:
            try:
                translated = translate_to_chinese_fallback(headline)
            except Exception:
                try:
                    translated = translate_to_chinese_mymemory(headline)
                except Exception:
                    translated = "中文翻译暂不可用"

        items.append(
            {
                "original": headline,
                "translated": translated,
            }
        )

    return items


def format_market_line(item: dict[str, float | str]) -> str:
    symbol = str(item["symbol"])
    label = str(item["label"])
    price = float(item["price"])
    change_pct = float(item["change_pct"])
    sign = "+" if change_pct >= 0 else ""
    return f"- {label} {symbol}: {price:.2f} ({sign}{change_pct:.2f}%)"


def build_body(
    snapshot: list[dict[str, float | str]], headlines: list[dict[str, str]]
) -> str:
    lines: list[str] = []
    lines.append("市场快照：")
    if snapshot:
        lines.extend(format_market_line(item) for item in snapshot)
    else:
        lines.append("- 今日市场数据暂时获取失败。")

    lines.append("")
    lines.append("新闻焦点：")
    if headlines:
        for item in headlines:
            lines.append(f"- 原文：{item['original']}")
            lines.append(f"  中文：{item['translated']}")
    else:
        lines.append("- 今日公开新闻源暂未返回可用标题。")

    lines.append("")
    lines.append("提示：本简报由 GitHub Actions 自动生成，仅供信息参考，不构成投资建议。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="brief.json")
    args = parser.parse_args()

    snapshot: list[dict[str, float | str]] = []
    for symbol, label in MARKET_SYMBOLS:
        try:
            snapshot.append(fetch_market_snapshot(symbol, label))
        except Exception:
            continue

    headlines = fetch_headlines()
    if not snapshot and not headlines:
        raise SystemExit("No market snapshot or headlines could be fetched.")

    now = dt.datetime.now(ASIA_SHANGHAI)
    brief = {
        "title": f"{now.month}月{now.day}日财经早报",
        "body": build_body(snapshot, headlines),
        "link_text": "查看 SPY 图表",
        "link_url": "https://finance.yahoo.com/quote/SPY/chart",
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(brief, handle, ensure_ascii=True, indent=2)

    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
