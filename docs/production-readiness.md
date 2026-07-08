# Collector Production Readiness

This document is the honest product status for CollectorX. A collector being
listed in `collectors/` does not mean it is production-ready. The goal is to
avoid building placeholders that look complete.

## Readiness Levels

| Level | Meaning | Required proof |
| --- | --- | --- |
| `production-candidate` | Can be used by FinClaw with real user authorization on at least one verified platform | Real-device run, stable event output, readiness manifest, tests, no secret leakage |
| `deep-beta` | Deep design exists and the code path is substantial, but broader real-device coverage is still needed | Parser/unit tests, local package output, platform notes, at least one realistic validation |
| `baseline` | Can parse authorized exports or produce valid CollectorX events, but not yet a full production collector | CLI, fixture, tests, event output |
| `lens-registered` | Investment lens exists and has routing rules, but does not yet have a mature classifier/backtest | Upstream dependency declared, boundaries documented |
| `placeholder` | YAML/config entry only; not a runnable collector | Scope and exclusions documented |

## Latest Productization Wave

FinClaw catalog validation now checks runnable invocation contracts:

- `tools/validate_project.py` now verifies that each
  `collectors/finclaw-investor-catalog.json` entry points to the correct
  collector YAML category, an existing skill directory, and existing Python
  script paths.
- Lens catalog entries must include `--source <collector-id>` so the product
  cannot accidentally run the wrong lens profile.
- Non-SoulMirror entries must declare a concrete `<out-dir>` target; SoulMirror
  entries must use `apiVersion: soulmirror/v1` in their collector YAML.
- The new gate caught and fixed the `qq` catalog command: `--db-dir` is a
  top-level `qq_query.py` option, and the command now writes both compact QQ
  collect JSON and `lake/qq/events.jsonl` under `<out-dir>`.
- This improves product-entry safety, but it does not make QQ a full standard
  package collector yet; QQ still needs a complete `manifest.json`/`SUMMARY.md`
  package pass before broad FinClaw exposure.

The prior completed wave: `ticktick-cli` now has a SoulMirror-aligned live collector path:

- `collectors/generic/ticktick.yaml` is aligned to the SoulMirror
  YAML + AgentRunner + skill contract.
- The live collector entrypoint is `collect_for_soulmirror.py`, which returns a
  JSON array snapshot and leaves Lake writes, diffing, and state to the
  SoulMirror daemon.
- Missing auth now fails with `ticktick_auth_required` instead of returning an
  empty snapshot.
- `auth.py connect` supports a FinClaw-managed OAuth Broker through
  `TICKTICK_OAUTH_BROKER_URL`, so ordinary users do not need to create a Dida365
  developer app.
- Local validation covers both missing auth and a fake authorized OpenAPI flow
  for active/completed tasks, project-name mapping, inbox fallback, dedupe, and
  no token leakage in snapshot output.
- `ticktick_events.py` remains only an offline authorized export conversion
  helper and writes `exports/ticktick/events.jsonl` to avoid confusing it with
  daemon-owned `lake/ticktick/events.jsonl`.
- This improves P1 task planning ingestion, but it does not claim real
  TickTick account validation until the managed OAuth Broker is deployed and a
  real recurring-task/timezone backtest is run.

The prior completed wave: CollectorX now has a package-level FinClaw ingestion gate:

- Added `tools/validate_collector_package.py` to validate an output directory
  before FinClaw adds it to durable Lake or runs Wiki distillation.
- The gate checks `manifest.json`, `lake/<collector-id>/events.jsonl`,
  `collectorx.event.v1` required fields, privacy booleans, raw refs, and
  optional `investor_wiki_evidence.v1.json` contract validity.
- Added `tools/test_collector_package_validator.py` and wired the validator into
  project validation.
- `tools/run_first_investor_loop.py` now writes `manifest.json`, and the
  project smoke test validates the first-loop package with
  `--require-evidence`.
- This improves product integration safety; it does not claim new real-account
  validation for any individual collector.

The prior completed wave: `xueqiu-watchlist` and `ths-watchlist` now emit standard Investor Wiki evidence
packages for attention-universe signals:

