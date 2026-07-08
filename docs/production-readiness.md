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

`pro-terminal-usage` now emits validator-safe filtered-all and no-input gap
packages:

- When user-authorized Wind, Choice, iFinD, or Bloomberg workflow records are
  fully excluded by terminal, activity, workspace, project, dataset, field, or
  keyword authorization filters, the Lake file contains one profile gap event
  instead of an empty package.
- The filtered-all gap reason is `pro_terminal_scope_policy_filtered_all`;
  readiness remains `scope_policy_filtered_all` and
  `collection_readiness.can_enter_finclaw=false`.
- Missing or unusable authorized inputs emit
  `pro_terminal_usage_authorized_input_missing` or
  `pro_terminal_usage_records_empty` with the same validator-safe event shape.
- Manifest `workflow_event_count=0` and `gap_event_count=1` keep package
  observability separate from real workspace, watchlist, search, download,
  model-template, factor, dataset, field, query, export, or lineage evidence.
- Gap events carry candidate/filter counts and reason summaries but no raw
  local input path, credential, cookie, token, license key, vendor database
  content, licensed content body, public market data mirror, or workflow fact.
- Investor Wiki evidence counts only retained terminal workflow records and
  reports zero generated events for pure gap packages.
- Fixture tests now run the shared CollectorX package validator with Investor
  Wiki evidence required for normal, no-input, and filtered-all paths.

The prior completed wave: `hk-us-brokerage` now emits validator-safe filtered-all and no-input gap
packages:

- When user-authorized Futu, Tiger, or IBKR exports are fully excluded by
  broker, account, subtype, symbol, market, currency, or keyword authorization
  filters, the Lake file contains one profile gap event instead of an empty
  package.
- The filtered-all gap reason is `brokerage_scope_policy_filtered_all`;
  readiness remains `scope_policy_filtered_all` and
  `collection_readiness.can_enter_finclaw=false`.
- Missing or unusable authorized inputs emit
  `hk_us_brokerage_authorized_input_missing` or
  `hk_us_brokerage_records_empty` with the same validator-safe event shape.
- Manifest `brokerage_event_count=0` and `gap_event_count=1` keep package
  observability separate from real asset, holding, execution, order, cashflow,
  dividend, or FX evidence.
- Gap events carry candidate/filter counts and reason summaries but no raw
  local input path, credential, token, trading password, broker business fact,
  order mutation, or investment conclusion.
- Investor Wiki evidence counts only retained brokerage records and reports
  `strong_trade_source=false` for pure gap packages.
- Fixture tests now run the shared CollectorX package validator with Investor
  Wiki evidence required for normal, no-input, and filtered-all paths.

The prior completed wave: `xueqiu-watchlist` and `xueqiu-investor-activity` now emit validator-safe
filtered-all and no-input gap packages:

- When user-authorized Xueqiu watchlist or activity inputs are fully excluded
  by authorization scope filters, the Lake file contains one profile gap event
  instead of an empty or misleading package.
- Watchlist filtered-all emits `xueqiu_watchlist_scope_policy_filtered_all`;
  activity filtered-all emits `xueqiu_scope_policy_filtered_all`. Both report
  `collection_readiness.status=scope_policy_filtered_all` and
  `collection_readiness.can_enter_finclaw=false`.
- Missing authorized inputs emit `xueqiu_watchlist_authorized_input_missing` or
  `xueqiu_authorized_input_missing` with the same validator-safe event shape.
- Manifest `watchlist_event_count=0` / `activity_event_count=0` and
  `gap_event_count=1` keep package observability separate from real attention,
  information-network, opinion, or model-portfolio evidence.
- Gap events carry candidate/filter counts and reason summaries but no raw
  local input path, credential, token, session, broker holding, execution,
  order, fund flow, or investment conclusion.
- The Xueqiu activity evidence package now counts only usable activity events,
  so collection gaps do not become Investor Wiki facts.
- Fixture tests now run the shared CollectorX package validator with Investor
  Wiki evidence required for normal, no-input, and filtered-all paths.

The prior completed wave: `ths-watchlist` now emits validator-safe filtered-all and no-input gap
packages:

- When a user-authorized Tonghuashun watchlist input is fully excluded by
  symbol, market, group, industry, tag, keyword, source, or source-platform
  scope filters, the Lake file contains one profile gap event instead of an
  empty or misleading watchlist package.
- The gap reason is `ths_watchlist_scope_policy_filtered_all`, readiness
  remains `scope_policy_filtered_all`, and
  `collection_readiness.can_enter_finclaw=false`.
- Missing authorized inputs emit `ths_watchlist_authorized_input_missing` with
  the same validator-safe event shape, so scheduler and Wiki layers can record
  the collection gap without inventing attention-universe facts.
- Manifest `watchlist_event_count=0` and `gap_event_count=1` keep package
  observability separate from real watchlist evidence.
- Gap events carry candidate/filter counts and reason summaries but no raw
  local input path, credential, token, session, holding, execution, order, fund
  flow, or investment conclusion.
- The fixture suite now runs the shared CollectorX package validator with
  Investor Wiki evidence required for normal, no-input, and filtered-all paths.

The prior completed wave: `financial-news-usage` now emits validator-safe
filtered-all gap packages:

- When a user-authorized CLS, WallstreetCN, or Gelonghui usage input is fully
  excluded by platform, action, source-app, domain, topic, or keyword scope
  filters, the Lake file contains one profile gap event instead of being empty.
- The gap reason is `financial_news_scope_policy_filtered_all`, readiness
  remains `scope_policy_filtered_all`, and
  `collection_readiness.can_enter_finclaw=false`.
- Manifest `usage_event_count=0` and `gap_event_count=1` keep the distinction
  between package observability and real personal usage evidence explicit.
- Gap events carry candidate/filter counts and reason summaries but no public
  article body, local input path, browser-history row, credential, token, or
  investment conclusion.
- Missing-input/no-record gap events now also carry a non-empty `time` value and
  pass the shared CollectorX package validator with evidence required.

The prior completed wave: `filesystem` now emits validator-safe metadata gap packages:

- When a user-authorized filesystem root yields no retained file metadata, the
  Lake file contains one profile gap event instead of being empty.
- Fully filtered runs emit `filesystem_scope_policy_filtered_all`; missing,
  empty, unsupported, hidden-only, or otherwise no-metadata runs emit
  `filesystem_no_metadata_events_collected`.
- Manifest `file_surface_summary.metadata_event_count` stays `0` for these
  gap packages, and `collection_readiness.can_enter_finclaw=false`, so the gap
  cannot be treated as a real file or research document.
- Gap events carry counts and reason summaries but no file body and no raw
  local path in the event payload.
- The generic filesystem collector remains SoulMirror-aligned: metadata-only,
  user-authorized roots only, no whole-disk claim, and no investment relevance
  claim.

The prior completed wave: `china-wealth-assets` now emits validator-safe
filtered-all gap packages:

- When a readable fund/wealth input is fully excluded by platform, account,
  subtype, product, currency, side, or keyword authorization filters, the Lake
  file contains one `china_wealth_scope_policy_filtered_all` profile gap event
  instead of being empty.
- Manifest readiness remains `scope_policy_filtered_all` with
  `can_enter_finclaw=false`, so filtered-out inputs cannot become usable asset,
  portfolio, or execution evidence.
- The gap event carries candidate, retained, filtered, and reason counts but no
  product identity, amount, transaction, credential, cookie, token, payment
  password, bank password, account mutation, or raw input path.
- No-input and filtered-all gap packages now carry non-empty event `time`
  values and pass `tools/validate_collector_package.py --collector
  china-wealth-assets`.
- Investor Wiki evidence keeps all 20 subdimensions at `support_level=none`
  for filtered-all packages.

The prior completed wave: `eastmoney-portfolio` now supports event-level
authorization scope filters before production-candidate strong trading
evidence enters the Lake:

- `eastmoney_query.py --collect-local` accepts event-kind, symbol, account,
  source, and keyword allow/deny filters.
