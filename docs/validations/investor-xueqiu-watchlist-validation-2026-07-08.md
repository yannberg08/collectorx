# Xueqiu Watchlist Collector Validation

Date: 2026-07-08

## Scope

This pass upgrades `xueqiu-watchlist` from a draft CSV parser into a runnable
baseline collector for user-authorized Xueqiu watchlist exports.

The collector is deliberately narrow:

- It collects Xueqiu watchlist and attention-universe evidence.
- It does not collect posts, comments, favorites, or portfolio activity; those
  belong to `xueqiu-investor-activity`.
- It does not collect or infer broker-confirmed holdings, executions, orders, or
  fund flows.
- It never asks for passwords, cookies, tokens, sessions, or device
  fingerprints.

## Inputs Covered

Fixture validation covers:

- CSV/TSV table exports.
- JSON/JSONL/NDJSON packages with nested watchlist sections.
- XLSX/XLSM workbook exports.
- HTML, Markdown, and TXT files with simple A/HK stock-code lists.
- Missing-input preflight/gap behavior.
- Legacy `--file/--export/--list` JSON export compatibility.

## Output Contract

The standard CLI writes:

- `lake/xueqiu-watchlist/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

Each event uses `collectorx.event.v1`, collector `xueqiu-watchlist`, kind
`watchlist`, and Wiki targets:

- `investor.opportunity_watchlist.watchlist`
- `investor.capability_circle.attention_universe`

## Product Boundary

Xueqiu watchlists are useful for FinClaw because they show what the user watches
and how the user groups or annotates targets. They are not strong trading
evidence. FinClaw should corroborate them with:

- `xueqiu-investor-activity` posts, comments, favorites, follows, and portfolio
  records.
- Broker/portfolio collectors such as `eastmoney-portfolio`, `ths-portfolio`,
  and `hk-us-brokerage`.
- Research files, notes, calendar/tasks, and review evidence.

## Validation Result

Status: `completed-baseline`

Gate reached: G1 Runnable Baseline

Not claimed:

- Real Xueqiu account/app validation.
- Complete user watchlist boundary.
- Strong transaction, holding, order, or cashflow capture.
- Windows/Linux real-device validation.

Next gates:

- G2: discover and validate real Xueqiu watchlist export/local-store workflow
  with user authorization.
- G3: run against real account/device exports on macOS, Windows, and Linux where
  applicable.
- G4: backtest against actual trades, research, and Xueqiu activity to confirm
  watchlist evidence lands in the right investor Wiki subdimensions without
  over-claiming.
