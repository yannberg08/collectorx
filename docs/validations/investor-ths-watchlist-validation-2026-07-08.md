# Tonghuashun Watchlist Collector Validation

Date: 2026-07-08

## Scope

This pass productizes `ths-watchlist` from a YAML/README placeholder into a
runnable baseline collector for user-authorized Tonghuashun watchlist exports.

The collector is intentionally narrower than `ths-portfolio`:

- It collects watchlist and attention-universe evidence.
- It does not collect or infer holdings, executions, orders, or fund flows.
- It never asks for passwords, trading passwords, cookies, tokens, sessions, or
  device fingerprints.

## Inputs Covered

Fixture validation covers:

- CSV/TSV table exports.
- JSON/JSONL/NDJSON packages with nested watchlist sections.
- XLSX/XLSM workbook exports.
- HTML, Markdown, and TXT files with simple stock-code lists.
- Missing-input preflight/gap behavior.

## Output Contract

The CLI writes:

- `lake/ths-watchlist/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

Each event uses `collectorx.event.v1`, collector `ths-watchlist`, kind
`watchlist`, and Wiki targets:

- `investor.opportunity_watchlist.watchlist`
- `investor.capability_circle.attention_universe`

## Product Boundary

Watchlist evidence is useful for FinClaw because it tells the investor avatar
what the user has watched, grouped, tagged, or annotated. It is not strong
trading evidence. FinClaw should corroborate it with:

- `ths-portfolio` / `eastmoney-portfolio` trade and holding evidence.
- Research files and notes.
- Calendar/task/review evidence.
- News and social influence signals when relevant.

## Validation Result

Status: `completed-baseline`

Gate reached: G1 Runnable Baseline

Not claimed:

- Real Tonghuashun account/app validation.
- Complete user attention-universe coverage.
- Strong transaction, holding, order, or cashflow capture.
- Windows/Linux real-device validation.

Next gates:

- G2: discover and validate real Tonghuashun watchlist export/local-store
  workflow with user authorization.
- G3: run against real account/device exports on macOS, Windows, and Linux where
  applicable.
- G4: backtest against actual trades/research to confirm watchlist evidence
  lands in the right investor Wiki subdimensions without over-claiming.
