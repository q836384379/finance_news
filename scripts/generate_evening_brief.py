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
        if item["symbol"] in {"SPY", "QQQ", "DIA", "TLT", "USO", "BTC-USD"}
    ]
    qqq = find_snapshot(snapshots, "QQQ")
    tlt = find_snapshot(snapshots, "TLT")
    uso = find_snapshot(snapshots, "USO")

    lines: list[str] = []
    lines.append("美股投资者视角")
    lines.append(overall_risk_tone(snapshots))
    if us_focus:
        lines.extend(format_market_line(item) for item in us_focus)
    if headlines:
        lines.append("市场焦点：")
        for item in headlines[:3]:
            lines.append(f"- 原文：{item['original']}")
            lines.append(f"  中文：{item['translated']}")

    lines.append("")
    lines.append("今晚关注")
    watch_items: list[str] = []
    if qqq and float(qqq["change_pct"]) >= 0:
        watch_items.append("科技龙头与AI链条若继续领涨，纳指风格可能延续。")
    else:
        watch_items.append("科技龙头若继续承压，需要警惕纳指与半导体波动放大。")

    if tlt and float(tlt["change_pct"]) < 0:
        watch_items.append("美债ETF走弱，说明收益率压力仍在，长久期成长股估值要更谨慎。")
    else:
        watch_items.append("若美债压力缓和，成长板块更容易获得估值支撑。")

    if uso and float(uso["change_pct"]) > 1:
        watch_items.append("油价偏强时，能源股更占优，但会抬高整体通胀担忧。")
    else:
        watch_items.append("油价若回落，有利于市场把焦点重新放回盈利与科技主线。")

    for item in watch_items:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("风险提示")
    lines.append("- 关注美债收益率、美元和油价是否同步走强，这会压制风险资产。")
    lines.append("- 关注大型科技股财报或指引是否引发AI主线重新定价。")
    lines.append("- 关注美国宏观数据与美联储表态，防止降息预期再度回摆。")
    lines.append("")
    lines.append("提示：本简报由 GitHub Actions 自动生成，仅供信息参考，不构成投资建议。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="brief.json")
    args = parser.parse_args()

    now = today_in_shanghai()
    brief = {
        "title": f"{now.month}月{now.day}日晚间美股观察",
        "body": build_body(),
        "link_text": "查看纳指100ETF",
        "link_url": "https://finance.yahoo.com/quote/QQQ/",
    }
    write_brief(args.out, brief)
    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

