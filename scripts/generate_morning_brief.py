from __future__ import annotations

import argparse
import json

from finance_brief_common import (
    MARKET_SYMBOLS,
    fetch_headlines,
    fetch_market_snapshots,
    find_snapshot,
    format_market_line,
    overall_risk_tone,
    today_in_shanghai,
    write_brief,
)


def build_body() -> str:
    snapshots = fetch_market_snapshots(MARKET_SYMBOLS)
    headlines = fetch_headlines(limit=4)

    us_focus = [
        item
        for item in snapshots
        if item["symbol"] in {"SPY", "QQQ", "TLT", "USO", "BTC-USD"}
    ]
    ah_focus = [
        item
        for item in snapshots
        if item["symbol"] in {"000001.SS", "399001.SZ", "^HSI", "^HSTECH"}
    ]

    lines: list[str] = []
    lines.append("财经早报")
    lines.append(overall_risk_tone(snapshots))
    if us_focus:
        lines.extend(format_market_line(item) for item in us_focus)
    if headlines:
        lines.append("新闻焦点：")
        for item in headlines[:3]:
            lines.append(f"- 原文：{item['original']}")
            lines.append(f"  中文：{item['translated']}")

    lines.append("")
    lines.append("A股/港股视角")
    hsi = find_snapshot(snapshots, "^HSI")
    hstech = find_snapshot(snapshots, "^HSTECH")
    tlt = find_snapshot(snapshots, "TLT")
    uso = find_snapshot(snapshots, "USO")

    implications: list[str] = []
    if tlt and float(tlt["change_pct"]) < 0:
        implications.append("美债承压意味着全球利率敏感资产估值修复空间仍受限制。")
    else:
        implications.append("美债压力若缓和，港股成长和科技方向更容易获得估值支撑。")

    if uso and float(uso["change_pct"]) > 1:
        implications.append("油价偏强更利于资源与能源链，但会压制航空、运输和部分制造利润预期。")
    else:
        implications.append("油价若回落，A股和港股对成本敏感的消费与制造板块情绪会相对受益。")

    if hstech and float(hstech["change_pct"]) < 0:
        implications.append("恒生科技若走弱，说明外部科技风险偏好传导仍不稳定，开盘追高需要谨慎。")
    elif hstech:
        implications.append("恒生科技若企稳，港股科技链条对外盘风险偏好的映射会更积极。")

    if ah_focus:
        lines.extend(format_market_line(item) for item in ah_focus)
    for item in implications[:3]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("风险提示")
    lines.append("- 关注美债收益率是否重新抬升，避免成长板块再受估值压制。")
    lines.append("- 关注油价与地缘事件是否继续发酵，防止资源上涨挤压其他板块情绪。")
    lines.append("- 关注海外科技龙头财报和指引变化，对A/H科技链条的传导可能更快。")
    lines.append("")
    lines.append("提示：本简报由 GitHub Actions 自动生成，仅供信息参考，不构成投资建议。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="brief.json")
    args = parser.parse_args()

    now = today_in_shanghai()
    brief = {
        "title": f"{now.month}月{now.day}日早间财经简报",
        "body": build_body(),
        "link_text": "查看恒生科技指数",
        "link_url": "https://finance.yahoo.com/quote/%5EHSTECH/",
    }
    write_brief(args.out, brief)
    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

