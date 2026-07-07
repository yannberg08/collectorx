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

### 同花顺自选股

```bash
python3 skills/ths-watchlist/scripts/ths_watchlist.py collect \
  --input <authorized-ths-watchlist-export-or-folder> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized Tonghuashun watchlist exports into `ths-watchlist`
  `watchlist` events.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, and TXT.
- Captures symbol, name, market, group, industry, tags, note/reason, and
  added time when present.
- Recursively filters credential-like raw keys.
- This is attention-universe evidence only. It does not prove holdings, trades,
  orders, or fund flows; use `ths-portfolio` for strong trading evidence.

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
- It does not read file content. Research content reading belongs to the
  explicit `research-documents` lens step below.
- The manifest records the macOS/Windows/Linux default-root plan for product
  preflight, but FinClaw should still pass explicit user-authorized roots when
  possible.

### 研报 / 财报 / 估值表内容

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source research-documents \
  --input <authorized-research-folder> \
  --include-content \
  --out-dir <out-dir>
```

Current status:

- Reads content only when `--include-content` is explicitly supplied.
- Supports Markdown/TXT/HTML, CSV/TSV, XLSX/XLSM, DOCX, and PDF extraction.
- Extracted text is capped and carries parser/status metadata.
- `manifest.collection_audit` records candidate counts, filtered counts, skipped
  extensions, parser counts, content-read counts, and the active content policy.
- Broad file-title hints such as a lone "股票" or "基金" do not enter Wiki
  evidence without stronger research context.
- Generic `filesystem` remains metadata-only; investment routing stays in the
  `research-documents` lens.

### 雪球投资活动

```bash
python3 skills/xueqiu-watchlist/scripts/xueqiu_query.py collect \
  --input <authorized-xueqiu-watchlist-export-or-folder> \
  --out-dir <out-dir>
```

Current status for `xueqiu-watchlist`:

- Converts authorized Xueqiu watchlist exports into `xueqiu-watchlist`
  `watchlist` events.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, TXT, and ZIP
  packages.
- Captures symbol, code, market, name, group, industry, tags, note/reason, and
  followed time when present; ZIP packages preserve `archive.zip::member`
  provenance and skip path-traversal members.
- Recursively filters credential-like raw keys.
- This is attention-universe evidence only. It does not prove holdings, trades,
  orders, or fund flows.

```bash
python3 skills/xueqiu-investor-activity/scripts/xueqiu_activity.py collect \
  --input <authorized-xueqiu-export-or-folder> \
  --out-dir <out-dir> \
  --sync-soulmirror
```

Current status:

- Parses authorized JSON/JSONL/CSV/TSV/XLSX/XLSM/HTML/TXT/ZIP exports for
  watchlists, follows, posts, comments, favorites, saved pages, and owner
  portfolio/rebalance records.
- Normalizes Snowball-like `statuses/list/data/items/stocks/cubes` payloads,
  preserves ZIP member provenance, strips credential-like keys from retained raw
  metadata, and writes a standard `investor_wiki_evidence.v1.json`.
- Not yet a real login/session collector.
- Not a broker-confirmed trade source.

### 中国基金理财资产

```bash
python3 skills/china-wealth-assets/scripts/china_wealth.py collect \
  --input <authorized-fund-or-wealth-export> \
  --out-dir <out-dir> \
  --sync-soulmirror
```

Current status:

- Parses authorized CSV/TSV/JSON/JSONL/XLSX/XLSM/HTML/TXT/ZIP exports for fund
  holdings, wealth holdings, cash-management holdings, subscriptions,
  redemptions, dividends, and asset snapshots.
- Normalizes platform names for Alipay, Tiantian Fund, Danjuan, Qieman, and
  bank wealth exports, preserves numeric asset/trade fields, records ZIP member
  provenance, and strips credential-like raw keys.
- Per-platform adapters for Alipay/Tiantian/Danjuan/Qieman/banks still need
  real validation.