- `xueqiu_query.py collect --input <authorized-watchlist-export> --out-dir
  <dir>` now writes `investor_wiki_evidence.v1.json` alongside
  `lake/xueqiu-watchlist/events.jsonl`, `manifest.json`, and `SUMMARY.md`.
- `ths_watchlist.py collect --input <authorized-watchlist-export> --out-dir
  <dir>` now writes the same evidence package shape for Tonghuashun watchlists.
- Both packages pass the shared 7-dimension/20-subdimension contract and route
  watchlists to market-view, value-preference, industry-circle,
  information-learning-style, style-profile, and information-source
  subdimensions.
- The evidence boundary remains conservative: watchlists are attention-universe
  evidence only, not broker-confirmed holdings, executions, orders, fund flows,
  or complete portfolio boundaries.

The prior completed wave: Investor Wiki evidence packages now have a shared
7-dimension/20-subdimension contract and validator:

- Added `collectorx.investor_wiki` as the shared FinClaw/SoulMirror evidence
  contract helper. It defines `external.investor / 7 dimensions / 20
  subdimensions`, conservative support levels, Wiki write policy checks, and
  reusable validation for `finclaw.investor_wiki_evidence.v1`.
- Added `tools/validate_investor_wiki_evidence.py` so FinClaw, CI, or a human
  reviewer can reject route-only evidence packages before distillation.
- Connected the shared dimension contract to `eastmoney-portfolio`,
  `xueqiu-investor-activity`, `china-wealth-assets`, `hk-us-brokerage`,
  `pro-terminal-usage`, and `financial-news-usage`. `ths-portfolio` and
  `investor-source-collectors` already emitted the canonical dimension tree and
  are now covered by the stricter project smoke test.
- Strong trade/asset collectors can support portfolio, execution, decision-log,
  risk-exposure, and time-preference subdimensions. Snowball, financial-news,
  and professional-terminal traces remain attention, information-source,
  workflow, or weak-process evidence and do not become standalone trade facts.
- This improves FinClaw Wiki consumability and product gating, but it does not
  claim new real-account validation.

The prior completed wave: `research-documents` now has stronger path-level
collection audit coverage for authorized research files and folders:

- `investor_sources.py collect --source research-documents --input
  <authorized-research-folder> --out-dir <dir>` records requested inputs,
  missing inputs, per-file parse results, extension coverage, skipped reasons,
  candidate/emitted counts, parser counts, content-read status, and limit
  truncation in `manifest.collection_audit`.
- The generic `filesystem` collector remains metadata-only. DOCX/PDF/XLSX/XLSM
  content extraction still requires explicit `--include-content`.
- Screenshots/images are recorded as metadata-only research candidates when they
  pass the lens rules; OCR is not performed and would require a separate adapter
  plus user authorization.
- This improves the P0 research-material path, but it does not claim broader
  private sample validation, Windows/Linux real-device validation, OCR adapter
  readiness, or Wiki backtest against real trades/reviews.

The prior completed wave: `email` now has stronger local-import source audit
coverage for authorized EML, MBOX, JSON, CSV, TSV, and ZIP email export
packages:

- `email_api.py import --input <authorized-email-export-or-folder> --out-dir
  <dir>` records `manifest.collection_audit` with requested inputs, missing
  inputs, per-file parse results, extension coverage, imported counts, skipped
  file reasons, ZIP member counts, skipped ZIP member reasons, limit truncation,
  and path-safety flags.
- IMAP `collect --out-dir` keeps the account/folder audit path, while local
  `import --out-dir` now has equivalent explainability for user-selected files
  and folders.
- Full bodies remain excluded by default and require explicit
  `--event-include-body`; attachment bodies are never written, only sanitized
  refs are retained.
- This improves the P0 email import path, but it does not claim real mailbox
  validation on the current machine because no mailbox is registered in the
  local email collector state.

The prior completed wave: `social-activity` now has stronger social-topic
coverage for authorized Weibo, Bilibili, and Xiaohongshu activity packages:

- `social_activity.py collect --input <authorized-social-activity-export-or-zip>
  --out-dir <dir>` records per-event `social_topics` plus
  `manifest.influence_surface_summary` topic counts, platform/topic counts,
  action/topic counts, and `manifest.source_audit` with requested inputs,
  missing inputs, per-file parse results, extension coverage, parsed/emitted
  counts, skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  limit truncation, and path-safety flags.