- Manifest `collection_audit.eastmoney_scope_policy` records configured
  filters, candidate event count, retained event count, filtered event count,
  reason counts, and filtered-all state.
- If every candidate event is filtered by policy, the package emits an
  `eastmoney_scope_policy_filtered_all` gap event, readiness reports
  `scope_policy_filtered_all`, and `can_enter_finclaw=false`.
- `eastmoney_portfolio_boundary_proof.authorization_scope_boundary` gives
  FinClaw a stable place to inspect the exact user authorization boundary
  before assets, holdings, executions, orders, fund flows, watchlists, notes,
  and recent-view evidence enter the investor Wiki pipeline.
- The collector remains read-only and preserves exact retained business
  numbers. No trading password, cookie, token, session, device fingerprint,
  order placement, order cancellation, transfer, or raw network payload is
  collected.

The prior completed wave: `filesystem` now supports explicit metadata
authorization scope filters before local file metadata enters the Lake:

- `filesystem_query.py collect` accepts extension, path, file-name, directory,
  and metadata-keyword allow/deny filters.
- Manifest `source_audit.filesystem_scope_policy` records configured filters,
  candidate file count, retained event count, filtered file count, reason
  counts, and whether every candidate was excluded by policy.
- As of version `0.3.2`, filtered-all and no-metadata packages emit one profile
  gap event instead of an empty `events.jsonl`, while readiness still prevents
  those packages from entering `research-documents` as usable file metadata.
- `filesystem_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the exact metadata authorization boundary before
  filesystem events feed `research-documents`.
- The generic filesystem collector remains metadata-only: no file body reading,
  no whole-disk claim, and no investment relevance claim.

The prior completed wave: `email-research` now supports explicit mailbox
research authorization scope filters before generic email Lake events become
Investor Wiki research evidence:

- `investor_sources.py collect --source email-research` accepts sender,
  sender-domain, folder, mailbox, subject, attachment filename, email-surface,
  and keyword allow/deny filters.
- Manifest `collection_audit.email_research_scope_policy` records configured
  filters, filtered candidate count, reason counts, and filtered-all state.
- If every candidate email-research record is filtered by policy, readiness
  reports `scope_policy_filtered_all` and the lens emits an explicit
  `email_research_scope_policy_filtered_all` gap.
- `email_research_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the exact mailbox-research authorization boundary
  before evidence enters the Investor Wiki.

The prior completed wave: `email` now supports explicit email authorization
scope filters before IMAP, local-scan, or local-import messages enter the Lake:

- `email_api.py collect` and `email_api.py import` accept mailbox, folder,
  sender, sender-domain, recipient, subject, attachment-name, and keyword
  allow/deny filters.
- Manifest `collection_audit.email_scope_policy` records configured filters,
  candidate email count, retained count, filtered count, reason counts, and
  whether every candidate was excluded by policy.
- If every candidate email is filtered by policy, readiness reports
  `scope_policy_filtered_all` and the package emits an
  `email_scope_policy_filtered_all` gap instead of pretending the mailbox or
  export was empty.
- `mailbox_boundary_proof.authorization_scope_boundary` gives FinClaw a stable
  place to inspect the exact mailbox/file/folder/person/topic authorization
  boundary before email evidence is routed into `email-research`.

The prior completed wave: `research-documents` now supports explicit document authorization scope filters
before authorized research files enter the investor evidence package:

- `investor_sources.py collect --source research-documents` accepts extension,
  path, file-name, parser, research-surface, and keyword allow/deny filters.
- Manifest `collection_audit.document_scope_policy` records configured filters,
  candidate record counts, filtered record counts, filter reason counts, and
  whether every candidate was excluded by policy.
- If every candidate research document record is filtered by policy, readiness
  reports `source_policy_filtered_all` and the evidence package remains empty.
- `research_corpus_boundary_proof.authorization_scope_boundary` gives FinClaw
  a stable place to inspect the exact user authorization boundary before using
  research materials in the investor Wiki pipeline.

The prior completed wave: `wechat-favorites` now supports explicit saved-article scope-policy filters
before generic WeChat favorites and public-account article records enter the
Lake/package output:

- WeChat favorites imports accept source-account, source-account-type, action,
  tag, URL-domain, and keyword allow/deny filters.
- Manifest `source_audit.wechat_favorites_scope_policy` records configured
  filters, candidate record counts, filtered record counts, filter reason
  counts, and `policy_does_not_assert_investment_relevance=true`.
- If every candidate favorite/article record is filtered by scope policy,
  readiness reports `scope_policy_filtered_all`.
- This tightens the generic-to-lens boundary: `wechat-favorites` narrows the
  authorized reading/source scope, while `wechat-article-favorites` still
  performs investment relevance classification.

The prior completed wave: `meeting-artifacts` and `collaboration-exports` now support explicit
meeting/collaboration scope-policy filters before generic meeting and
collaboration records enter the Lake/package output:

- Meeting artifact imports accept source-platform, participant/organizer, and
  keyword allow/deny filters.
- DingTalk/WeCom collaboration imports accept source-platform, record-kind,
  chat/conversation, sender/receiver, participant, and keyword allow/deny
  filters.
- Manifest `source_audit.meeting_scope_policy` and
  `source_audit.collaboration_scope_policy` record configured filters,
  candidate record counts, filtered record counts, filter reason counts, and
  `policy_does_not_assert_investment_relevance=true`.
- If every candidate meeting/collaboration record is filtered by scope policy,
  readiness reports `scope_policy_filtered_all`.
- This tightens the generic-to-lens boundary: meeting/collaboration collectors
  narrow authorized workplace scope, while `meeting-minutes` and later lenses
  still perform investment relevance classification.

The prior completed wave: `ticktick_events.py` and `calendar-collector` now support explicit task/calendar
scope-policy filters before planning evidence enters the Lake/package output:

- Offline TickTick/Dida authorized imports accept source-app, project/list, tag,
  and keyword allow/deny filters.
- Calendar imports accept source-platform, calendar name, attendee/organizer,
  and keyword allow/deny filters.
- Manifest `source_audit.task_scope_policy` and
  `source_audit.calendar_scope_policy` record configured filters, candidate
  record counts, filtered record counts, filter reason counts, and
  `policy_does_not_assert_investment_relevance=true`.
- If every candidate task/calendar record is filtered by scope policy,
  readiness reports `scope_policy_filtered_all`.
- This tightens the generic-to-lens boundary: task/calendar collectors narrow
  authorized planning scope, while `task-calendar-investor` still performs
  investment relevance classification.

The prior completed wave: `notes-collector` now supports explicit source-app/path/tag authorization
filters before generic note events enter the Lake:

- `notes_api.py import --allow-source-app ... --allow-path ... --allow-tag ...`
  keeps only the user-authorized note scope, such as a selected Notion export
  folder or investment tag.
- `notes_api.py obsidian` accepts the same filters for local vault collection.
- Manifest `source_audit.note_source_policy` records the configured allow/deny
  filters, candidate note count, filtered note count, filter reason counts, and
  `policy_does_not_assert_investment_relevance=true`.
- If all candidate notes are filtered by policy, collection readiness reports
  `source_policy_filtered_all` instead of pretending there were no notes.
- This tightens the generic-to-lens boundary: `notes` narrows authorized scope,
  while `investment-notes` still performs investment relevance classification.

The prior completed wave: `hk-us-brokerage` now supports explicit
authorization scope filters for user-owned read-only brokerage records:

- `skills/hk-us-brokerage/scripts/hk_us_brokerage.py collect` accepts
  broker/account/subtype/symbol/market/currency/keyword allow and deny filters.
- Manifest `source_audit.brokerage_scope_policy` records the configured
  filters, candidate record count, filtered record count, filter reason counts,
  and whether every candidate was excluded by policy.
- When all candidate records are excluded, collection readiness reports
  `scope_policy_filtered_all` and no synthetic gap event is written.