- Any parsed input is treated as partial authorized input until platform/account
  coverage is verified.
- `manifest.platform_coverage` tells FinClaw which expected P0 platforms were
  observed in the authorized input and which are still missing.
- `manifest.field_coverage` and `manifest.asset_value_summary` tell FinClaw
  which key asset fields are present and summarize this run's authorized values
  by platform.

### 邮件

IMAP collection:

```bash
python3 skills/email-collector/scripts/email_api.py collect \
  --account all \
  --format json \
  --event-export <out-dir>/lake/email/events.jsonl
```

Authorized local export import:

```bash
python3 skills/email-collector/scripts/email_api.py import \
  --input <authorized-eml-mbox-json-csv-email-export> \
  --out-dir <out-dir>
```

Current status:

- Converts IMAP messages or authorized local EML/MBOX/JSON/JSONL/CSV/TSV/ZIP
  exports into generic `email` events.
- Captures mailbox, folder, sender, recipients, cc, subject, date,
  body preview, message ID, attachment refs, and ZIP member provenance.
- Does not include full body by default; `--event-include-body` requires
  explicit authorization.
- Does not write attachment bodies into events; attachment refs and raw refs
  filter token/cookie/password/secret-like keys.
- `email-research` can also match clear research attachment filenames such as
  broker reports, morning notes, roadshow invites, and financial statements.
- Does not claim investment-research status directly. Feed `lake/email/events.jsonl`
  into `email-research` for broker research, roadshow, and IR mail evidence.

### 笔记

```bash
python3 skills/notes-collector/scripts/notes_api.py obsidian \
  --vault <authorized-obsidian-vault> \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

For authorized exports from Youdao, Evernote/Yinxiang, Notion exports,
Markdown/HTML/TXT folders, JSON note exports, or ZIP export packages:

```bash
python3 skills/notes-collector/scripts/notes_api.py import \
  --input <authorized-notes-export-or-folder> \
  --source-app auto \
  --export <out-dir>/notes.json \
  --out-dir <out-dir>
```

Current status:

- Emits generic `notes` events and a standard package.
- Supports authorized local import for Markdown, HTML, TXT, JSON/JSONL,
  Evernote ENEX, and ZIP packages containing those formats.
- Writes `manifest.platform_coverage` with expected P1 note platforms
  (`obsidian`, `notion`, `youdao`, `evernote`), observed platforms, missing
  platforms, event counts, and `real_account_validation`.
- Writes `manifest.field_coverage`, `source_audit`, and `content_policy` so
  FinClaw can tell whether title/path/content preview/tags/time fields are
  present, whether ZIP member provenance exists, and whether the run used
  preview-only or full-content authorization.
- Does not claim investment-note status directly.
- Feed `lake/notes/events.jsonl` into `investment-notes` lens for investor Wiki
  evidence.

### 滴答清单 / 任务

```bash
python3 skills/ticktick-cli/scripts/ticktick_events.py collect \
  --input <authorized-ticktick-task-json-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized TickTick/Dida task JSON/JSONL/ZIP exports into generic
  `ticktick` task events.
- Writes `manifest.platform_coverage` with `ticktick`/`dida365` source
  coverage, missing sources, event counts, and `real_account_validation`.
- Filters credential-like raw keys such as password, cookie, token, session,
  secret, authorization, and credential.
- Does not claim investment-task status directly.
- Feed `lake/ticktick/events.jsonl` into `task-calendar-investor` lens for
  trading plans, research tasks, and review reminders.
- Live TickTick API collection requires the user's OAuth token.

### 日历