- The collector remains weak-evidence-only: it captures the user's follows,
  likes, favorites, watch history, comments, shares, creator refs, topics,
  symbols, engagement counts, and weak influence topics, while keeping
  content/comment previews capped.
- It does not scrape platform-wide content, mirror full creator profiles, collect
  platform credentials, or let social activity become a standalone investment
  conclusion.
- This improves the P2 social activity import path, but it does not claim real
  Weibo/Bilibili/Xiaohongshu account export validation, creator/domain
  allowlists, social-topic false-positive review, weak-evidence backtest, or
  Windows/macOS/Linux path validation.

The prior completed wave: `pro-terminal-usage` now has stronger workflow-topic
coverage for authorized Wind, Choice, iFinD, and Bloomberg workflow packages:

- `pro_terminal_usage.py collect --input <authorized-workflow-export-or-zip>
  --out-dir <dir>` records per-event `workflow_topics` plus
  `manifest.workflow_surface_summary` topic counts, terminal/topic counts,
  activity/topic counts, and `manifest.source_audit` with requested inputs,
  missing inputs, per-file parse results, extension coverage, parsed/emitted
  counts, skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  and path-safety flags.
- The collector remains workflow-metadata-only: it captures user workspaces,
  watchlists, searches, downloads, templates, factors, datasets, fields,
  function codes, workflow context, and research-topic metadata, while keeping
  content previews capped.
- It does not mirror vendor databases, licensed content bodies, public market
  data, reports, credentials, authorization headers, or license material.
- This improves the P2 professional terminal import path, but it does not claim
  real Wind/Choice/iFinD/Bloomberg native export validation, account-level
  validation, legal/license review, workflow-topic false-positive review, or
  Windows/macOS/Linux path validation.

The prior completed wave: `hk-us-brokerage` now has stronger account-boundary,
currency/market, and fee/tax/margin coverage for authorized read-only Futu,
Tiger, and IBKR export packages:

- `hk_us_brokerage.py collect --input <authorized-export-or-zip> --out-dir
  <dir>` records `manifest.account_boundary_summary`,
  `manifest.currency_market_summary`, `manifest.fee_tax_margin_summary`, and
  `manifest.source_audit` with requested inputs, missing inputs, per-file parse
  results, extension coverage, parsed/emitted counts, skipped file reasons, ZIP
  member counts, skipped ZIP member reasons, and path-safety flags.
- Strong brokerage facts remain numeric and unsanitized where they are the
  user's own authorized assets, positions, executions, orders, cashflows,
  dividends, FX, margin, tax, and settlement fields.
- The collector remains read-only and does not ask for passwords, collect
  cookies/tokens, place orders, cancel orders, or claim a complete brokerage
  boundary without real account validation.
- This improves the P2 HK/US brokerage import path, but it does not claim real
  Futu/Tiger/IBKR account export validation, read-only screen validation,
  complete account-boundary proof, Windows/macOS/Linux path validation, or
  broker-specific real column maps.

The prior completed wave: `financial-news-usage` now has stronger source audit
coverage for authorized finance-news usage exports, saved pages, ZIP packages,
and browser-history copies:

- `financial_news_usage.py collect --input <authorized-export-or-history-copy>
  --out-dir <dir>` records `manifest.source_audit` with requested inputs,
  missing inputs, per-file parse results, extension coverage, parsed/emitted
  counts, skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  browser-history source apps, and path-safety flags.
- Browser history remains domain-filtered to CLS, WallstreetCN, and Gelonghui
  before events are written.
- The collector remains personal-usage evidence and does not crawl or mirror
  public news content.
- This improves the P1 finance-news usage package path, but it does not claim
  real app/account adapters, subscription stores, Safari, Windows, or Linux
  validation.

The prior completed wave: `wechat-favorites` now has stronger source audit
coverage for authorized WeChat favorites and public-account article exports:

- `wechat_favorites.py collect --input <authorized-export> --out-dir <dir>`
  records `manifest.source_audit` with requested inputs, missing inputs,
  per-file parse results, extension coverage, parsed/emitted counts, skipped
  file reasons, ZIP member counts, skipped ZIP member reasons, and path-safety
  flags.
