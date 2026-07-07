#!/usr/bin/env python3
"""Run the first deterministic investor-avatar loop.

This is not the final LLM distill app. It is a small, verifiable bridge that
proves the data path:

CSV -> CollectorX events -> lake -> investor wiki -> maturity summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
THS_SCRIPTS = ROOT / "skills" / "ths-portfolio" / "scripts"
sys.path.insert(0, str(THS_SCRIPTS))

from ths.events import records_to_events  # noqa: E402
from ths.parser import parse_portfolio_csv  # noqa: E402
from ths.stats import calculate_stats, calculate_stock_stats  # noqa: E402


CN_TZ = timezone(timedelta(hours=8))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the first investor avatar loop")
    parser.add_argument(
        "--input-csv",
        default=str(ROOT / "examples" / "fixtures" / "ths-portfolio.sample.csv"),
        help="Tonghuashun portfolio CSV",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / ".tmp" / "first-investor-loop"),
        help="Output directory for lake/wiki artifacts",
    )
    parser.add_argument(
        "--collected-at",
        default=datetime.now(CN_TZ).isoformat(timespec="seconds"),
        help="Collection timestamp",
    )
    args = parser.parse_args()

    input_csv = Path(args.input_csv).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    records = parse_portfolio_csv(str(input_csv))
    events = records_to_events(
        records,
        source="同花顺交割单 CSV",
        raw_file=str(input_csv),
        collected_at=args.collected_at,
    )

    lake_events = out_dir / "lake" / "ths-portfolio" / "events.jsonl"
    _write_jsonl(lake_events, events)

    wiki_root = out_dir / "wiki" / "vertical" / "investor"
    stats = calculate_stats(records)
    stock_stats = calculate_stock_stats(records)
    _write_investor_wiki(wiki_root, records, events, stats, stock_stats)

    maturity = _maturity_summary(events, records)
    maturity_path = out_dir / "wiki" / "vertical" / "investor_maturity.json"
    _write_json(maturity_path, maturity)

    summary_path = out_dir / "SUMMARY.md"
    _write_summary(summary_path, input_csv, out_dir, events, maturity)

    print(json.dumps({
        "ok": True,
        "records": len(records),
        "events": len(events),
        "lake": str(lake_events),
        "wiki": str(wiki_root),
        "maturity": str(maturity_path),
        "summary": str(summary_path),
    }, ensure_ascii=False, indent=2))
    return 0


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.rstrip() + "\n", encoding="utf-8")


def _write_investor_wiki(
    wiki_root: Path,
    records: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    stats: Dict[str, Any],
    stock_stats: List[Dict[str, Any]],
) -> None:
    _write_md(
        wiki_root / "record-review" / "决策日志.md",
        _decision_log(records, events),
    )
    _write_md(
        wiki_root / "risk-portfolio" / "组合约束.md",
        _portfolio_constraints(stats, stock_stats),
    )
    _write_md(
        wiki_root / "competence-circle" / "公司能力圈.md",
        _company_coverage(stock_stats),
    )
    _write_md(
        wiki_root / "decision-framework" / "仓位决策.md",
        _position_sizing(records),
    )


def _decision_log(records: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> str:
    lines = [
        "---",
        "maturity: basic",
        "source: ths-portfolio",
        "---",
        "",
        "# 决策日志",
        "",
        "本文件由同花顺交割单事件生成,只记录可从交易数据直接证明的事实,不推断投资理由。",
        "",
        "| 时间 | 标的 | 方向 | 价格 | 数量 | 金额 | 证据 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for record, event in zip(records, events):
        time = f"{record.get('date', '')} {record.get('time', '')}".strip()
        stock = f"{record.get('code', '')} {record.get('name', '')}".strip()
        lines.append(
            f"| {time} | {stock} | {record.get('direction', '')} | "
            f"{record.get('price', 0):,.2f} | {record.get('quantity', 0):,} | "
            f"{record.get('amount', 0):,.2f} | `{event['id']}` |"
        )
    return "\n".join(lines)


def _portfolio_constraints(stats: Dict[str, Any], stock_stats: List[Dict[str, Any]]) -> str:
    total = stats.get("total", 0)
    buy_amount = stats.get("buy_amount", 0.0)
    sell_amount = stats.get("sell_amount", 0.0)
    net_amount = stats.get("net_amount", 0.0)
    lines = [
        "---",
        "maturity: hint",
        "source: ths-portfolio",
        "---",
        "",
        "# 组合约束",
        "",
        "当前只接入了交易记录,尚未接入完整持仓、账户资产和现金约束。因此这里只能形成初步画像。",
        "",
        f"- 交易记录数: {total}",
        f"- 买入金额: {buy_amount:,.2f}",
        f"- 卖出金额: {sell_amount:,.2f}",
        f"- 交易净额: {net_amount:,.2f}",
        "",
        "## 个股交易集中度线索",
        "",
    ]
    for item in stock_stats:
        lines.append(
            f"- {item['stock']}: {item['count']} 笔, "
            f"买入 {item['buy_amount']:,.2f}, 卖出 {item['sell_amount']:,.2f}, "
            f"净额 {item['net_amount']:,.2f}"
        )
    return "\n".join(lines)


def _company_coverage(stock_stats: List[Dict[str, Any]]) -> str:
    lines = [
        "---",
        "maturity: hint",
        "source: ths-portfolio",
        "---",
        "",
        "# 公司能力圈",
        "",
        "交易记录只能证明用户曾经交易过这些公司,不能直接证明用户真正理解这些公司。",
        "需要结合投研笔记、聊天讨论、复盘记录后才能提高成熟度。",
        "",
    ]
    for item in stock_stats:
        lines.append(f"- {item['stock']}: 出现在交割单中 {item['count']} 次")
    return "\n".join(lines)


def _position_sizing(records: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = f"{record.get('code', '')} {record.get('name', '')}".strip()
        grouped[key].append(record)

    lines = [
        "---",
        "maturity: hint",
        "source: ths-portfolio",
        "---",
        "",
        "# 仓位决策",
        "",
        "当前只有成交记录,还缺少总资产、持仓快照和交易前后仓位,不能直接还原真实仓位比例。",
        "这里先记录每个标的的单笔交易规模,作为后续仓位规则蒸馏的证据。",
        "",
    ]
    for stock, rows in grouped.items():
        amounts = [row.get("amount", 0.0) for row in rows]
        lines.append(f"- {stock}: 单笔金额范围 {min(amounts):,.2f} - {max(amounts):,.2f}")
    return "\n".join(lines)


def _maturity_summary(events: List[Dict[str, Any]], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    stocks = sorted({f"{r.get('code', '')} {r.get('name', '')}".strip() for r in records if r.get("code") or r.get("name")})
    return {
        "schema": "finclaw.investor_maturity.v0.1",
        "score": 8,
        "computed_from": {
            "collector": "ths-portfolio",
            "events": len(events),
            "stocks": stocks,
        },
        "dimensions": {
            "record_review": {
                "score": 20,
                "reason": "已有结构化交易记录,但缺少买卖理由与复盘。",
            },
            "risk_portfolio": {
                "score": 8,
                "reason": "只有交易金额线索,缺少持仓、总资产、现金和回撤数据。",
            },
            "competence_circle": {
                "score": 5,
                "reason": "只知道交易过哪些公司,不能证明理解深度。",
            },
            "decision_framework": {
                "score": 5,
                "reason": "可看到动作,看不到触发条件和证据标准。",
            },
        },
        "next_data_needed": [
            "持仓快照",
            "总资产或仓位比例",
            "买入/卖出理由",
            "投研笔记",
            "交易复盘",
        ],
    }


def _write_summary(
    path: Path,
    input_csv: Path,
    out_dir: Path,
    events: List[Dict[str, Any]],
    maturity: Dict[str, Any],
) -> None:
    lines = [
        "# First Investor Loop Summary",
        "",
        f"- Input CSV: `{input_csv}`",
        f"- Output root: `{out_dir}`",
        f"- Events written: {len(events)}",
        f"- Investor maturity score: {maturity['score']}",
        "",
        "## Data Path",
        "",
        "```text",
        "ths-portfolio.sample.csv",
        "  -> ths parser",
        "  -> collectorx.event.v1 JSONL",
        "  -> lake/ths-portfolio/events.jsonl",
        "  -> deterministic investor organize step",
        "  -> wiki/vertical/investor/*.md",
        "  -> investor_maturity.json",
        "```",
        "",
        "## Current Limits",
        "",
        "- This loop proves the file/data path; it is not yet the final LLM distill pipeline.",
        "- Trade records reveal actions, not the user's full reasons or decision framework.",
        "- Next data needed: holdings, notes, review records, and investment conversations.",
    ]
    _write_md(path, "\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