```bash
python3 skills/calendar-collector/scripts/calendar_query.py collect \
  --input <authorized-calendar-ics-json-csv-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized ICS, JSON/JSONL, CSV, TSV, and ZIP exports into generic
  `calendar` events.
- Captures title, start/end time, all-day status, location, meeting links,
  organizer, attendees, recurrence, and reminders.
- Writes `manifest.platform_coverage` with expected P1 calendar platforms
  (Apple, Google, Outlook, Feishu, DingTalk, WeCom, Tencent Meeting), observed
  platforms, missing platforms, event counts, and `real_account_validation`.
- Does not claim investment-calendar status directly.
- Feed `lake/calendar/events.jsonl` into `task-calendar-investor` lens for
  trading plans, earnings events, research meetings, and review reminders.

### 钉钉 / 企业微信协作导出

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform dingtalk \
  --input <authorized-dingtalk-export> \
  --out-dir <out-dir>
```

```bash
python3 skills/collaboration-exports/scripts/collaboration_exports.py collect \
  --platform wecom \
  --input <authorized-wecom-export> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, and TXT
  collaboration exports into `dingtalk` or `wecom` events.
- Captures messages, chats, contacts, file refs, meeting refs, sender, receiver,
  department, participants, meeting links, file names, tags, and content
  previews.
- Filters credential-like raw keys and keeps file bodies out of the generic
  collaboration collector.
- Does not claim investment collaboration directly.
- Feed `lake/dingtalk/events.jsonl` and `lake/wecom/events.jsonl` into
  downstream investor lenses such as `meeting-minutes`, future collaboration
  dialogue lenses, and research-document routing.

### 会议产物

```bash
python3 skills/meeting-artifacts/scripts/meeting_artifacts.py collect \
  --input <authorized-meeting-minutes-transcript-folder-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized local minutes/transcript/subtitle files, ZIP packages,
  and common platform export files into generic `meeting-artifacts` events.
- Supported export shapes include Markdown, TXT, HTML, JSON/JSONL/NDJSON,
  CSV/TSV, VTT, and SRT.
- Normalizes Feishu, DingTalk, WeCom, and Tencent Meeting platform evidence
  into stable platform values and captures participants, organizer, meeting
  links, start/end time, text preview, and attachment refs where present.
- Writes `manifest.platform_coverage` with expected P1 meeting platforms,
  observed platforms, missing platforms, event counts, and
  `real_account_validation`.
- Filters credential-like raw keys such as password, cookie, token, session,
  secret, authorization, and credential.
- Does not claim investment-meeting status directly.
- Feed `lake/meeting-artifacts/events.jsonl` into `meeting-minutes` lens for
  roadshows, research meetings, IC records, and review meetings.
- Feishu/DingTalk/WeCom/Tencent Meeting account API adapters still require
  real authorization validation.

### 微信收藏 / 公众号文章

```bash
python3 skills/wechat-favorites/scripts/wechat_favorites.py collect \
  --input <authorized-wechat-favorites-saved-article-folder-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL, CSV/TSV, HTML, Markdown, TXT, and ZIP
  saved-article records into generic `wechat-favorites` events.
- Writes `manifest.action_coverage` with expected user actions: favorite,
  read, share, and saved file.
- Captures source account count and filters credential-like raw keys.
- Does not claim investment-article status directly.
- Feed `lake/wechat-favorites/events.jsonl` into `wechat-article-favorites`
  lens for investment public-account articles and saved reading sources.
- Real WeChat favorites database/public-account read-history adapters still
  require version-specific validation.

### 财经资讯使用痕迹

```bash
python3 skills/financial-news-usage/scripts/financial_news_usage.py collect \
  --input <authorized-cls-wallstreetcn-gelonghui-usage-export-or-zip-or-history-copy> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL, CSV/TSV, HTML, Markdown, TXT, ZIP packages,
  Chromium `History`, and Safari `History.db` usage records into
  `financial-news-usage` events.
- Captures user actions: read, favorite, subscribe, search, and alert.
- Writes `manifest.platform_coverage` for CLS, WallstreetCN, and Gelonghui,
  plus `manifest.action_coverage` for expected user actions.
- For browser history, filters to CLS, WallstreetCN, and Gelonghui domains
  before writing events.