- The collector remains a generic saved-article/action source and does not
  claim investment relevance; `wechat-article-favorites` remains responsible
  for investor Wiki evidence.
- This improves the P1 public-account article package path, but it does not
  claim real WeChat favorites database, public-account read-history, Windows,
  or Linux validation.

The prior completed wave: `notes-collector` now has stronger source audit
coverage for authorized Obsidian vaults and notes exports:

- `notes_api.py obsidian/import --out-dir <dir>` records
  `manifest.source_audit` with input kind, resolved files, extension coverage,
  parsed/emitted counts, skipped file reasons, ZIP member counts, skipped ZIP
  member reasons, path-level results, and path-safety flags.
- The collector remains a generic notes source and does not claim investment
  relevance; `investment-notes` remains responsible for investor Wiki evidence.
- This improves the P1 notes package path, but it does not claim real Notion,
  Youdao, Evernote, Windows, or Linux validation.

The prior completed wave: `filesystem` now has stronger source audit coverage
for authorized local research-material roots:

- `filesystem_query.py collect --root <authorized-root> --out-dir <dir>`
  records `manifest.source_audit` with requested/resolved/missing roots,
  scanned/emitted file counts, extension coverage, skipped file/directory
  counts, skipped reasons, size policy, ignored directories, and per-root scan
  results.
- The collector remains metadata-only and does not read file bodies; investment
  relevance and explicit content extraction stay in the `research-documents`
  lens.
- This improves the local-material package path, but it does not claim real
  Windows/Linux device validation or broad private-document parser coverage.

The prior completed wave: `ticktick` and `calendar` now have stronger source
audit coverage for authorized task/calendar exports:

- Manifest output records input count, resolved file count, extension coverage,
  ZIP member/skipped-member counts, skipped-member reasons, parsed record
  count, emitted event count, supported extensions, and path-level parse
  results.
- Task time/status summary and calendar time-surface summary remain available
  for FinClaw to inspect planning usefulness.
- The generic/lens boundary remains explicit: task/calendar events enter Lake,
  but only `task-calendar-investor` can classify trading plans, research tasks,
  review reminders, and earnings events for Wiki evidence.
- This improves the local/export package path, but it does not claim real
  TickTick OAuth validation or real calendar-account validation.

The prior completed wave: `feishu` now has a CollectorX standard package path
instead of only being a migrated utility skill:

- `feishu_api.py collect --input <authorized-feishu-export> --out-dir <dir>`
  writes `lake/feishu/events.jsonl`, `manifest.json`, and `SUMMARY.md`.
- Manifest output records field coverage, Feishu surface summary, source
  audit, ZIP member/skipped-member counts, parsed/emitted counts, and
  path-level parse results.
- Existing Feishu OAuth/API helper commands remain available; the new collect
  path is a read-only local authorized export import and does not require live
  account credentials.
- The generic/lens boundary remains explicit: Feishu events enter Lake, while
  meeting, research-document, and collaboration lenses decide what becomes
  investor Wiki evidence.
- This improves the export/package path, but it does not claim real Feishu
  account/API validation or tenant-permission boundary validation.

The prior completed wave: `china-wealth-assets` now has stronger source audit
coverage for authorized fund, wealth-management, and cash-management exports:

- Manifest output records input count, resolved file count, extension coverage,
  ZIP member/skipped-member counts, parsed record count, emitted event count,
  supported extensions, and path-level parse results.
- Platform coverage, field coverage, account-boundary summary, asset-surface
  summary, currency summary, transaction-side summary, and asset value summary
  remain available for FinClaw to inspect numeric usefulness and boundary
  quality.
- The complete-asset-boundary policy remains conservative: parsed exports are
  partial authorized input until real account or read-only screen validation
  proves account scope.

The prior completed wave: `xueqiu-watchlist` and
`xueqiu-investor-activity` now have stronger package audit coverage:

- `xueqiu-investor-activity` saved HTML pages are parsed as `saved_page`
  evidence instead of failing on undefined variables.
- Both Xueqiu collectors record source audit, extension coverage, ZIP
  member/skipped-member counts, parsed record counts, emitted event counts, and
  field coverage.
- `xueqiu-investor-activity` records pagination marker fields such as `page`,
  `total`, `max_id`, `next_max_id`, `since_id`, and cursor-like fields.
