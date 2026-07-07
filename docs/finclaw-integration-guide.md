# FinClaw Integration Guide

CollectorX is the personal evidence layer for FinClaw. FinClaw should call
CollectorX collectors to get user-owned evidence, then pass the evidence through
SoulMirror/FinClaw distillation into the investor Wiki.

## Flow

```text
FinClaw UI / job runner
  -> CollectorX collector skill
  -> collectorx.event.v1 JSONL
  -> local lake
  -> finclaw.investor_wiki_evidence.v1
  -> investor-portrait distill/organize
  -> Wiki external.investor
```

Collectors do not write the final Wiki directly.

## What FinClaw Should Discover

FinClaw should read collector metadata from:

```text
collectors/generic/*.yaml
collectors/vertical/*.yaml
collectors/lenses/*.yaml
```

Each YAML declares:

- `id`: collector id
- `category`: `generic`, `vertical`, or `lens`
- `skill`: executable skill, if available
- `armed`: whether the user has explicitly enabled it
- `scope.collects`: allowed evidence
- `scope.excludes`: forbidden evidence
- `upstream_collectors`: for lenses

FinClaw should not run collectors with `armed: false` unless the user has just
authorized that collector in the product flow.

## Invocation Contract

A production collector should expose a CLI that can be run by FinClaw and produce
one or more of:

```text
<out-dir>/
├── lake/<collector-id>/events.jsonl
├── manifest.json
├── investor_wiki_evidence.v1.json
└── SUMMARY.md
```

The minimum useful output is `events.jsonl`, where each line is a
`collectorx.event.v1` object.

## Current Runnable Examples

### 东方财富

```bash
python3 skills/eastmoney-portfolio/scripts/eastmoney_query.py \
  --collect-local \
  --auto-trade-ui \
  --sync-soulmirror \
  --output <out-dir>
```

Preconditions:

- User has installed and logged into EastMoney.
- For strong trade tables, the trading account must be manually unlocked by the user.
- macOS Accessibility permission is required for read-only UI capture.

Do not ask for or store trading password, login password, cookie, token, session,
signature, or device fingerprint.

### 同花顺

```bash
python3 skills/ths-portfolio/scripts/ths_query.py \
  --local-scan \
  --include-metadata-events \
  --include-gui-events \
  --output <out-dir> \
  --sync-soulmirror
```

Preconditions:

- User has authorized local app/file access.
- GUI snapshot requires the relevant trading page to be visible/unlocked.

### 本地文件

```bash
python3 skills/filesystem-collector/scripts/filesystem_query.py collect \
  --root ~/Documents \
  --out-dir <out-dir>
```

Preconditions:

- User selects scan roots.

Boundary:

- This collector is metadata-only. It records path, extension, size, and mtime.
- It does not read file content. Research content reading belongs to a later
  explicit authorization/distillation step.

### 雪球投资活动

```bash
python3 skills/xueqiu-investor-activity/scripts/xueqiu_activity.py collect \
  --input <authorized-xueqiu-export-or-folder> \
  --out-dir <out-dir>
```

Current status:

- Parses authorized local exports for watchlists, follows, posts, comments,
  favorites, and owner portfolios.
- Not yet a real login/session collector.
- Not a broker-confirmed trade source.

### 中国基金理财资产

```bash
python3 skills/china-wealth-assets/scripts/china_wealth.py collect \
  --input <authorized-fund-or-wealth-export> \
  --out-dir <out-dir>
```

Current status:

- Parses authorized CSV/JSON exports for fund holdings, wealth holdings,
  subscriptions, redemptions, and asset snapshots.
- Per-platform adapters for Alipay/Tiantian/Danjuan/Qieman/banks still need
  real validation.
- Any parsed input is treated as partial authorized input until platform/account
  coverage is verified.

### 笔记

```bash
python3 skills/notes-collector/scripts/notes_api.py obsidian \
  --vault <authorized-obsidian-vault> \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

Current status:

- Emits generic `notes` events and a standard package.
- Does not claim investment-note status directly.
- Feed `lake/notes/events.jsonl` into `investment-notes` lens for investor Wiki
  evidence.

### 滴答清单 / 任务

```bash
python3 skills/ticktick-cli/scripts/ticktick_events.py collect \
  --input <authorized-ticktick-task-json> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized TickTick task JSON into generic `ticktick` task events.
- Does not claim investment-task status directly.
- Feed `lake/ticktick/events.jsonl` into `task-calendar-investor` lens for
  trading plans, research tasks, and review reminders.
- Live TickTick API collection requires the user's OAuth token.

### 投资 Lens / 分类工具

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py list-sources
```

Lenses should consume already-collected generic lake events. They should not
directly reconnect to WeChat, email, notes, or calendar accounts.

Example lens collection:

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source wechat-investment-dialogue \
  --input <wechat-collector-json-or-jsonl> \
  --out-dir <out-dir>
```

Default behavior:

- Generic-channel lenses only emit investment-matched evidence.
- Each emitted event includes `data.classification.confidence`,
  `data.classification.reasons`, `matched_terms`, and `matched_symbols`.
- The default relevance threshold is `--min-score 0.30`.
- Use `--include-non-matches` only for audit/backtest runs, not normal Wiki
  ingestion.
- If input is readable but not investment-related, the manifest status is
  `no_investment_evidence_matched` and Wiki coverage stays empty.

## Frontend / Product Preconditions

Before calling a collector, FinClaw should show the user:

1. Source name and category.
2. What will be collected.
3. What will not be collected.
4. Whether secrets/passwords are never requested.
5. Where output will be stored.
6. Whether the collector is production-ready, beta, baseline, lens-only, or placeholder.

The UI should only expose one-click collection for collectors at
`production-candidate`, `deep-beta`, or `baseline` levels. Placeholder collectors
should appear as roadmap items, not runnable actions.

## Platform Rules

Each collector must report platform status separately:

- `macos`: real-device, code-level, unsupported, or unknown
- `windows`: real-device, code-level, unsupported, or unknown
- `linux`: real-device, code-level, unsupported, or unknown

GUI automation claims require real screenshot/UI/readiness validation on that
platform. Parser-only code-level simulation is not enough to claim production.

## Security Rules

- Store user evidence locally by default.
- Never store passwords, payment passwords, trading passwords, cookies, tokens,
  sessions, signatures, device fingerprints, or raw network payloads.
- Do not turn public market data into personal evidence.
- Keep raw sensitive evidence in lake/raw refs; Wiki should receive distilled
  facts and evidence indexes.

## FinClaw Readiness Gate

FinClaw should inspect `manifest.json` when available:

- `collection_readiness.status`
- `event_count`
- `classification_summary` for lens collectors
- required strong table/materialization flags for broker collectors
- gap events and missing authorization states

If a collector only emits a gap/preflight event, FinClaw should show the missing
authorization/input, not treat it as collected personal data.