- Captures domain, source app, URL, title, visit time, visit count, typed count,
  tags, symbols, and article ID where present.
- Preserves file/ZIP member provenance in `raw_ref.path`.
- Recursively filters credential-like raw keys.
- Outputs `investor_wiki_evidence.v1.json` for information-consumption and
  monitoring-rule evidence.
- Does not crawl public news or platform-wide content.
- Real CLS/WallstreetCN/Gelonghui app caches, account APIs, and subscription
  stores still require account-level validation.

### 港美股券商

```bash
python3 skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect \
  --input <authorized-futu-tiger-ibkr-readonly-export-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized CSV/TSV/JSON/JSONL/NDJSON/XLSX/XLSM/ZIP exports into
  `hk-us-brokerage` events.
- Expands multi-section JSON packages, including assets, positions, executions,
  orders, cashflows, dividends, and FX; ZIP packages preserve
  `archive.zip::member` provenance.
- Captures strong brokerage fields: assets, positions, executions, orders,
  cashflows, dividends, FX, margin, tax, settlement dates, order type, time in
  force, net liquidation, and multi-currency amounts.
- Writes broker, trade-surface, and recommended strong-field coverage manifests
  so FinClaw can see missing brokers/tables/fields before treating the package
  as a full brokerage boundary.
- Preserves business numbers needed by the investor avatar.
- Does not ask for passwords and does not place, cancel, or modify orders.
- Real Futu/Tiger/IBKR account exports or read-only screens still require
  account-level validation.

### 专业金融终端使用痕迹

```bash
python3 skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect \
  --input <authorized-wind-choice-ifind-workflow-export-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  TXT, INI/CONF, LOG, and ZIP workflow records into `pro-terminal-usage`
  events.
- Expands multi-section workflow packages, including workspaces, dashboards,
  watchlists, searches, downloads, exports, templates, models, factors, and
  indicators; ZIP packages preserve `archive.zip::member` provenance.
- Captures workspaces, watchlists, searches, downloads, model templates, and
  factor attention.
- Captures workflow metadata such as function codes, menu paths, projects,
  strategy names, datasets, fields, frequency, date ranges, download formats,
  file names, symbols, industries, markets, and regions.
- Writes terminal, activity, and workflow-field coverage manifests so FinClaw
  can see missing platforms, activity types, or research-workflow metadata.
- Outputs workflow evidence for capability circle, research workflow, monitoring
  rules, and information-source dimensions.
- Does not copy vendor databases, public market data, reports, or licensed
  content bodies.
- Real Wind/Choice/iFinD/Bloomberg native exports still require license-safe
  account-level validation.

### 社交平台用户活动

```bash
python3 skills/social-activity/scripts/social_activity.py collect \
  --input <authorized-weibo-bilibili-xiaohongshu-activity-export-or-zip> \
  --out-dir <out-dir>
```

Current status:

- Converts authorized JSON/JSONL/NDJSON, CSV/TSV, XLSX/XLSM, HTML, Markdown,
  TXT, and ZIP activity records into generic `social-activity` events.
- Expands multi-section activity packages such as follows, likes, favorites,
  watch history, comments, shares, and reposts; ZIP packages preserve
  `archive.zip::member` provenance.
- Captures follows, likes, favorites, watch/view history, comments, shares, and
  saved pages.
- Captures creator IDs, creator URLs, domains, item IDs, tags, topics, symbols,
  engagement counts, watch progress, and comment/content previews.
- Every emitted event marks itself as `weak_influence_signal`,
  `investment_claim_allowed: false`, and `requires_corroboration: true`.
- Writes platform, action, weak-signal-field coverage and weak-evidence-policy
  manifests.
- Does not claim investment influence directly.
- Feed `lake/social-activity/events.jsonl` into `social-investment-influence`
  lens. Treat resulting evidence as weak influence evidence unless corroborated
  by stronger sources.

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