- The evidence boundary remains explicit: Xueqiu is attention, network,
  opinion, saved-page, and model-portfolio evidence, not broker-confirmed trade
  evidence.
- This improves the local/export package path, but it does not claim real
  Xueqiu account or real pagination validation.

The prior completed wave: `email` now has the same standard package contract
for registered IMAP mailboxes as it already had for local authorized exports:

- `email_api.py collect --account all --out-dir <dir>` writes
  `lake/email/events.jsonl`, `manifest.json`, and `SUMMARY.md`.
- Manifest output records account/folder audit, field coverage, body policy,
  attachment policy, and the generic-to-lens evidence boundary.
- Gap events distinguish missing registered mailbox, no messages in the selected
  time window, and IMAP collection failure.
- Full bodies remain excluded by default and require explicit
  `--event-include-body`; attachment bodies are never written.
- This upgrades the real-mailbox product path, but it does not claim real
  mailbox validation on the current machine because no mailbox is registered in
  the local email collector state.

The prior completed wave: `wechat` and `wechat-investment-dialogue` now have a
standard source-to-lens path for FinClaw:

- `wechat_query.py --collect --out-dir <dir>` writes
  `lake/wechat/events.jsonl`, `manifest.json`, and `SUMMARY.md`.
- Legacy `--out <file>` compact JSON array output remains compatible.
- Manifest output records field coverage, filter policy, message surface
  summary, platform/key preconditions, source audit, and the generic-to-lens
  evidence boundary.
- `wechat-investment-dialogue` now supports optional chat/sender allow and deny
  policies, records source-policy audit fields, and emits an explicit
  `source_policy_filtered_all` gap status when a policy excludes every
  candidate.
- The generic collector still does not write investor Wiki evidence directly;
  the lens decides whether messages are investment evidence.

This upgrades the WeChat generic source and investment-dialogue lens to
`baseline+audit`, but it does not claim real-source validation on the current
Mac because authorized WeChat 4.x key/SIP preconditions are still unresolved.

## P0 Status

| Need | Current implementation | Status | Gap to reach Tonghuashun/EastMoney standard |
| --- | --- | --- | --- |
| 微信投资对话 | `wechat` generic collector + `wechat-investment-dialogue` lens classifier | `baseline+audit`; `wechat` writes a standard CollectorX package; the lens supports chat/sender source policy, source-policy audit, explicit `source_policy_filtered_all` gap status, classifier metadata, and fixture validation; real-source validation remains blocked on current Mac by missing WeChat 4.x keys/SIP enabled | Prepare authorized WeChat keys, real WeChat lake validation, user-tuned contact/group/sender allowlists, entity/time matching, backtest against trade events |
| 本地研报/财报/PDF/Excel/Markdown/截图 | `filesystem-collector` metadata-only + `research-documents` lens classifier/content reader | `baseline+audit`; macOS metadata and explicit content extraction validation passed; default-root code paths for macOS/Windows/Linux are fixture-tested; filesystem manifest records authorized-root source audit, extension coverage, skipped reasons and per-root results; research-documents manifest records requested inputs, missing inputs, per-file parse results, skipped reasons, extraction policy, parser counts, content-read counts, limit truncation, and screenshot metadata-only/no-OCR policy | Broader private PDF/XLSX/DOCX samples, optional screenshot OCR adapter review, real Windows/Linux device validation, backtest against real trades/reviews |
| 雪球投资活动 | `xueqiu-watchlist` + `xueqiu-investor-activity` | `baseline+audit`; watchlist and activity collectors support authorized ZIP packages with member provenance, path-traversal skipping, source audit, field coverage, and explicit non-broker-trade evidence policy; activity also supports XLSX/XLSM, saved HTML pages, nested Snowball-like payloads, pagination marker audit, raw sanitization, and SoulMirror sync; neither is a real account adapter | Real Xueqiu login/export discovery, real pagination coverage, watchlist/favorites/posts/comments/follows/portfolio validation, rate/terms boundary |
| 支付宝/天天基金/蛋卷/且慢/银行理财 | `china-wealth-assets` | `baseline+audit`; normalized local export/package path covers Excel/JSON/CSV/ZIP, platform inference, numeric asset fields, platform coverage, field coverage, account boundary summary, asset surface summary, currency summary, transaction-side summary, source audit, asset value summary, raw sanitization, ZIP provenance, skipped ZIP accounting, and SoulMirror sync; no real account export found yet | Per-platform export/UI adapters, real account validation, complete account-boundary proof |
| 邮件研报 | `email` generic collector + `email-research` lens classifier | `baseline+audit`; IMAP `collect --out-dir` and local EML/MBOX/JSON/CSV/TSV/ZIP `import --out-dir` both produce standard packages with account/folder audit, per-input import audit, skipped file/ZIP-member reasons, field coverage, sanitized attachment refs, body/attachment policy, generic-to-lens evidence boundary, and research-attachment filename matching; current machine has no registered mailbox, so real mailbox validation is still pending | Register mailbox through `password_env`, real mailbox validation, broader broker/IR sender backtest, no-full-body Wiki leakage review on real mailboxes |