- `brokerage_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the user's authorization boundary before using strong
  trade events in the investor Wiki pipeline.
- Existing CSV/JSON/Excel/ZIP, nested statements, source audit, account
  boundary, cashflow, income, order execution, and read-only evidence
  validations still pass.

The prior completed wave: `financial-news-usage` now supports explicit
authorization scope filters for user-owned finance-news usage traces:

- `skills/financial-news-usage/scripts/financial_news_usage.py collect` accepts
  platform/action/source-app/domain/topic/keyword allow and deny filters.
- Manifest `source_audit.financial_news_scope_policy` records the configured
  filters, candidate record count, filtered record count, filter reason counts,
  and whether every candidate was excluded by policy.
- As of version `0.2.9`, when all candidate records are excluded, collection
  readiness reports `scope_policy_filtered_all` and the package emits one
  `financial_news_scope_policy_filtered_all` profile gap event.
- `usage_boundary_proof.authorization_scope_boundary` gives FinClaw a stable
  place to inspect the user's authorization boundary before using events in the
  investor Wiki pipeline.
- Existing JSON/CSV/HTML/TXT/ZIP, Chromium, Safari, and ZIP-packaged history
  validations still pass.

The prior completed wave: `financial-news-usage` now supports direct Safari `History.db` and ZIP-packaged
browser-history members in addition to local usage exports, saved pages, and
Chromium history copies:

- `skills/financial-news-usage/scripts/financial_news_usage.py collect --input
  <authorized-folder-or-zip> --out-dir <dir>` can parse copied Safari
  `History.db` files and `archive.zip::Safari/History.db` members.
- Browser-history events remain domain-filtered to CLS, WallstreetCN, and
  Gelonghui before entering the Lake, so unrelated browser history is not
  emitted as personal investor evidence.
- Manifest `source_audit` and `usage_boundary_proof.source_artifact_boundary`
  now include `browser_history_source_app_counts` alongside input/event counts
  and source apps.
- Safari records preserve `visit_count` when present and map
  `load_successful` into behavior-level transition status.
- ZIP provenance is kept as `raw_ref.path=<archive>::<member>`,
  `source_archive`, and `archive_member`; temporary extraction paths are not
  exposed in events.

The latest completed wave: `china-wealth-assets` now exposes explicit
authorization scope-policy boundaries:

- `china_wealth.py collect` accepts platform, account, subtype, product code,
  product name, currency, side, and keyword allow/deny filters before fund,
  wealth, cash-management, PDF, HAR, or ZIP records enter the Lake.
- Manifest `collection_audit` records configured filters, candidate record
  count, retained/emitted count, filtered count, reason counts, and
  `china_wealth_scope_policy_filtered_all`.
- As of version `0.4.7`, filtered-all runs produce one
  `china_wealth_scope_policy_filtered_all` profile gap event with
  `scope_policy_filtered_all` readiness, so FinClaw can ingest a traceable
  authorization-boundary package instead of an empty Lake file.
- `asset_boundary_proof.authorization_scope_boundary` exposes the same policy
  boundary to FinClaw so partial asset facts remain user-authorized and do not
  become complete asset-boundary claims.
- This improves P0 fund/wealth asset authorization control, but it does not
  claim real Alipay/Tiantian/Danjuan/Qieman/bank account validation.

The prior completed wave: `china-wealth-assets` now supports user-authorized PDF fund and wealth
statements in addition to CSV/Excel/HTML/HAR/ZIP inputs:

- `skills/china-wealth-assets/scripts/china_wealth.py collect --input
  <authorized-statement.pdf> --out-dir <dir>` parses local PDF statements with
  `pdfplumber`.
- PDF table extraction can emit exact numeric asset snapshots, fund holdings,
  bank-wealth holdings, and transaction records when the statement exposes
  structured columns.
- Manifest `collection_audit` records PDF parser availability, file count,
  page count, table count, table-record count, text-record count, parse errors,
  and keeps `pdf_text_ocr_used=false`.
- ZIP packages can include PDF statements and keep `archive.zip::member`
  provenance.
- Asset-boundary proof remains conservative: PDF statements are authorized
  partial inputs and do not create a complete asset-boundary claim without
  real account/read-only screen validation.

The prior completed wave: `ths-watchlist` now has an authorized local-scan path in addition to export
imports:

- `skills/ths-watchlist/scripts/ths_watchlist.py collect --local-scan` can scan
  a user-authorized Tonghuashun root for likely watchlist files.
- `--platform auto|mac|windows|linux|generic`, `--container-root`, and
  `--probe-export` give FinClaw a product-safe preflight and execution path.
- The scan limits itself to likely watchlist filenames and supported local
  formats, then still applies normal symbol filtering before emitting events.
- Manifest `collection_audit` records local-scan platform, roots, candidate
  files, candidate-selection rules, and local-scan event counts.
- `ths_watchlist_boundary_proof.local_scan_boundary` keeps the collector inside
  the attention-universe role and explicitly avoids holdings, executions,
  orders, fund flows, credentials, cookies, tokens, and sessions.
- The FinClaw catalog and invocation contract now prefer an authorized local
  scan root, with `--input` exports remaining as a fallback path.
- This reduces manual export dependence for a P0 source, but it does not claim
  real Tonghuashun local-store validation or complete attention-universe
  coverage until real device samples are tested.

The prior completed wave: FinClaw now has a catalog helper readiness doctor, runbook, compact batch
manifest, and dry-run-first batch runner for product-side discovery and
invocation planning:

- `tools/finclaw_catalog.py list/show/plan/doctor/runbook/batch-manifest` merges
  `collectors/finclaw-investor-catalog.json` with
  `collectors/finclaw-invocation-contracts.json`.
- `tools/run_finclaw_batch.py` consumes an existing batch manifest or builds one
  from the catalog filters. It defaults to dry-run reporting and requires
  `--execute` before running collector commands.
- Product runners can list collectors, inspect authorization/preflight details,
  and render a collector command with placeholder replacement before execution.
- `plan` and `doctor` now include both a display `command` and executable
  `argv`, so FinClaw can run collectors without shell string reparsing.
- `plan` and `doctor` also include `package_validation.argv`, so FinClaw can run
  the post-collection package gate without rebuilding validator commands.
- `doctor --out-dir-root ... --json` produces a batch readiness matrix for
  setup screens and collection-run planning.
- `runbook --out-dir-root ... --json` groups the same catalog items into
  executable product stages: ready collectors, ready lenses, upstream-Lake
  waits, user-input waits, and SoulMirror-runner handoff.
- `batch-manifest --out-dir-root ... --json` emits ordered `ready_steps` with
  executable `argv`, dependency ids, output directories, expected Lake
  `events.jsonl` paths, and post-run validation commands; blocked entries move
  to `blocked_steps` with the same `next_action` contract.
- The batch runner executes only ready steps, runs post-run package validation
  after successful collector commands, and stops on the first collector or
  validation failure unless `--continue-on-error` is supplied. A successful
  collector command without a ready validation command is still treated as a
  validation failure.
- Runbook auto-links deterministic `<upstream-id-events-jsonl>` lens inputs from
  ready upstream package paths, while ambiguous inputs still remain explicit
  user/product choices.
- `plan --require-ready` exits with status `2` when a command is not ready for
  ordinary execution, while still returning JSON the product can inspect.
- Plan and doctor JSON now report `next_action` and `blocked_reason`, so FinClaw
  can route to ordinary command execution, missing-precondition collection,
  upstream Lake collection, or the SoulMirror runner.
- The plan output reports unresolved placeholders and `runner=soulmirror` for
  SoulMirror-owned collectors such as TickTick, preventing accidental treatment
  as a normal shell command.
- `tools/test_finclaw_catalog.py` and project validation now cover catalog
  listing, lens upstream contracts, command placeholder replacement, safe argv
  rendering, package-validation argv rendering, upstream auto-linking,
  batch-manifest execution output, batch-runner dry-run/execute/failure
  behavior, and ready-to-run gate/doctor/runbook handling.
- This improves FinClaw product-call ergonomics, but it does not claim new
  real-account validation for any collector.

The prior completed wave: FinClaw catalog coverage and invocation contracts are now part of the project validation gate:

- `ths-watchlist` is now a first-class FinClaw investor catalog entry instead
  of only a YAML/README-described collector.
- The `doubao` generic YAML is explicitly excluded from the FinClaw investor
  catalog until investor-specific scope, evidence boundaries, and product
  routing are reviewed.
- `collectors/finclaw-invocation-contracts.json` now gives each catalog entry a
  machine-readable authorization mode, product surface, evidence role,
  preflight, user step, failure state, and lens upstream requirements where
  applicable.
- `tools/validate_project.py` now fails if a collector YAML is neither in the
  investor catalog nor in explicit exclusions, or if any catalog entry lacks a
  matching invocation contract.
- This improves FinClaw call safety and user-facing precondition handling, but
  it does not claim new real-account validation for any collector.

The latest completed wave: `xueqiu-watchlist` and
`xueqiu-investor-activity` now expose explicit authorization scope-policy
boundaries:

- `xueqiu-watchlist` accepts symbol, market, group, industry, tag, and keyword
  allow/deny filters before watchlist records enter the Lake.
- `xueqiu-investor-activity` accepts activity, source-surface, source-app,
  domain, symbol, author, and keyword allow/deny filters before Xueqiu activity,
  HAR response, saved-page, or browser-history records enter the Lake.
- Manifest audits now report configured filters, candidate counts, retained
  counts, filtered counts, reason counts, and filtered-all status.
- Filtered-all runs produce explicit `scope_policy_filtered_all` readiness
  instead of looking like empty successful imports.
- Watchlist and activity boundary proof now expose the authorization scope
  boundary so FinClaw can route attention evidence without confusing it with
  broker-confirmed trade facts.
- This improves user authorization control and Wiki routing, but it does not
  claim real Xueqiu account adapter or real pagination validation.

The prior completed wave: FinClaw skill metadata is now part of the project validation gate:

- Every skill referenced by `collectors/finclaw-investor-catalog.json` must have
  both `.collectorx.json` and `VERSION`.
- `.collectorx.json.version` must exactly match the local `VERSION` file, and
  the metadata must include a stable `slug` or `collector` plus a non-empty
  description.
- The gate is wired into `tools/validate_project.py`, so `bash
  test_collectors.sh` now catches catalog-callable skills whose GitHub metadata
  has drifted from the code.
- Existing metadata drift was corrected for `calendar-collector`,
  `china-wealth-assets`, `email-collector`, `notes-collector`,
  `xueqiu-watchlist`, and `xueqiu-investor-activity`; missing metadata was
  added for `wechat-export` and `ticktick-cli`.
- This improves FinClaw discovery and release safety, but it does not claim new
  real-account validation for any collector.

The prior completed wave: `xueqiu-investor-activity` now supports user-authorized copied browser history:

- Chromium `History`, Safari `History.db`, `.sqlite`, `.sqlite3`, and `.db`
  inputs are parsed read-only when the user provides a copy.
- Browser-history parsing is domain-filtered to `xueqiu.com` and subdomains;
  unrelated browsing records are not emitted.
- Events preserve source browser app, URL, title, visit time, visit count,
  typed count, and browser transition type when present.
- Manifest and Wiki evidence now include `browser_history_boundary` and
  `browser_history_event_count`, while still marking complete account activity
  and broker trade claims as false.
- Fixture validation covers a direct `History` file, a ZIP package containing
  an extensionless browser history member, spaced file paths, Xueqiu subdomains,
  and an unrelated-domain exclusion.

The prior completed wave: `xueqiu-investor-activity` now carries explicit activity-boundary and pagination proof:

- `manifest.activity_boundary_proof` and the Investor Wiki evidence coverage
  summary now report whether expected Snowball activity surfaces were observed:
  watchlist, followed users, followed portfolios, portfolio activity, comments,
  favorites, posts, and saved pages.
- Per-surface proof levels distinguish usable, thin, raw-presence, missing
  activity evidence.
- `pagination_completeness` reports pagination markers, HAR endpoints, limit
  truncation, and whether the run is only a partial export. It never claims a
  complete Snowball timeline without real account pagination validation.
- Package summaries now surface activity-boundary proof and pagination
  completeness levels.
- Fixture validation covers broad all-surface coverage, HAR pagination markers,
  evidence propagation, package summaries, and non-trade boundaries.
- This improves P0 attention-network evidence quality, but it does not claim a
  one-click Snowball account adapter or complete timeline validation.

The prior completed wave: `china-wealth-assets` now carries explicit partial asset-boundary proof:

- `manifest.asset_boundary_proof` and the Investor Wiki evidence coverage
  summary now report account-level proof strength for each platform/account.
- The proof checks whether an authorized input has known platform identity,
  named account refs, asset snapshots, holding surfaces, transaction surfaces,
  and numeric value fields.
- Account proof levels are conservative:
  `strong_partial_account_boundary`, `medium_partial_account_boundary`,
  `weak_partial_account_boundary`, or `no_account_evidence`.
- Overall proof remains partial, and `complete_asset_boundary_claimed` stays
  false until real account/read-only-screen validation proves account scope.
- Fixture validation covers all expected platforms, account-level proof
  classification, missing account requirements, evidence propagation, and gap
  package behavior.
- This improves P0 fund/wealth asset boundary quality, but it does not claim
  one-click real Alipay/Tiantian/Danjuan/Qieman/bank account validation.

The prior completed wave: `calendar` and `task-calendar-investor` now carry stronger time-quality evidence:

- `calendar-collector` events now include whether a schedule has a complete time
  range, validated time order, duration minutes, and multi-day status.
- `manifest.time_surface_summary` now reports missing start/end fields,
  duration coverage, min/max/average duration, all-day and multi-day counts,
  invalid time ranges, missing meeting links/reminders, and same-calendar
  conflict pairs without exposing event titles in the conflict sample.
- `task-calendar-investor` lens surface summaries and
  `manifest.task_calendar_boundary_proof` now preserve duration, multi-day,
  invalid-time, upstream source, candidate/matched/filtered, and no-complete
  task/calendar boundary fields so FinClaw can inspect planning evidence
  quality before Wiki distillation.
- Fixture validation covers normal ICS duration output, CSV overlap detection,
  invalid time ranges, cross-night schedules, and lens surface propagation.
- This improves P1 planning and review evidence quality, but it does not claim
  real Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting account
  validation.

The prior completed wave: `ticktick` and `task-calendar-investor` now carry task checklist and recurrence evidence:

- `collect_for_soulmirror.py` still returns a SoulMirror-compatible JSON array,
  and now exposes timezone, repeat, reminders, checklist totals, and checklist
  completed counts at the snapshot top level while preserving raw task fields
  in `data`.
- `ticktick_events.py` offline authorized imports now normalize task
  start/due/completed times, preserve all-day/timezone fields, derive repeat
  frequency, and expose checklist items plus total/completed/pending counts and
  completion rate.
- `manifest.time_status_summary` reports task time-quality, repeat-frequency
  counts, timezone coverage, checklist totals, completed/pending checklist
  items, and average checklist completion rate.
- `task-calendar-investor` lens surface summaries and
  `manifest.task_calendar_boundary_proof.task_structure_boundary` propagate
  checklist execution structure into Investor Wiki evidence without claiming a
  complete task list.
- This improves P1 execution-plan evidence quality, but it does not claim real
  TickTick OAuth validation or real mixed-corpus false-positive backtesting.

The prior completed wave: `qq` now has a standard CollectorX package path:

- `qq_query.py --db-dir <authorized-qq-db-dir> collect --out-dir <out-dir>`
  writes `lake/qq/events.jsonl`, `manifest.json`, `qq.collect.json`, and
  `SUMMARY.md`.
- The manifest records filter policy, owner-UIN presence without leaking the
  UIN, field coverage, source audit, communication-surface counts, and the
  generic-to-lens evidence boundary.
- If no readable QQ database exists, the collector writes an explicit gap
  package with `collection_readiness.status=needs_readable_qq_db` instead of
  returning an ambiguous empty result.
- Fixture validation covers normal package output, package-gate validation, and
  missing-database gap packages.
- This improves QQ's FinClaw-callable product path, but it does not claim real
  decrypted QQ NT message validation on the current machine because local
  passphrase capture remains blocked by the LLDB/SIP precondition.

The prior completed wave: FinClaw catalog validation now checks runnable invocation contracts:

- `tools/validate_project.py` now verifies that each
  `collectors/finclaw-investor-catalog.json` entry points to the correct
  collector YAML category, an existing skill directory, and existing Python
  script paths.
- Lens catalog entries must include `--source <collector-id>` so the product
  cannot accidentally run the wrong lens profile.
- Non-SoulMirror entries must declare a concrete `<out-dir>` target; SoulMirror
  entries must use `apiVersion: soulmirror/v1` in their collector YAML.
- The new gate caught and fixed the historical `qq` catalog command:
  `--db-dir` is a top-level `qq_query.py` option.
- This improves product-entry safety; QQ's full standard package path is now
  covered by the later QQ package wave above.

The latest completed wave: `ths-portfolio` now has explicit filtered-all gap
events for authorization-scope package ingestion:

- `ths-portfolio` is upgraded to `0.5.2`.
- If a readable Tonghuashun input is fully outside the user's event-kind,
  symbol, account, source, or keyword authorization scope, the package writes
  one `ths_scope_policy_filtered_all` profile gap event instead of an empty
  `events.jsonl`.
- The manifest still reports
  `collection_readiness.status=scope_policy_filtered_all` and
  `can_enter_finclaw=false`, so FinClaw can track the boundary without treating
  it as successful user fact capture.
- The gap event carries only policy counts and reason counts; it does not write
  filtered trade, holding, order, execution, cashflow, metadata sidecar, GUI
  snapshot sidecar, credential, or mutation facts.
- This improves package ingestion safety, but does not promote Tonghuashun
  beyond `deep-beta` until broader real-device and multi-account validation is
  complete.

The prior completed wave: `ticktick-cli` now has a SoulMirror-aligned live collector path:

- `collectors/generic/ticktick.yaml` is aligned to the SoulMirror
  YAML + AgentRunner + skill contract.
- The live collector entrypoint is `collect_for_soulmirror.py`, which returns a
  JSON array snapshot and leaves Lake writes, diffing, and state to the
  SoulMirror daemon.
- Missing auth now fails with `ticktick_auth_required` instead of returning an
  empty snapshot.
- The AgentRunner prompt now explicitly separates authorization from
  collection: collection must not start OAuth or write an auth-error object into
  the snapshot/result file.
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

- `research-documents` now has an explicit optional image OCR path:
  `--include-image-ocr` runs a local `tesseract` adapter only when the user
  authorizes it separately from `--include-content`.
- Screenshot/image runs record OCR engine availability, OCR status counts,
  image OCR event counts, and per-file OCR/metadata-only policy in
  `manifest.collection_audit`.
- `investor_sources.py collect --source research-documents --input
  <authorized-research-folder> --out-dir <dir>` records requested inputs,
  missing inputs, per-file parse results, extension coverage, skipped reasons,
  candidate/emitted counts, parser counts, content-read status, and limit
  truncation in `manifest.collection_audit`.
- The generic `filesystem` collector remains metadata-only. XLS/XLSX/PPTX/DOCX/PDF
  content extraction still requires explicit `--include-content`.
- Screenshots/images are still metadata-only by default; OCR requires
  `--include-image-ocr` and a local `tesseract` engine, and failures degrade to
  audited metadata-only output.
- This improves the P0 research-material path, but it does not claim broader
  private sample validation, Windows/Linux real-device validation, OCR quality
  across real Chinese screenshots, or Wiki backtest against real
  trades/reviews.

The latest completed wave: `research-documents` now exposes audited binary-XLS boundaries:

- Legacy `.xls` parser results are now split in `parser_counts` instead of
  being collapsed into one label: XML Spreadsheet, HTML table, delimited text,
  plain text, renamed OOXML, and binary BIFF via `xlrd`.
- `manifest.collection_audit.content_extraction_policy` reports whether binary
  BIFF `.xls` parsing is available on the current machine.
- When binary BIFF `.xls` content is authorized but `xlrd` is unavailable, the
  event records `content_extract.status: extract_failed`, parser `xlrd-biff`,
  and error `xlrd_unavailable_for_binary_xls` instead of fabricating content.
- Fixture validation covers the no-`xlrd` failure path with package validation.

The prior completed wave: `email` now has stronger local-import source audit
coverage for authorized EML, Apple Mail EMLX, Maildir, MBOX, JSON, CSV, TSV, and ZIP email export
packages:

- `email_api.py import --input <authorized-email-export-or-folder> --out-dir
  <dir>` records `manifest.collection_audit` with requested inputs, missing
  inputs, per-file parse results, extension coverage, imported counts, skipped
  file reasons, ZIP member counts, skipped ZIP member reasons, limit truncation,
  and path-safety flags.
- Apple Mail `.emlx` files and Maildir `cur/` / `new/` message files are now
  accepted in local folders and ZIP packages. Maildir detection is constrained
  to RFC822-like files so ordinary extensionless notes are skipped.
- IMAP `collect --out-dir` keeps the account/folder audit path, while local
  `import --out-dir` now has equivalent explainability for user-selected files
  and folders.
- Full bodies remain excluded by default and require explicit
  `--event-include-body`; attachment bodies are never written, only sanitized
  refs are retained.
- This improves the P0 email import path, but it does not claim real mailbox
  validation on the current machine because no mailbox is registered in the
  local email collector state.

The prior completed wave: `social-activity` now has authorization
scope-policy audit for weak social activity packages:

- `social_activity.py collect` accepts platform, action, source-app, domain,
  creator, social-topic, and keyword allow/deny filters before writing Lake
  output.
- `manifest.source_audit.social_activity_scope_policy` records the configured
  policy, candidate record count, filtered record count, reason counts, and
  `social_activity_scope_policy_filtered_all`.
- `manifest.social_activity_boundary_proof.authorization_scope_boundary` gives
  FinClaw one stable field for checking whether the user's social-source
  authorization narrowed the weak influence evidence.
- If all candidate records are outside the authorized scope, readiness reports
  `scope_policy_filtered_all` and no synthetic success/gap event is written.
- This improves user-authorization control for P2 social activity imports, but
  it does not claim real Weibo/Bilibili/Xiaohongshu account exports, real
  browser path validation, default creator/domain allowlists, topic
  false-positive review, or weak-evidence backtest.

The prior completed wave: `social-activity` now accepts user-authorized
browser-history copies for Weibo, Bilibili, and Xiaohongshu weak influence
signals:

- `social_activity.py collect --input <authorized-browser-history-copy>
  --out-dir <dir>` recognizes Chromium/Safari history stores and filters rows
  to configured social-platform domains before emitting events.
- Events preserve `source_app`, `visit_count`, `typed_count`, and
  `transition_type` while remaining `weak_influence_signal` and
  `requires_corroboration: true`.
- `manifest.source_audit` reports browser-history input counts, event counts,
  and source apps; `manifest.influence_surface_summary` reports visit totals
  and browser transition distribution.
- `social_activity_boundary_proof` exposes browser-history source counts and
  domain-filtering boundaries, and keeps false claims explicit: no unrelated
  browser history collection, no platform-wide scrape, no full creator profile,
  and no standalone investment conclusion.
- This improves the P2 social import path, but does not claim real
  Weibo/Bilibili/Xiaohongshu account exports, real browser path validation,
  creator allowlists, topic false-positive review, or weak-evidence backtest.

The prior completed wave: `social-activity` and `social-investment-influence`
now have explicit weak-evidence boundary proofs:

- `manifest.social_activity_boundary_proof` gives FinClaw one gate for
  authorized social-activity input presence, Weibo/Bilibili/Xiaohongshu
  platform coverage, action coverage, weak-signal fields, social-topic coverage,
  influence surfaces, source audit counts, content-preview policy, and required
  lens flow.
- `manifest.social_influence_boundary_proof` and evidence
  `source_boundary_proof_summary.social-investment-influence` tell SoulMirror
  that filtered social influence records remain weak attention evidence and
  require stronger trade/research/note/meeting corroboration.
- False claims remain explicit: no standalone investment conclusion, no
  complete social activity history, no real account validation, no platform-wide
  scrape, no full creator profile scrape, no full content mirror, no private
  platform credentials, and no direct Wiki write.
- This improves FinClaw gating for P2 social influence packages, but still does
  not replace real Weibo/Bilibili/Xiaohongshu export validation, creator/domain
  allowlists, topic false-positive review, or weak-evidence backtesting.

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

The prior completed wave: `pro-terminal-usage` now has authorization
scope-policy audit for professional terminal workflow packages:

- `pro_terminal_usage.py collect` accepts terminal, activity, workspace,
  project, dataset, field, and keyword allow/deny filters before writing Lake
  output.
- `manifest.source_audit.pro_terminal_scope_policy` records the configured
  policy, candidate record count, filtered record count, reason counts, and
  `pro_terminal_scope_policy_filtered_all`.
- `manifest.workflow_boundary_proof.authorization_scope_boundary` gives
  FinClaw one stable field for checking whether the user's terminal workflow
  authorization narrowed the imported evidence.
- As of version `0.2.8`, if all candidate records are outside the authorized
  scope, readiness reports `scope_policy_filtered_all` and the package emits
  one validator-safe `pro_terminal_scope_policy_filtered_all` profile gap
  event instead of an empty Lake file.
- This improves user-authorization control for P2 professional-terminal
  imports, but it does not claim real Wind/Choice/iFinD/Bloomberg native export
  validation, account-level validation, legal/license review, workflow-topic
  false-positive review, or Windows/macOS/Linux path validation.

The prior completed wave: `pro-terminal-usage` now has workflow-intensity and
lineage surfaces for authorized Wind, Choice, iFinD, and Bloomberg workflow
packages:

- Per-event workflow metadata now includes query terms, query/filter
  parameters, export paths, row counts, workspace IDs, template IDs,
  securities/fields/datasets/factors counts, watchlist sizes, and stable
  lineage refs.
- `manifest.workflow_intensity_summary` summarizes query terms, parameter keys,
  export row totals, workspace/template IDs, function codes, datasets, fields,
  factors, templates, workspaces, download formats, and per-activity quantity
  totals.
- `manifest.workflow_boundary_proof.workflow_intensity_boundary` lets FinClaw
  check whether query terms, parameters, export paths, row counts, symbol refs,
  field refs, dataset refs, factor refs, and watchlist sizes are available
  before using the evidence for the investor avatar.
- This improves P2 professional-terminal evidence quality, but it still does
  not claim complete terminal history, vendor database mirroring, licensed
  content mirroring, legal/license review, or real Wind/Choice/iFinD/Bloomberg
  account validation.

The prior completed wave: `pro-terminal-usage` now has unified workflow-boundary
proof for authorized Wind, Choice, iFinD, and Bloomberg workflow packages:

- `manifest.workflow_boundary_proof` gives FinClaw one gate for authorized
  input presence, terminal coverage, activity coverage, workflow-field coverage,
  workflow-topic coverage, workflow surfaces, source audit counts, license
  safety, and Investor Wiki flow.
- The proof keeps personal workflow metadata usable for the investor avatar:
  workspaces, watchlists, searches, downloads, exports, templates, models,
  factors, datasets, fields, function codes, symbols, projects, and topics.
- False claims remain explicit: no complete terminal usage history, no real
  licensed-account validation, no vendor database mirror, no licensed content
  body mirror, no public market data mirror, no credentials, no license keys,
  no order mutation, and no direct Wiki write.
- This improves FinClaw gating for P2 professional terminal packages, but still
  does not replace real Wind/Choice/iFinD/Bloomberg account/export validation
  or legal/license review.

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

The prior completed wave: `hk-us-brokerage` now has unified brokerage-boundary
proof for authorized read-only Futu, Tiger, and IBKR export packages:

- `manifest.brokerage_boundary_proof` gives FinClaw one gate for authorized
  input presence, broker coverage, strong trade surfaces, recommended numeric
  fields, account IDs, asset values, multi-currency evidence, fee/tax/margin
  evidence, cashflow activity, income return, order execution, source audit
  counts, and Investor Wiki flow.
- The proof keeps exact user business numbers intact for assets, cash, buying
  power, fees, tax, margin, FX, orders, executions, positions, dividends, and
  cashflows when the user authorized those inputs.
- `manifest.cashflow_activity_summary`, `manifest.income_return_summary`, and
  `manifest.order_execution_summary` expose deposits/withdrawals, dividend
  gross/net/tax, FX amounts, net cashflow, dividend symbols, P/L, fee/tax drag,
  order statuses, order type/TIF, trade IDs, settlement dates, and fill ratios.
- False claims remain explicit: no complete account boundary, no complete
  brokerage history, no native broker API validation, no trading password, no
  order mutation, no community crawl, and no direct Wiki write.
- This improves FinClaw gating for P2 HK/US brokerage packages, but still does
  not replace real Futu/Tiger/IBKR export or read-only-screen validation.

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
and behavior-surface coverage for authorized finance-news usage exports, saved
pages, ZIP packages, and browser-history copies:

- `financial_news_usage.py collect --input <authorized-export-or-history-copy>
  --out-dir <dir>` records `manifest.source_audit` with requested inputs,
  missing inputs, per-file parse results, extension coverage, parsed/emitted
  counts, skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  browser-history source apps, and path-safety flags.
- Browser history remains domain-filtered to CLS, WallstreetCN, and Gelonghui
  before events are written.
- The collector remains personal-usage evidence and does not crawl or mirror
  public news content.
- Events and manifests now preserve search terms, subscription targets, alert
  conditions, notification channels, trigger sources, referrers, session IDs,
  dwell seconds, visit/typed counts, and browser transition types when the
  authorized input provides them. `usage_boundary_proof.usage_behavior_boundary`
  exposes those counts to FinClaw without claiming complete account history.
- This improves the P1 finance-news usage package path, but it does not claim
  real app/account adapters, subscription stores, real Safari/macOS history
  samples, or Windows/Linux browser-history path validation.

The prior completed wave: `wechat-favorites` now has stronger source audit and
behavior-surface coverage for authorized WeChat favorites and public-account
article exports:

- `wechat_favorites.py collect --input <authorized-export> --out-dir <dir>`
  records `manifest.source_audit` with requested inputs, missing inputs,
  per-file parse results, extension coverage, parsed/emitted counts, skipped
  file reasons, ZIP member counts, skipped ZIP member reasons, and path-safety
  flags.
- The collector remains a generic saved-article/action source and does not
  claim investment relevance; `wechat-article-favorites` remains responsible
  for investor Wiki evidence.
- Generic events and the investment lens now preserve article IDs, source
  account types, favorite reasons, share targets, read duration/progress,
  symbol hints, and engagement counters when the authorized input provides
  them. `wechat_article_boundary_proof.behavior_boundary` exposes those counts
  to FinClaw without claiming a complete WeChat read history.
- This improves the P1 public-account article package path, but it does not
  claim real WeChat favorites database, public-account read-history, Windows,
  or Linux validation.

The prior completed wave: `notes-collector` now has stronger source audit
coverage for authorized Obsidian vaults and notes exports:

- `notes_api.py obsidian/import --out-dir <dir>` records
  `manifest.source_audit` with input kind, resolved files, extension coverage,
  parsed/emitted counts, skipped file reasons, ZIP member counts, skipped ZIP
  member reasons, path-level results, and path-safety flags.
- Notion-style CSV/TSV database exports are now accepted as table notes; the
  audit records table file count, table row count, and emitted table note count.
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

The latest completed wave: `email-research` now has a lens-level surface and
boundary proof for investor Wiki gating:

- `manifest.lens_surface_summary` classifies broker research, morning meetings,
  roadshow invitations, company IR threads, earnings/announcement alerts,
  research attachment refs, and portfolio alerts.
- `manifest.email_research_boundary_proof` records sender-domain, folder,
  mailbox, timestamp, message-id, body-preview, attachment-ref, and research
  attachment coverage while keeping full-body Wiki inclusion, attachment-body
  collection, and complete-mailbox claims false.
- Fixture validation covers upstream `email` lake events, filters unrelated
  personal mail, validates the generated package with `--require-evidence`, and
  confirms the lens remains dependent on the generic `email` collector.

The latest completed wave: `wechat` now has standard preflight/no-message gap
packages for FinClaw:

- `wechat-export` is upgraded to `0.11.2`.
- `wechat_query.py --collect --out-dir <dir>` now writes a validator-safe
  profile gap package when `db_storage` is missing, Mac 4.x key/dependency
  preflight fails, or no owner-relevant text messages remain after filters.
- Gap events record `raw_database_access_performed=false`,
  `credentials_collected=false`, `message_text_collected=false`, and
  `investment_claim_allowed=false`.
- Manifest readiness sets `can_enter_investor_lens=false` for those gap
  packages, so FinClaw can distinguish "not authorized/not ready/no retained
  messages" from a successful WeChat conversation source.
- This improves product gating while real-source validation remains blocked on
  this Mac by WeChat 4.x key/SIP preconditions.

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
| 微信投资对话 | `wechat` generic collector + `wechat-investment-dialogue` lens classifier | `baseline+audit`; `wechat` writes a standard CollectorX package; the lens supports chat/sender source policy, source-policy audit, explicit `source_policy_filtered_all` gap status, classifier metadata, WeChat dialogue boundary proof, dialogue surface summary, and fixture validation; real-source validation remains blocked on current Mac by missing WeChat 4.x keys/SIP enabled | Prepare authorized WeChat keys, real WeChat lake validation, user-tuned contact/group/sender allowlists, entity/time matching, backtest against trade events |
| 本地研报/财报/PDF/Excel/Markdown/截图 | `filesystem-collector` metadata-only + `research-documents` lens classifier/content reader | `baseline+audit`; macOS metadata and explicit content extraction validation passed; default-root code paths for macOS/Windows/Linux are fixture-tested; filesystem manifest records authorized-root source audit, extension coverage, skipped reasons, per-root results, filtered-all/no-metadata gap packages, and metadata-only boundary proof; research-documents manifest records requested inputs, missing inputs, per-file parse results, skipped reasons, extension/path/file-name/parser/research-surface/keyword scope-policy audit, filtered-all status, extraction policy, parser counts, content-read counts, limit truncation, screenshot metadata-only/default policy, explicit `--include-image-ocr` tesseract adapter audit, legacy XML/HTML/text/renamed OOXML `.xls` extraction, binary `.xls` xlrd availability/failure audit, PPTX slide-text extraction, research document surface summary, and research corpus boundary proof | Broader private PDF/XLS/XLSX/DOCX/PPTX/image samples, real binary `.xls` with xlrd validation, OCR quality review on real Chinese screenshots, real Windows/Linux device validation, backtest against real trades/reviews |
| 雪球投资活动 | `xueqiu-watchlist` + `xueqiu-investor-activity` | `baseline+audit`; watchlist and activity collectors support authorized ZIP packages with member provenance, path-traversal skipping, source audit, field coverage, authorization scope-policy audit, validator-safe filtered-all/no-input gap packages, and explicit non-broker-trade evidence policy; watchlist emits attention-universe boundary proof for symbol/market/group/industry/tag/keyword scope; activity also supports XLSX/XLSM, saved HTML pages, nested Snowball-like payloads, activity/source/domain/symbol/author/keyword scope boundaries, activity-boundary proof, pagination completeness summary, HAR browser-network export parsing for `xueqiu.com` response bodies, copied Chromium/Safari browser history with Xueqiu-domain filtering, visit/typed counts, transition types, credential/query stripping audit, raw sanitization, and SoulMirror sync; not yet a one-click real account adapter | Real Xueqiu account/HAR/browser-history samples, real pagination coverage, watchlist/favorites/posts/comments/follows/portfolio validation, rate/terms boundary |
| 支付宝/天天基金/蛋卷/且慢/银行理财 | `china-wealth-assets` | `baseline+audit`; normalized local export/package path covers Excel/legacy `.xls`/Excel XML/HTML table/PDF statement/JSON/CSV/ZIP plus HAR browser-network export parsing for whitelisted fund/wealth domains, platform inference, numeric asset fields, platform/account/subtype/product/currency/side/keyword scope-policy audit, filtered-all gap packages, platform coverage, field coverage, account boundary summary, partial asset-boundary proof strength, authorization scope boundary, asset surface summary, currency summary, transaction-side summary, source/PDF/HAR audit, asset value summary, credential/query stripping, raw sanitization, ZIP provenance, skipped ZIP accounting, and SoulMirror sync; no one-click real account adapter yet | Real platform PDF/HAR/export samples, per-platform UI adapters, real account validation, complete account-boundary proof |
| 邮件研报 | `email` generic collector + `email-research` lens classifier | `baseline+audit`; IMAP `collect --out-dir`, local email `import --local-scan --out-dir`, and local EML/Apple Mail EMLX/Maildir/MBOX/Thunderbird mbox/JSON/CSV/TSV/ZIP `import --out-dir` produce standard packages with account/folder audit, local-scan/import audit, skipped file/ZIP-member reasons, Apple Mail/Maildir/Thunderbird counts, Thunderbird `.msf` index skip audit, local-scan root status, field coverage, sanitized attachment refs, body/attachment policy, mailbox boundary proof, generic-to-lens evidence boundary, research-attachment filename matching, email research surface summary, sender-domain/body-preview/attachment boundary, sender-domain/folder/mailbox/subject/attachment/email-surface/keyword scope-policy audit, filtered-all readiness, and email_research_boundary_proof.authorization_scope_boundary; current machine has no registered mailbox, so real mailbox validation is still pending | Register mailbox through `password_env`, validate real Apple Mail/Thunderbird/Maildir local roots, broader broker/IR sender backtest, no-full-body Wiki leakage review on real mailboxes |

## P1 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 飞书/钉钉/腾讯会议/企业微信会议纪要 | `meeting-artifacts` local/platform-export/ZIP collector + `feishu` authorized export package collector + `collaboration-exports` for `dingtalk`/`wecom` + `meeting-minutes` lens classifier | `baseline+audit`; macOS local meeting-file validation passed; HTML/CSV/JSON/ZIP platform-export fixture validation passed; meeting manifest reports platform coverage, field coverage, meeting surface summary, participant-role counts, action/decision/risk item counts, recording refs, requested inputs, missing paths, unsupported file extensions, ZIP provenance, ZIP skip counts/reasons, per-input parse audit, source audit, source-platform/participant/keyword scope-policy audit, filtered-all status, and evidence policy; Feishu now has a CollectorX `collect` package path for messages/documents/files/folders/meetings/recordings with field coverage, surface summary, ZIP skip counts/reasons, per-input parse audit, source audit, and evidence policy; DingTalk/WeCom collaboration exports support ZIP plus equivalent audit fields and source-platform/record-kind/chat/sender/participant/keyword scope-policy audit; meeting-minutes lens now reports roadshow/research/IC/expert/earnings/decision/risk/follow-up surfaces, upstream collectors, source platforms, participant roles, meeting URLs, attachment refs, recording refs, time coverage, decision/action/risk item coverage, meeting-minutes boundary proof, and decision/action boundary proof; platform account APIs pending | Build/port real Feishu/DingTalk/WeCom/Tencent Meeting account adapters, validate real authorized exports, participant and speaker identity normalization, attachment/recording reference validation, false-positive review |
| Obsidian/Notion/有道云/印象笔记 | `notes-collector` event package + authorized export/ZIP import + `investment-notes` lens classifier | `baseline+audit`; macOS Obsidian-style real validation passed; Youdao/Evernote/Markdown/Obsidian Canvas/HTML/JSON/CSV/TSV/ENEX/ZIP fixtures pass; generic notes manifest reports platform coverage, field coverage, source-app/path/tag authorization filters, table import audit, Canvas import audit, per-input parse results, skipped reasons, ZIP provenance, path-safety boundary, content policy, and generic-collector evidence policy; investment-notes manifest/evidence now reports review/rules/checklist/valuation/research note-type surface, source-app surface, preview/full-content surface, and investment note boundary proof | Validate real Notion/Youdao/Evernote account exports or APIs, real-user allowlist tuning, false-positive review, Windows/Linux vault path validation |
| 日历/任务/滴答清单 | `ticktick-cli` SoulMirror YAML + AgentRunner + skill live path; `ticktick_events.py` offline export helper; `calendar-collector`; `task-calendar-investor` lens classifier | `baseline+audit`; TickTick live path now returns a dependency-light JSON snapshot through `collect_for_soulmirror.py`, fails clearly with `ticktick_auth_required` when disconnected, and keeps daemon-owned `lake/ticktick/events.jsonl` separate from offline `exports/ticktick/events.jsonl`; offline TickTick/Dida imports support source-app/project/tag/keyword scope-policy audit; fake OpenAPI validation covers active/completed tasks, project names, inbox fallback, dedupe, checklist counts, timezone/repeat/reminder fields, and token non-leakage; generic calendar ICS/JSON/CSV/TSV/ZIP paths report duration, multi-day, invalid-time, conflict quality, and source-platform/calendar/attendee/keyword scope-policy audit; task-calendar lens surfaces preserve these time-quality counts plus task checklist execution structure and writes task/calendar boundary proof | Deploy FinClaw-managed TickTick OAuth Broker, run real account validation, validate real calendar exports/accounts, recurring tasks/timezones/checklists, backtest investment task classifier |
| 公众号/微信收藏文章 | `wechat-favorites` local file/folder/ZIP collector + `wechat-article-favorites` lens classifier | `baseline+audit`; macOS saved-article validation passed; JSON/HTML/ZIP fixtures cover favorite/read/share/saved-file actions plus favorite reasons, share targets, read duration/progress, article IDs, symbols, and engagement counters; generic manifest reports action coverage, field coverage, article surface summary, article behavior summary, source-account/source-account-type/action/tag/domain/keyword scope-policy audit, filtered-all status, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, source audit, content policy, and generic-collector evidence policy; wechat-article lens reports broker/fundamental/strategy/industry/valuation/portfolio/risk/macro article surfaces, action counts, source-account type counts, URL/article-ID/tag/text/time coverage, behavior boundary proof, article boundary proof, and filters non-investment saved articles; real WeChat favorites adapter pending | Discover/validate real WeChat favorites and public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation, false-positive backtest |
| 华尔街见闻/财联社/格隆汇使用痕迹 | `financial-news-usage` local usage/browser-history/ZIP collector | `baseline+audit`; JSON/CSV/HTML/TXT/ZIP fixture validation passed; Chromium browser-history validation passed; Safari `History.db` direct-file and ZIP-member validation passed; manifest reports platform/action/topic coverage, field coverage, usage surface summary, usage behavior summary, platform/action/source-app/domain/topic/keyword scope-policy audit, filtered-all gap packages, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, browser-history source audit/source-app counts, usage boundary proof, content policy, and evidence policy; usage topics cover macro policy, market strategy, industry themes, company fundamentals, HK/US markets, risk events, trading opportunities, and portfolio alerts; behavior fields cover query terms, subscription targets, alert conditions, notification channels, trigger sources, referrers, session IDs, dwell seconds, visit/typed counts, Safari load status, and browser transition types; real app/account adapters pending | Discover/validate CLS/WallstreetCN/Gelonghui app caches, account APIs, real subscription/alert stores, real Safari/macOS history samples, Windows/Linux browser-history paths, authorization default scopes, topic false-positive review; do not crawl public news as personal evidence |

## P2 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 富途/老虎/盈透/港美股券商 | `hk-us-brokerage` local read-only CSV/JSON/Excel/ZIP export collector | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, broker coverage, trade-surface coverage, field coverage, strong-trade surface summary, account-boundary summary, currency/market summary, fee/tax/margin summary, asset value summary, cashflow activity summary, income return summary, order execution summary, broker/account/subtype/symbol/market/currency/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, ZIP provenance, per-input parse results, skipped file/ZIP-member reasons, path-safety audit, and read-only evidence policy validation passed; no real local export found yet | Validate real Futu/Tiger/IBKR exports or read-only screens, broker-specific column maps, complete account-boundary proof, multi-currency assets, margin, tax, dividends, FX, authorization default scopes, and Windows/macOS/Linux paths |
| Choice/Wind/同花顺 iFinD 使用痕迹 | `pro-terminal-usage` local CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow collector | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, terminal coverage, activity coverage, workflow-field coverage, workflow-topic coverage, workflow surface summary, workflow intensity summary, query terms, parameters, export paths, row counts, workspace/template IDs, object counts, terminal/activity/workspace/project/dataset/field/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, workflow/gap event counts, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, license policy, and evidence policy validation passed; real licensed terminal exports pending | Validate real Wind/Choice/iFinD/Bloomberg authorized workflow exports, user workspace paths, watchlists, searches, downloads, templates, datasets, fields, function codes, query/export lineage, authorization default scopes, workflow-topic false positives, and license-safe boundaries |
| B站/微博/小红书投资内容痕迹 | `social-activity` local JSON/CSV/Excel/HTML/TXT/ZIP/browser-history activity collector + `social-investment-influence` lens classifier | `baseline+audit`; fixture validation passed; multi-section JSON, Excel, ZIP, Chromium browser-history copy, weak-evidence policy, platform coverage, action coverage, weak-signal-field coverage, social-topic coverage, influence surface summary, browser-history source/visit/transition summary, platform/action/source-app/domain/creator/topic/keyword scope-policy audit, filtered-all readiness, social activity boundary proof, social influence boundary proof, per-input parse results, skipped file/ZIP-member reasons, ZIP provenance, source audit, limit truncation, domain filtering, and preview-only content policy validation passed; real account/export adapters pending | Validate real Weibo/Bilibili/Xiaohongshu exports, real Chromium/Safari/Windows/Linux browser-history paths, watch/favorite/like/follow/comment/share surfaces, platform allowlists, creator/domain default allowlists, engagement fields, social-topic false positives, and weak-evidence backtest |

## Deep-Designed Existing Collectors

| Collector | Current status |
| --- | --- |
| `eastmoney-portfolio` | `production-candidate` on current macOS machine for unlocked account read-only asset/holding/execution/order/fund-flow capture; event-kind/symbol/account/source/keyword authorization scope-policy audit, filtered-all readiness, and strong trade boundary proof exist; Windows/Linux are code-level simulations or fallback paths |
| `ths-portfolio` | `deep-beta`; strong local package, GUI snapshot design, event-kind/symbol/account/source/keyword authorization scope-policy audit, explicit filtered-all gap event, and Wiki boundary proof exist, but broader real-device/multi-account validation is still required before production |
| `ths-watchlist` | `baseline+audit`; authorized local-scan plus export/package collector for same-channel watchlist/attention-universe evidence with local-scan provenance, path-level source audit, ZIP provenance, symbol/market/group/industry/tag/keyword/source authorization scope-policy audit, filtered-all readiness, field coverage, ths_watchlist_boundary_proof, and standard 7/20 Wiki evidence package; not a strong trade, holding, order, or fund-flow collector |
| `qq` | `deep-beta`; QQ NT discovery/decrypt-ready flow plus standard package output, manifest/summary, field/filter audit, gap packages, and fixture package validation exist; current machine still has LLDB/passphrase capture limitation for real encrypted NT messages |

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