## P1 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 飞书/钉钉/腾讯会议/企业微信会议纪要 | `meeting-artifacts` local/platform-export/ZIP collector + `feishu` authorized export package collector + `collaboration-exports` for `dingtalk`/`wecom` + `meeting-minutes` lens classifier | `baseline+audit`; macOS local meeting-file validation passed; HTML/CSV/JSON/ZIP platform-export fixture validation passed; meeting manifest reports platform coverage, field coverage, meeting surface summary, ZIP provenance, ZIP skip counts/reasons, per-input parse audit, source audit, and evidence policy; Feishu now has a CollectorX `collect` package path for messages/documents/files/folders/meetings/recordings with field coverage, surface summary, ZIP skip counts/reasons, per-input parse audit, source audit, and evidence policy; DingTalk/WeCom collaboration exports support ZIP plus equivalent audit fields; meeting-minutes lens now reports roadshow/research/IC/expert/earnings/decision/risk/follow-up surfaces, upstream collectors, source platforms, participants, meeting URLs, attachment refs, recording refs, and time coverage; platform account APIs pending | Build/port real Feishu/DingTalk/WeCom/Tencent Meeting account adapters, validate real authorized exports, participant identity normalization, attachment/recording reference validation, false-positive review |
| Obsidian/Notion/有道云/印象笔记 | `notes-collector` event package + authorized export/ZIP import + `investment-notes` lens classifier | `baseline+audit`; macOS Obsidian-style real validation passed; Youdao/Evernote/Markdown/HTML/JSON/ENEX/ZIP fixtures pass; generic notes manifest reports platform coverage, field coverage, per-input parse results, skipped reasons, ZIP provenance, path-safety boundary, content policy, and generic-collector evidence policy; investment-notes manifest/evidence now reports review/rules/checklist/valuation/research note-type surface, source-app surface, and preview/full-content surface | Validate real Notion/Youdao/Evernote account exports or APIs, user allowlists, false-positive review, Windows/Linux vault path validation |
| 日历/任务/滴答清单 | `ticktick-cli` SoulMirror YAML + AgentRunner + skill live path; `ticktick_events.py` offline export helper; `calendar-collector`; `task-calendar-investor` lens classifier | `baseline+audit`; TickTick live path now returns a dependency-light JSON snapshot through `collect_for_soulmirror.py`, fails clearly with `ticktick_auth_required` when disconnected, and keeps daemon-owned `lake/ticktick/events.jsonl` separate from offline `exports/ticktick/events.jsonl`; fake OpenAPI validation covers active/completed tasks, project names, inbox fallback, dedupe, and token non-leakage; generic calendar ICS/JSON/CSV/TSV/ZIP paths and task-calendar lens surfaces remain tested | Deploy FinClaw-managed TickTick OAuth Broker, run real account validation, validate real calendar exports/accounts, recurring tasks/timezones, backtest investment task classifier |
| 公众号/微信收藏文章 | `wechat-favorites` local file/folder/ZIP collector + `wechat-article-favorites` lens classifier | `baseline+audit`; macOS saved-article validation passed; JSON/HTML/ZIP fixtures cover favorite/read/share/saved-file actions; generic manifest reports action coverage, field coverage, article surface summary, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, source audit, content policy, and generic-collector evidence policy; wechat-article lens reports broker/fundamental/strategy/industry/valuation/portfolio/risk/macro article surfaces, action counts, source-account type counts, URL/tag/text/time coverage, and filters non-investment saved articles; real WeChat favorites adapter pending | Discover/validate real WeChat favorites and public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation, false-positive backtest |
| 华尔街见闻/财联社/格隆汇使用痕迹 | `financial-news-usage` local usage/browser-history/ZIP collector | `baseline+audit`; JSON/CSV/HTML/TXT/ZIP fixture validation passed; Chromium browser-history validation passed; manifest reports platform/action/topic coverage, field coverage, usage surface summary, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, browser-history source audit, content policy, and evidence policy; usage topics cover macro policy, market strategy, industry themes, company fundamentals, HK/US markets, risk events, trading opportunities, and portfolio alerts; real app/account adapters pending | Discover/validate CLS/WallstreetCN/Gelonghui app caches, account APIs, real subscription/alert stores, Safari/Windows/Linux browser-history paths, topic false-positive review; do not crawl public news as personal evidence |

## P2 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 富途/老虎/盈透/港美股券商 | `hk-us-brokerage` local read-only CSV/JSON/Excel/ZIP export collector | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, broker coverage, trade-surface coverage, field coverage, strong-trade surface summary, account-boundary summary, currency/market summary, fee/tax/margin summary, asset value summary, ZIP provenance, per-input parse results, skipped file/ZIP-member reasons, path-safety audit, and read-only evidence policy validation passed; no real local export found yet | Validate real Futu/Tiger/IBKR exports or read-only screens, broker-specific column maps, complete account-boundary proof, multi-currency assets, margin, tax, dividends, FX, and Windows/macOS/Linux paths |
| Choice/Wind/同花顺 iFinD 使用痕迹 | `pro-terminal-usage` local CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow collector | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, terminal coverage, activity coverage, workflow-field coverage, workflow-topic coverage, workflow surface summary, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, license policy, and evidence policy validation passed; real licensed terminal exports pending | Validate real Wind/Choice/iFinD/Bloomberg authorized workflow exports, user workspace paths, watchlists, searches, downloads, templates, datasets, fields, function codes, workflow-topic false positives, and license-safe boundaries |
| B站/微博/小红书投资内容痕迹 | `social-activity` local JSON/CSV/Excel/HTML/TXT/ZIP activity collector + `social-investment-influence` lens classifier | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, weak-evidence policy, platform coverage, action coverage, weak-signal-field coverage, social-topic coverage, influence surface summary, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, source audit, limit truncation, and preview-only content policy validation passed; real account/export adapters pending | Validate real Weibo/Bilibili/Xiaohongshu exports, watch/favorite/like/follow/comment/share surfaces, platform allowlists, creator allowlists, engagement fields, social-topic false positives, and weak-evidence backtest |

## Deep-Designed Existing Collectors

| Collector | Current status |
| --- | --- |
| `eastmoney-portfolio` | `production-candidate` on current macOS machine for unlocked account read-only asset/holding/execution/order/fund-flow capture; Windows/Linux are code-level simulations or fallback paths |
| `ths-portfolio` | `deep-beta`; strong local package and GUI snapshot design exists, but needs broader real-device validation to claim production |
| `ths-watchlist` | `baseline+audit`; authorized local export collector for same-channel watchlist/attention-universe evidence with standard 7/20 Wiki evidence package; not a strong trade, holding, order, or fund-flow collector |
| `qq` | `deep-beta`; QQ NT discovery/decrypt-ready flow exists, current machine still has LLDB/passphrase capture limitation |

## Product Rule

For a collector to be marked `production-candidate`, it needs the same product
discipline as the Tonghuashun/EastMoney work:

1. Channel responsibility: what it collects and what it must never collect.
2. Authorization story: how the user grants access without exposing secrets.
3. Cross-platform plan: macOS, Windows, Linux status stated separately.
4. Event contract: emits `collectorx.event.v1` with stable IDs.
5. Evidence package: where applicable, emits `finclaw.investor_wiki_evidence.v1`.
6. Tests: parser/unit tests and at least one fixture without private data.
7. Real validation: run against a real account/device/export and record readiness.
8. Backtest: verify events can land in investor Wiki dimensions without hallucinating reasons.
