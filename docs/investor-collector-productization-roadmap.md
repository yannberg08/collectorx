# Investor Collector Productization Roadmap

This is the working roadmap for turning the P0/P1/P2 investor-avatar collectors
from registry entries into production-ready CollectorX sources.

## Operating Rule

CollectorX progress is tracked in the repo. Every productization wave should
leave behind:

1. Runnable collector or lens code.
2. Fixture tests without private data.
3. CLI invocation contract for FinClaw.
4. Updated readiness status.
5. Git commit after the validation suite passes.

No collector is marked `production-candidate` without real-device or real-account
validation.

## Readiness Gates

| Gate | Meaning | Proof |
| --- | --- | --- |
| G0 Contract | Source is classified and has a YAML/profile entry | Taxonomy, matrix, scope, exclusions |
| G1 Runnable Baseline | CLI can parse authorized local input and emit events | Fixture tests, manifest, evidence package |
| G2 Source Adapter | Collector can reach the real source with user authorization | Source-specific adapter, preflight, platform notes |
| G3 Real Validation | Runs against a real account/device/export | Readiness manifest, gap log, no secret leakage |
| G4 Wiki Backtest | Evidence lands in the 7 dimensions / 20 subdimensions correctly | Backtest fixture, false-positive review |
| G5 Production Candidate | FinClaw can expose it as a user-facing collector | Stable CLI, docs, tests, platform status |

## Program Control Board

The current product control board is maintained in:

- `collectors/finclaw-investor-catalog.json` for machine-readable FinClaw
  discovery and gating.
- `docs/finclaw-investor-collector-productization.md` for the human P0/P1/P2
  productization status.

The wave log below records how each collector reached its current state.

## Completed Waves

### Wave A: Investor lens evidence baseline

Status: `completed-baseline`

Implemented in `skills/investor-source-collectors`:

- Investment evidence classifier for lens sources.
- Default filtering for generic-channel lenses.
- Vertical sources pass as investment-native evidence.
- Upstream `collectorx.event.v1` input support.
- Classification metadata: confidence, reasons, matched terms, symbols.
- Gap output when authorized input has no investment evidence.
- Wiki evidence generation excludes gap events.

Covered lenses:

- `wechat-investment-dialogue`
- `research-documents`
- `email-research`
- `meeting-minutes`
- `investment-notes`
- `task-calendar-investor`
- `wechat-article-favorites`
- `social-investment-influence`

Remaining to production:

- Validate against real WeChat/email/notes/files/task lake outputs.
- Add user white/black lists and source-specific allowlists.
- Backtest false positives and false negatives against real investor histories.
- Add entity extraction beyond keyword/security-code matching.

### Wave B: P0 real validation pass 1

Status: `in-progress`

Validation record:

- `docs/validations/investor-p0-real-validation-2026-07-08.md`

Findings:

- `wechat-investment-dialogue`: real source collection is blocked on this Mac
  because WeChat 4.x per-DB keys are not available and SIP is enabled. No
  messages were read.
- `research-documents`: real local metadata validation passed on macOS; 1000
  filesystem metadata events yielded 454 research-document lens events and 10
  usable investor subdimensions.
- `filesystem`: generic collector route was corrected so it no longer suggests
  investor Wiki targets for every file.
- `email-research`: real mailbox validation is blocked because no mailbox is
  registered in the local email collector.
- `xueqiu-investor-activity`: local candidate parsing produced 100 events from
  22 candidate files, but this is not yet a real account adapter.
- `china-wealth-assets`: local candidate parsing produced 1 holding event from
  20 candidate files; manifest was corrected to avoid claiming complete asset
  boundary from partial input.

### Wave B1: P0 WeChat standard package pass 1

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-wechat-standard-package-validation-2026-07-08.md`

Findings:

- Added `--out-dir` to `wechat_query.py --collect` so WeChat can write a
  standard CollectorX package: `lake/wechat/events.jsonl`, `manifest.json`, and
  `SUMMARY.md`.
- Preserved the legacy compact JSON array path through `--out`.
- Converted collect records into `collectorx.event.v1` message events with
  chat, sender, sender ownership, text, text length, source, raw refs, and
  local-only personal-message privacy markers.
- Added manifest field coverage, message surface summary, filter policy,
  platform precondition notes, source audit, and generic-to-lens evidence
  policy.
- Kept the boundary explicit: generic `wechat` enters Lake, and
  `wechat-investment-dialogue` is responsible for investor Wiki evidence.
- Fixture validation covers standard package output without requiring real
  WeChat data or keys.
- Real-source validation is still blocked on the current Mac by WeChat 4.x key
  extraction/SIP preconditions.

### Wave B1b: P0 WeChat investment-dialogue source policy pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-wechat-lens-source-policy-validation-2026-07-08.md`

Findings:

- Added source-scope policy flags to `investor_sources.py collect`:
  `--allow-chat`, `--deny-chat`, `--allow-sender`, and `--deny-sender`.
- The policy is applied before investment classification, so FinClaw can narrow
  WeChat lens runs to user-approved contacts, groups, and senders.
- The policy does not assert investment relevance; normal investment
  classification still decides whether a message can become investor evidence.
- Manifest `collection_audit.source_policy` records configured patterns,
  filtered candidate count, and filter reason counts.
- Added explicit `source_policy_filtered_all` gap status when every readable
  candidate is excluded by source policy.
- Fixture validation covers allow chat, deny sender, policy metadata on kept
  events, source-policy audit counts, and filtered-all gap behavior.
- Real WeChat lake validation and user-tuned allowlists are still pending.

### Wave B2: P0 research content extraction pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-research-content-validation-2026-07-08.md`

Findings:

- Added explicit `--include-content` extraction for research documents in
  `skills/investor-source-collectors`.
- Default filesystem scanning remains metadata-only.
- Fixture validation covers XLSX, DOCX, and PDF content extraction.
- Real local candidate validation produced 28 research evidence events from 30
  candidates and confirmed 6 PDF content extractions via `pdfplumber`.
- Wiki coverage reached 10 usable investor subdimensions.

### Wave B2b: P0 research scope audit and false-positive guard

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-research-scope-audit-validation-2026-07-08.md`

Findings:

- Added `manifest.collection_audit` for `research-documents`: input file counts,
  candidate counts, filtered counts, skipped extension counts, parser counts,
  content-read counts, and content extraction status counts.
- Added a machine-readable content policy that keeps the generic `filesystem`
  collector metadata-only and requires explicit `--include-content` before
  DOCX/PDF/XLSX/XLSM body/table extraction.
- Registered the same policy in `collectors/lenses/research-documents.yaml`.
- Tightened file-title classification so a lone broad title hint such as
  `股票` or `基金` does not enter Wiki evidence without stronger research
  context.
- Fixture validation covers authorized content extraction, metadata-only binary
  handling without `--include-content`, unsupported extension skipping, and weak
  title false-positive filtering.

### Wave B2c: P0 research document source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-research-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.4`.
- Added path-level `manifest.collection_audit` fields for requested inputs,
  missing inputs, skipped reasons, per-file parse results, candidate/emitted
  counts, parser names, and limit truncation.
- Added explicit screenshot/image metadata-only audit fields:
  `screenshot_metadata_only_file_count`, `ocr_performed=false`, and per-path
  `content_policy=screenshot_metadata_only_no_ocr`.
- Preserved the content boundary: generic `filesystem` remains metadata-only;
  DOCX/PDF/XLSX/XLSM extraction still requires `--include-content`; OCR is not
  claimed without a future separate adapter and user authorization.
- Fixture validation covers PDF/DOCX/XLSX content extraction, binary
  metadata-only mode, missing inputs, unsupported extensions, broad-title
  false-positive filtering, screenshot metadata-only/no-OCR policy, and limit
  truncation.

### Wave B2d: P0 research screenshot OCR adapter pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-research-image-ocr-validation-2026-07-08.md`

Findings:

- Added explicit `--include-image-ocr` authorization for `research-documents`.
  It is separate from `--include-content`, so reading document bodies and
  reading screenshot text remain two distinct user choices.
- Added a local `tesseract` adapter selected from `PATH` or
  `COLLECTORX_TESSERACT_CMD`.
- OCR output is treated like other explicit content extraction: capped text,
  parser/status metadata, `content_read`, `content_extract`, and
  `raw_ref.image_ocr_*` fields are recorded.
- If OCR is requested but the engine is missing or fails, the run degrades to
  metadata-only evidence and records the OCR status in manifest/path audit
  instead of pretending the screenshot was read.
- Fixture validation covers default metadata-only screenshot behavior and a fake
  local `tesseract` adapter that extracts investment-relevant screenshot text.
- This improves the P0 local research-material channel, but it still needs real
  private screenshot samples, Chinese OCR quality review, Windows/Linux engine
  path validation, and Wiki backtesting against real trades/reviews.

### Wave B3: P0 Xueqiu activity productization pass 2

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-xueqiu-productization-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-investor-activity` to normalize Snowball-like nested
  `statuses/list/data/items/stocks/cubes/rebalancing_histories` payloads.
- Added credential-key sanitization for retained raw metadata.
- Added fixture validation for posts, favorites, owner portfolio activity,
  portfolio change details, normalized security symbols, and SoulMirror lake
  sync.
- Current local machine did not have a clearly named authorized Xueqiu export,
  so this pass still does not claim real account validation.

### Wave B3b: P0 Xueqiu package provenance and evidence policy

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-xueqiu-package-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-watchlist` to `0.2.1` and `xueqiu-investor-activity` to
  `0.2.1`.
- Added authorized ZIP package import for watchlist and broad activity exports.
- ZIP packages preserve `archive.zip::member` provenance and skip unsafe path
  traversal members.
- Added XLSX/XLSM workbook parsing to `xueqiu-investor-activity`.
- Added manifest evidence policies that explicitly mark Xueqiu as attention,
  network, opinion, and model-portfolio evidence only, not broker-confirmed
  trade evidence.
- Fixture validation covers watchlist ZIP, activity ZIP with Excel workbook,
  archive member provenance, traversal skipping, and broker-trade boundary flags.

### Wave B3c: P0 Xueqiu source audit and saved-page fix

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-xueqiu-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-watchlist` and `xueqiu-investor-activity` to `0.3.0`.
- Fixed saved HTML page parsing in `xueqiu-investor-activity`; saved pages now
  enter as `saved_page` activity instead of crashing on undefined variables.
- Added source audit to both Xueqiu collectors: input count, resolved file
  count, extension coverage, ZIP member counts, skipped member counts, parsed
  records, emitted events, and path-level results.
- Added field coverage to both manifests.
- Added pagination marker audit to `xueqiu-investor-activity` for fields such as
  `page`, `total`, `max_id`, `next_max_id`, `since_id`, and cursor-like fields.
- Preserved the evidence boundary: Xueqiu is attention, network, opinion,
  saved-page, and model-portfolio evidence, not broker-confirmed trade evidence.
- Fixture validation covers saved HTML pages, source audit, field coverage,
  pagination marker audit, ZIP skip accounting, and watchlist filtered-record
  accounting.
- Real Xueqiu account adapter and real pagination validation remain pending.

### Wave B3d: P0 Xueqiu authorized browser-network export pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-xueqiu-har-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-investor-activity` to `0.3.1`.
- Added `.har` input support for user-authorized browser network exports.
- HAR parsing only reads `xueqiu.com` response bodies and stores endpoint path,
  response status, HAR entry, and row provenance. Request headers, cookies,
  Authorization values, and request URL query strings are not written to events,
  manifest, or Wiki evidence.
- Manifest audit now records HAR file count, entry count, Xueqiu entry count,
  endpoint coverage, skip reasons, response record count, query-string stripping
  count, and credential-material stripping count.
- Fixture validation covers a logged-in-like Xueqiu timeline response, a
  non-Xueqiu URL skip, a non-JSON Xueqiu skip, symbol/author normalization, and
  credential non-leakage.
- This is an authorized browser export baseline, not a one-click login/session
  adapter. Real account HAR samples and pagination completeness remain pending.

### Wave B3e: P0 Xueqiu activity-boundary and pagination proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-xueqiu-activity-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-investor-activity` to `0.3.2`.
- Added `manifest.activity_boundary_proof` and mirrored it into
  `investor_wiki_evidence.v1.json`.
- Expected activity surfaces now include watchlist, followed users, followed
  portfolios, portfolio activity, comments, favorites, posts, and saved pages.
- Per-surface proof levels distinguish usable, thin, raw-presence, and missing
  activity evidence.
- Added `pagination_completeness` with pagination marker counts, marker fields,
  HAR endpoint counts, limit truncation status, and conservative
  `complete_timeline_claimed: false` policy.
- Package `SUMMARY.md` now shows activity-boundary proof and pagination
  completeness levels.
- Fixture validation covers all expected activity surfaces, HAR pagination
  markers, evidence propagation, package summary output, and the explicit
  non-broker-trade boundary.
- This improves Snowball as a P0 attention-network and opinion-source channel,
  but it does not claim a one-click real account adapter or complete timeline
  validation.

### Wave B4: P0 China wealth assets productization pass 2

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-china-wealth-productization-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to normalize Alipay, Tiantian Fund, Danjuan,
  Qieman, and bank-wealth local exports.
- Added XLSX/XLSM parsing via `openpyxl` in addition to CSV/TSV/JSON/JSONL and
  saved HTML/TXT screens.
- Added numeric field normalization for market value, total assets, cash,
  cost, PnL, PnL rate, transaction amount, and fees.
- Added credential-key sanitization for retained raw metadata.
- Added fixture validation for mixed platform JSON, Excel exports, partial
  boundary manifests, and SoulMirror lake sync.
- Current local machine did not have a clearly named authorized fund/wealth
  export, so this pass still does not claim real account validation.

### Wave B4b: P0 China wealth ZIP and field coverage pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-china-wealth-field-coverage-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to `0.3.1`.
- Added authorized ZIP package import for CSV/TSV, JSON/JSONL/NDJSON,
  XLSX/XLSM, HTML, Markdown, and TXT members.
- ZIP packages preserve `archive.zip::member` provenance and skip unsafe path
  traversal members.
- Added `manifest.field_coverage` so FinClaw can inspect platform, product,
  quantity, NAV, value, cost, PnL, rate, transaction amount, fee, and side
  coverage.
- Added `manifest.asset_value_summary` and evidence-package value summary so
  FinClaw can see this run's authorized market value, total asset, and
  transaction amount totals by platform.
- Added `manifest.evidence_policy` to state that no complete asset boundary or
  real account validation is claimed.
- Fixture validation covers ZIP import, archive member provenance, traversal
  skipping, value summary, and field coverage.

### Wave B4c: P0 China wealth source audit pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-china-wealth-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to `0.4.0`.
- Added source audit to the manifest: input count, resolved file count,
  extension coverage, ZIP member count, skipped member count, parsed record
  count, emitted event count, supported extensions, and path-level parse
  results.
- Kept the complete asset boundary policy unchanged: parsed exports are partial
  authorized input until each platform/account path is validated.
- Fixture validation covers missing-input audit, ZIP member/skipped-member
  accounting, extension counts, parsed record counts, emitted event counts,
  platform coverage, field coverage, and asset value summary.
- Real Alipay/Tiantian/Danjuan/Qieman/bank account validation remains pending.

### Wave B4d: P0 China wealth account boundary pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-china-wealth-account-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to `0.4.1`.
- Added manifest and evidence summaries for account boundary, asset surface,
  currency, platform-surface matrix, and transaction-side amounts.
- Kept the complete asset/account boundary policy unchanged: parsed exports are
  partial authorized input until each platform/account path is validated.
- Fixture validation covers five expected platforms, five named account groups,
  asset snapshot, fund holding, wealth holding, cash-management, fund
  transaction, CNY/USD value fields, buy/sell transaction-side amounts, and
  evidence-package propagation.
- Real Alipay/Tiantian/Danjuan/Qieman/bank account validation remains pending.

### Wave B4e: P0 China wealth authorized browser-network export pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-china-wealth-har-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to `0.4.2`.
- Added `.har` input support for user-authorized browser network exports.
- HAR parsing only reads whitelisted Alipay, Tiantian Fund, Danjuan, Qieman,
  and bank-wealth response bodies. It stores endpoint path, response status,
  platform, HAR entry, and row provenance. Request headers, cookies,
  Authorization values, and request URL query strings are not written to events,
  manifest, or Wiki evidence.
- Manifest audit now records HAR file count, entry count, investment-platform
  entry count, platform-entry coverage, endpoint coverage, skip reasons,
  response record count, query-string stripping count, and credential-material
  stripping count.
- Fixture validation covers Alipay cash-management holdings, Tiantian Fund
  subscription transactions, non-investment URL skipping, bank non-JSON skipping,
  account/value normalization, platform inference, and credential non-leakage.
- This is an authorized browser export baseline, not a one-click login/session
  adapter. Real platform HAR samples and full account-boundary proof remain
  pending.

### Wave B4f: P0 China wealth asset-boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-china-wealth-asset-boundary-proof-validation-2026-07-08.md`

Findings:

- Upgraded `china-wealth-assets` to `0.4.3`.
- Added `manifest.asset_boundary_proof` and mirrored it into
  `investor_wiki_evidence.v1.json`.
- The proof checks platform identity, named account refs, asset snapshots,
  holding surfaces, transaction surfaces, and numeric value fields.
- Account proof levels are conservative:
  `strong_partial_account_boundary`, `medium_partial_account_boundary`,
  `weak_partial_account_boundary`, and `no_account_evidence`.
- Overall proof remains partial. `complete_asset_boundary_claimed` remains
  false until real account/read-only-screen validation proves platform and
  account scope.
- Fixture validation covers no-input gaps, all expected platforms, account-level
  strong/medium proof classification, missing account requirements, platform
  proof summaries, package summary output, and Wiki evidence propagation.
- This improves FinClaw's ability to distinguish useful fund/wealth asset
  evidence from incomplete input, but it does not claim one-click real
  Alipay/Tiantian/Danjuan/Qieman/bank account validation.

### Wave B5: P0 Email IMAP package and audit pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-email-imap-package-validation-2026-07-08.md`

Findings:

- Upgraded `email-collector` to `0.5.0`.
- Added `email_api.py collect --account all --out-dir <dir>` for registered
  IMAP mailboxes, matching the local import package contract.
- Standard IMAP packages now include `lake/email/events.jsonl`,
  `manifest.json`, and `SUMMARY.md`.
- Manifest output records account/folder audit, selected/configured account
  counts, login/search/fetch status counts, matched and fetched message counts,
  field coverage, body policy, attachment policy, and generic-to-lens evidence
  policy.
- Gap packages now distinguish missing registered mailbox, no messages in the
  selected time window, and IMAP collection failure.
- Fixture validation covers fake IMAP multi-folder package output and missing
  registered mailbox gap output.
- Current local machine still has no registered mailbox, so this pass does not
  claim real mailbox G3 validation.

### Wave C: P1 notes productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-notes-validation-2026-07-08.md`

Findings:

- `notes-collector` now emits `collectorx.event.v1` and a standard collection
  package for Obsidian/Notion flows.
- Real local Obsidian-style validation produced 168 generic note events.
- `investment-notes` lens produced 100 investor-note evidence events and 10
  usable investor subdimensions.
- Shared lens readiness was corrected so it does not claim complete source
  collection from partial authorized input.

### Wave C2: P1 notes export import pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-notes-export-validation-2026-07-08.md`

Findings:

- Added `notes_api.py import` for user-authorized local note exports and folders.
- Supported Markdown, TXT, HTML, JSON/JSONL/NDJSON, and Evernote ENEX.
- Added source inference for Youdao, Evernote/Yinxiang, Notion, Markdown, and
  generic note exports.
- Fixture validation covers Youdao-style JSON, Evernote ENEX, and Markdown
  imports into generic `notes` events.

### Wave D: P1 task/calendar productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-task-calendar-validation-2026-07-08.md`

Findings:

- Added `ticktick_events.py` to convert authorized TickTick task JSON into
  `collectorx.event.v1`.
- `task-calendar-investor` lens now has a fixture proving investment tasks are
  kept and unrelated personal tasks are filtered.
- Real TickTick API validation is blocked because the local OAuth token is not
  present.

### Wave D2: P1 generic calendar productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-calendar-validation-2026-07-08.md`

Findings:

- Added runnable `calendar-collector` generic collector for authorized ICS,
  JSON/JSONL, CSV, and TSV calendar exports.
- Captures title, start/end time, all-day flag, location, meeting links,
  organizer, attendees, recurrence, and reminders.
- Generic calendar events route to `internal.calendar.events`; investment
  filtering remains in `task-calendar-investor`.
- Fixture validation covers ICS, JSON, CSV, gap events, and raw credential-key
  sanitization.

### Wave E: P1 meeting artifacts productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-meeting-validation-2026-07-08.md`

Findings:

- Added runnable `meeting-artifacts` generic collector for authorized local
  meeting minutes/transcript files.
- `meeting-minutes` lens now has a fixture proving investment meetings are kept
  and unrelated logistics meetings are filtered.
- Real local candidate validation produced 10 generic meeting events and 10
  investor-meeting lens events.
- Platform API adapters for Feishu/DingTalk/WeCom/Tencent Meeting are still not
  done.

### Wave E2: P1 meeting artifacts platform-export pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-meeting-platform-validation-2026-07-08.md`

Findings:

- Upgraded `meeting-artifacts` to `0.2.0`.
- Added HTML, CSV, and TSV parsing for user-authorized platform exports.
- Normalizes Feishu, DingTalk, WeCom, and Tencent Meeting platform evidence
  into stable platform values.
- Captures participants, organizer, meeting URL, start/end time, text preview,
  and attachment refs when present.
- Filters credential-like raw fields before writing lake events.
- Fixture validation covers DingTalk JSON, WeCom CSV, and Tencent Meeting HTML.
- Real platform account/API validation is still pending user-authorized access.

### Wave F: P1 WeChat favorites productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-wechat-favorites-validation-2026-07-08.md`

Findings:

- Added runnable `wechat-favorites` generic collector for authorized local
  favorites/saved-article exports.
- `wechat-article-favorites` lens now has a fixture proving investment articles
  are kept and lifestyle articles are filtered.
- Tightened ASCII finance-term matching to avoid false positives such as `PE`
  matching inside ordinary field names.
- Real local saved-article validation produced 17 generic article events and 8
  investor-article lens events.
- Real WeChat favorites database/public-account read-history adapters are still
  not done.

### Wave G: P1 financial news usage productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-financial-news-validation-2026-07-08.md`

Findings:

- Added runnable `financial-news-usage` vertical collector for authorized local
  finance-news usage exports and saved pages.
- Captures read, favorite, subscribe, search, and alert actions without crawling
  public news content.
- Fixture validation covers CLS, WallstreetCN, Gelonghui, and saved HTML.
- Real local candidate validation produced 41 usage events from 16 candidate
  files.
- Platform inference remains partial: 25 real local events were `unknown`.

### Wave G2: P1 financial news browser-history pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-financial-news-browser-history-validation-2026-07-08.md`

Findings:

- Upgraded `financial-news-usage` to `0.2.0`.
- Added read-only Chromium `History` and Safari `History.db` parsing for
  user-authorized browser history copies.
- Filters browser history to CLS, WallstreetCN, and Gelonghui domains before
  writing events.
- Captures domain, source app, URL, title, visit time, visit count, typed
  count, browser transition, tags, symbols, and article ID where present.
- Strengthened platform/action normalization and recursive raw-field
  sanitization.
- Fixture validation proves ordinary non-finance browsing history is excluded.
- Real app/account adapters and real subscription/alert stores remain pending.

### Wave H: P2 HK/US brokerage productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-validation-2026-07-08.md`

Findings:

- Added runnable `hk-us-brokerage` vertical collector for authorized read-only
  Futu/Tiger/IBKR exports.
- Fixture validation covers asset snapshots, positions, executions, orders,
  cashflows, numeric fields, and strong-trade evidence output.
- Real local candidate search found 5 candidate files, but none were valid
  read-only brokerage exports; the collector emitted a gap event and did not
  enter FinClaw.

### Wave H2: P2 HK/US brokerage export package pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-export-package-validation-2026-07-08.md`

Findings:

- Upgraded `hk-us-brokerage` to `0.2.0`.
- Added XLSX/XLSM workbook parsing with per-sheet section inference.
- Expanded multi-section JSON packages so assets, positions, executions,
  orders, cashflows, dividends, and FX can be collected in one run.
- Added richer strong-trade fields: net liquidation, available/settled cash,
  margin, tax, gross/net amounts, settlement dates, order type, time in force,
  FX from/to currencies and amounts, exchange rate, ISIN/CUSIP.
- Strengthened broker/status/field-name normalization, numeric parsing, and
  recursive raw-field sanitization.
- Fixture validation covers Tiger-style nested statements and Futu-style Excel
  positions/dividends.
- Real broker account/export validation remains pending.

### Wave I: P2 professional terminal usage productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-pro-terminal-validation-2026-07-08.md`

Findings:

- Added runnable `pro-terminal-usage` vertical collector for authorized
  Wind/Choice/iFinD/Bloomberg workflow exports.
- Fixture validation covers workspaces, watchlists, searches, downloads,
  model templates, factor attention, and license-safe evidence output.
- Real local candidate validation produced 20 workflow events, but only 9 were
  clearly recognized as Wind; the run is not enough to claim native licensed
  terminal validation.

### Wave I2: P2 professional terminal export package pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-pro-terminal-export-package-validation-2026-07-08.md`

Findings:

- Upgraded `pro-terminal-usage` to `0.2.0`.
- Added XLSX/XLSM workbook parsing for authorized terminal workflow exports.
- Expanded multi-section JSON packages so workspaces, dashboards, watchlists,
  searches, downloads, exports, templates, models, factors, and indicators can
  be collected in one run.
- Added richer workflow metadata fields: source section, project/strategy,
  function code, menu path, universe, regions, datasets, fields, frequency,
  date range, download format, file name, and file path hint.
- Strengthened field-name normalization, list parsing, recursive secret/license
  filtering, and content/body preview capping.
- Fixture validation covers Bloomberg-style nested workflow packages and
  Choice/Wind-style Excel workflow sheets.
- Real licensed terminal export validation remains pending.

### Wave J: P2 social activity productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-social-activity-validation-2026-07-08.md`

Findings:

- Added runnable `social-activity` generic collector for authorized
  Weibo/Bilibili/Xiaohongshu activity exports and saved records.
- Fixture validation covers follows, likes, favorites/watch history, comments,
  saved pages, and investment-lens filtering.
- Broad local keyword validation was rejected as too noisy; strict local
  candidate validation produced 1 generic event and 1 weak investor-influence
  lens event.
- The lens intentionally produced no `usable_for_wiki_now` subdimensions because
  social activity is weak influence evidence unless corroborated.

### Wave J2: P2 social activity weak-evidence package pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-social-activity-weak-evidence-validation-2026-07-08.md`

Findings:

- Upgraded `social-activity` to `0.2.0`.
- Added XLSX/XLSM workbook parsing for authorized social activity exports.
- Expanded multi-section JSON packages so follows, likes, favorites,
  watch-history, comments, shares, and reposts can be collected in one run.
- Added creator IDs/URLs, domains, item IDs, symbols, engagement counts, watch
  progress, and source sections.
- Every event now carries weak-evidence policy fields:
  `evidence_role=weak_influence_signal`, `investment_claim_allowed=false`, and
  `requires_corroboration=true`.
- Manifest readiness now records `evidence_strength=weak_attention` and
  `collector_claims_investment_conclusion=false`.
- Strengthened platform URL inference, field-name normalization, list parsing,
  recursive credential filtering, and content/comment preview capping.
- Fixture validation covers Xiaohongshu nested packages and Bilibili/Weibo Excel
  activity sheets.

### Wave K: P1 DingTalk/WeCom collaboration exports pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-collaboration-exports-validation-2026-07-08.md`

Findings:

- Added runnable `collaboration-exports` generic skill for `dingtalk` and
  `wecom`.
- Replaced `dingtalk` and `wecom` YAML-only placeholders with a real shared CLI:
  `collaboration_exports.py collect --platform dingtalk|wecom`.
- Supports authorized JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, and TXT
  exports.
- Captures messages, chats, contacts, file refs, meeting refs, sender/receiver,
  departments, participants, meeting links, file names, tags, and content
  previews.
- Emits `collectorx.event.v1` with collector IDs matching the channel:
  `dingtalk` or `wecom`.
- Generic collaboration events route to internal collaboration Wiki targets;
  investment filtering remains in investor lenses.
- Fixture validation covers DingTalk multi-section packages, DingTalk HTML
  meeting refs, WeCom CSV messages/meetings, gap events, and credential-key
  sanitization.

### Wave L: Tonghuashun watchlist productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-ths-watchlist-validation-2026-07-08.md`

Findings:

- Added runnable `ths-watchlist` vertical skill for user-authorized
  Tonghuashun watchlist exports.
- Replaced the previous YAML-only README placeholder with a real CLI:
  `ths_watchlist.py collect --input <authorized-export> --out-dir <out>`.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, and TXT
  inputs.
- Captures symbol, name, market, group, industry, tags, reason/note, added
  time, source section, and sanitized raw metadata.
- Emits `collectorx.event.v1` watchlist events into `lake/ths-watchlist`.
- Treats watchlists as attention-universe evidence only; it does not claim
  holdings, trades, orders, or fund flows.
- Fixture validation covers mixed CSV/JSON/XLSX/TXT inputs, missing-input gap
  events, credential-key sanitization, and non-A-share code handling.

### Wave M: Xueqiu watchlist productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-xueqiu-watchlist-validation-2026-07-08.md`

Findings:

- Upgraded `xueqiu-watchlist` from a draft CSV parser to a runnable vertical
  baseline collector.
- Added a standard CLI: `xueqiu_query.py collect --input <authorized-export>
  --out-dir <out>`.
- Preserved the legacy `--file/--export/--list` JSON workflow.
- Supports CSV/TSV, JSON/JSONL/NDJSON, XLSX/XLSM, HTML, Markdown, and TXT
  watchlist inputs.
- Captures symbol, code, market, name, group, industry, tags, note/reason,
  followed time, source section, and sanitized raw metadata.
- Emits `collectorx.event.v1` watchlist events into `lake/xueqiu-watchlist`.
- Treats watchlists as attention-universe evidence only; broader posts,
  comments, favorites, and portfolio activity stay in `xueqiu-investor-activity`.
- Fixture validation covers mixed CSV/JSON/XLSX/TXT inputs, gap events, legacy
  export compatibility, credential-key sanitization, and A/HK symbol handling.

### Wave N: P0 email local import productization pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-email-import-validation-2026-07-08.md`

Findings:

- Added `email_api.py import` for user-authorized local email exports.
- Supports EML, MBOX, JSON/JSONL/NDJSON, CSV, and TSV inputs.
- Writes a standard package with `lake/email/events.jsonl`, `manifest.json`,
  and `SUMMARY.md`.
- Captures sender, recipients, cc, subject, date, body preview, message ID,
  folder/mailbox, and attachment refs.
- Full body remains opt-in via `--event-include-body`; attachment bodies are not
  written into events.
- Fixture validation covers mixed EML/JSON/CSV imports, attachment refs,
  missing-input gap events, and legacy IMAP event paths.

### Wave N2: P0 email package and research-attachment pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-email-package-validation-2026-07-08.md`

Findings:

- Added authorized ZIP package import for EML, MBOX, JSON/JSONL/NDJSON, CSV, and
  TSV email exports.
- ZIP imports preserve `archive.zip::member` provenance and skip unsafe path
  traversal members.
- Generic `email` events now sanitize attachment refs and `raw_ref` so token,
  cookie, password, secret, session, and authorization keys do not leak into
  lake events.
- IMAP collection now carries attachment metadata refs in the same safe format
  as local imports.
- Email import manifests now include body policy, attachment policy, and
  collection audit fields for file/archive counts.
- `email-research` now scores clear research attachment filenames, so a broker
  report attached to a plain email can still become investor evidence.
- Fixture validation covers ZIP import, archive traversal skipping, raw ref and
  attachment sanitization, IMAP attachment refs, and research-attachment lens
  matching.

### Wave N3: P0 email local import source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-email-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `email-collector` to `0.5.1` and aligned `.collectorx.json` with
  `baseline+audit`.
- Added `source_type=authorized_email_export` and path-level audit fields for
  requested inputs, missing inputs, resolved files, extension counts, skipped
  file counts, skipped reasons, parsed/imported counts, and limit truncation.
- Added ZIP member reason audit for unsafe paths, Windows drive paths,
  unsupported extensions, parse errors, imported member email counts, and
  unvisited members when `--limit` truncates collection.
- Kept IMAP package behavior unchanged while making local import manifests as
  explainable as the later package collectors.
- Fixture validation covers mixed EML/JSON/CSV import, unsupported file skips,
  missing input gap audit, ZIP provenance, POSIX traversal, Windows drive member
  refusal, unsupported ZIP members, ZIP limit accounting, sanitized attachment
  refs, and no-full-body policy.

### Wave N4: P0 email Apple Mail and Maildir local import pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-email-local-formats-validation-2026-07-08.md`

Findings:

- Upgraded `email-collector` to `0.5.2`.
- Added Apple Mail `.emlx` import for user-authorized local exports. The parser
  strips the Apple Mail byte-count prefix before reading the RFC822 message.
- Added Maildir `cur/` and `new/` message import for Linux/server-style local
  exports. Maildir detection requires RFC822-like headers so ordinary
  extensionless files remain skipped.
- Added ZIP support for `.emlx` and Maildir members while preserving
  `archive.zip::member` provenance.
- Manifest audit now records Apple Mail EMLX file count, Maildir message file
  count, `<maildir>` extension coverage, per-file parser names, and ZIP member
  extension counts for these local formats.
- Fixture validation covers folder import, ZIP import, no-full-body policy,
  unsupported extensionless noise skipping, and raw-ref `format` values
  (`emlx`, `maildir`).
- Current local machine still has no registered mailbox, so this pass improves
  local authorized export coverage without claiming live mailbox validation.

### Wave O: P0 filesystem cross-platform manifest pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-filesystem-cross-platform-validation-2026-07-08.md`

Findings:

- Added a testable `platform_default_root_plan` for macOS, Windows, and Linux
  default document roots.
- Manifest output now records default-root plans and collection readiness.
- Fixture validation proves the collector remains metadata-only and does not
  read content.
- Fixture validation covers macOS iCloud Drive, Windows OneDrive, and Linux
  default root behavior at code level.
- This is not a real Windows/Linux device validation claim; it closes the
  code-level simulation gap.

### Wave O2: P0 filesystem source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p0-filesystem-source-audit-validation-2026-07-08.md`

Findings:

- Added `scan_files_with_audit` while keeping the existing `scan_files` API
  compatible.
- `filesystem_query.py collect --out-dir` now writes
  `manifest.source_audit` with requested/resolved roots, missing roots,
  scanned/emitted file counts, extension coverage, skipped file/directory
  counts, skipped reasons, size policy, ignored directories, limit status, and
  per-root scan results.
- The collector remains metadata-only and does not route every local file into
  investor Wiki evidence; `research-documents` still owns investment filtering
  and explicit content extraction.
- Fixture validation covers unsupported extensions, hidden files, ignored
  directories, missing roots, package output, and cross-platform default-root
  planning.

### Wave P: P0 China wealth platform coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p0-china-wealth-platform-coverage-validation-2026-07-08.md`

Findings:

- Added `manifest.platform_coverage` to `china-wealth-assets`.
- The manifest now lists expected P0 platforms: Alipay, Tiantian Fund, Danjuan,
  Qieman, and bank wealth.
- The manifest records observed platforms, missing expected platforms, unknown
  event count, and `real_account_validation=false`.
- Fixture validation proves partial platform coverage and all-expected-platform
  input coverage are reported separately from complete asset-boundary claims.

### Wave Q: P1 notes platform coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-notes-platform-coverage-validation-2026-07-08.md`

Findings:

- Added authorized ZIP export import for common Notion/Youdao/Evernote/Markdown
  note packages.
- Added `manifest.platform_coverage` to `notes-collector`, including expected
  P1 note platforms, observed platforms, missing platforms, source counts,
  unknown count, and `real_account_validation=false`.
- Added Obsidian source inference for authorized export folders.
- Added Notion `--token-env` so FinClaw can authorize API collection without
  placing tokens in command history.
- Fixture validation now proves partial platform coverage, all-expected-platform
  coverage, and ZIP path traversal skipping.

### Wave Q2: P1 notes audit and content policy pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-notes-audit-validation-2026-07-08.md`

Findings:

- Added note event metadata for `content_length`, `content_digest`,
  `content_included`, URL, and ZIP provenance in `raw_ref`.
- Added `manifest.field_coverage` for source app, title, path, content preview,
  content length, tags, URL, and event time.
- Added `manifest.source_audit` and `manifest.content_policy` so FinClaw can
  distinguish preview-only runs from explicit full-content authorization and can
  detect ZIP member provenance.
- Strengthened ZIP member safety for POSIX traversal, absolute paths, backslash
  paths, and Windows drive-letter members.
- Kept the generic/lens boundary explicit: notes can enter Lake, but only
  `investment-notes` can classify investment notes for Wiki evidence.

### Wave Q3: P1 notes source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-notes-source-audit-validation-2026-07-08.md`

Findings:

- Added `parse_notes_export_with_audit` while keeping the existing
  `parse_notes_export` API compatible.
- `notes_api.py obsidian/import --out-dir` now writes `manifest.source_audit`
  with input kind, resolved files, extension coverage, parsed/emitted counts,
  skipped file reasons, ZIP member counts, skipped ZIP member reasons,
  path-level parse results, limit status, and path-safety flags.
- Obsidian vault collection now records per-file parse status instead of only
  event-derived source references.
- The generic/lens boundary remains explicit: generic notes enter Lake, while
  `investment-notes` classifies investment relevance for Wiki evidence.
- Fixture validation covers Obsidian vault audit, unsupported import files,
  all expected P1 note platforms, ZIP unsafe member skipping, and preview-only
  content policy.

### Wave Q3b: P1 notes table export import pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-notes-table-import-validation-2026-07-08.md`

Findings:

- Upgraded `notes-collector` to `0.2.4`.
- Added CSV/TSV import for user-authorized note table exports, including
  Notion database exports, investment rules tables, review templates, valuation
  assumption tables, and research checklists.
- Table rows are normalized into generic `notes` events. Title columns prefer
  `title/name/标题/名称`; content columns prefer
  `content/text/正文/内容/备注/notes`; other non-metadata columns are appended to
  the content preview so table fields are not silently dropped.
- Added ZIP support for CSV/TSV note table members while preserving
  `source_archive` and `archive_member` provenance.
- Manifest `source_audit` now records `table_import_supported`,
  `table_file_count`, `table_row_count`, and `table_note_count`.
- Fixture validation covers Notion-style CSV databases, TSV table members in
  ZIP packages, Notion source inference, table row counts, preview-only policy,
  and generic/lens boundary preservation.
- Real Notion/Youdao/Evernote account exports and mixed-note false-positive
  backtesting remain pending.

### Wave Q4: P1 investment notes surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-investment-notes-surface-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.5`.
- Added `investment-notes` classification fields for review notes, rules
  libraries, trade checklists, valuation assumptions, and research notes.
- Added `manifest.lens_surface_summary` and evidence
  `coverage_summary.source_surface_summary` for note-type counts, source-app
  counts, upstream collector counts, matched-symbol counts, preview/full-content
  counts, and tagged/path/URL coverage.
- Fixture validation reads upstream `notes` events, filters a life note, keeps
  three investment notes, and proves surface propagation into manifest and
  `finclaw.investor_wiki_evidence.v1`.
- Real Notion/Youdao/Evernote account validation and real mixed-note
  false-positive backtesting remain pending.

### Wave R0: P1 task-calendar surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-task-calendar-surface-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.6`.
- Added `task-calendar-investor` classification fields for research tasks,
  trade plans, review reminders, earnings calendar items, research meetings,
  and risk checks.
- Added `manifest.lens_surface_summary` and evidence
  `coverage_summary.source_surface_summary` for surface counts, upstream
  collector counts, kind counts, source app/platform counts, time/reminder
  coverage, meeting URL coverage, and project/calendar grouping coverage.
- Fixture validation reads upstream `ticktick` and `calendar` events, filters a
  life calendar item, keeps four investment task/calendar items, and proves
  surface propagation into manifest and `finclaw.investor_wiki_evidence.v1`.
- Real TickTick/Dida OAuth, real calendar account validation, and mixed-corpus
  false-positive backtesting remain pending.

### Wave R: P1 task/calendar platform coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-task-calendar-platform-coverage-validation-2026-07-08.md`

Findings:

- Added authorized ZIP export import to `calendar-collector` and
  `ticktick_events.py`.
- Added `manifest.platform_coverage` to generic `calendar` packages for Apple,
  Google, Outlook, Feishu, DingTalk, WeCom, Tencent Meeting, and generic
  calendar exports.
- Added `manifest.platform_coverage` to generic `ticktick` packages for
  TickTick/Dida source coverage.
- Added source fields (`source_platform`/`source_app`) to task and calendar
  events so FinClaw can see which platform each event came from before lens
  filtering.
- Hardened TickTick event raw snapshots to remove credential-like fields.
- Fixture validation covers partial coverage, all expected calendar platforms,
  Dida ZIP exports, and ZIP path traversal skipping.

### Wave R2: P1 task/calendar audit and time-surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-task-calendar-audit-validation-2026-07-08.md`

Findings:

- Added `manifest.field_coverage` to both task and calendar packages so FinClaw
  can inspect title, source, project/calendar, status, start/due/end,
  recurrence, reminders, attendees, and meeting URL coverage.
- Added TickTick/Dida `time_status_summary` for pending/completed/overdue tasks,
  start/due/completion coverage, recurrence, and reminders.
- Added calendar `time_surface_summary` for start/end, all-day, meeting URL,
  location, attendees, recurrence, and reminders.
- Preserved ZIP `source_archive` and `archive_member` in task/calendar raw
  references and strengthened ZIP safety for POSIX traversal, backslash
  traversal, absolute paths, and Windows drive-letter members.
- Kept the generic/lens boundary explicit: task/calendar events enter Lake, but
  only `task-calendar-investor` can classify trading plans, research tasks, and
  review reminders for Wiki evidence.

### Wave R3: P1 task/calendar source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-task-calendar-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `calendar-collector` to `0.2.0` and `ticktick-cli` event import to
  `0.1.9`.
- Added package-level source audit fields for input count, resolved file count,
  top-level extension counts, parsed record count, emitted event count, and
  path-level parse results.
- Added ZIP member audit fields for total member count, member extension
  counts, skipped member count, skipped member extension counts, and skip
  reason counts.
- Updated package summaries to surface skipped archive members.
- Fixture tests now assert gap output and safe/unsafe ZIP accounting for both
  generic calendar exports and TickTick/Dida task exports.

### Wave R4: P1 calendar time-quality and conflict pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-calendar-time-quality-validation-2026-07-08.md`

Findings:

- Upgraded `calendar-collector` to `0.2.1`.
- Calendar events now include `has_time_range`, `time_order_valid`,
  `duration_minutes`, and `is_multi_day` when start/end fields can be parsed.
- `manifest.time_surface_summary` now reports duration coverage, missing
  start/end fields, invalid time ranges, all-day/multi-day counts, missing
  meeting/reminder signals, and same-calendar conflict pairs without exposing
  event titles in conflict samples.
- `task-calendar-investor` lens summaries now preserve duration, multi-day, and
  invalid-time counts so FinClaw can inspect planning evidence quality before
  Wiki distillation.
- Fixture validation covers ICS duration, CSV overlap detection, invalid end
  before start, cross-night schedules, and lens evidence propagation.
- This improves P1 planning/review evidence quality, but still does not claim
  real TickTick OAuth validation or real Apple/Google/Outlook/Feishu/DingTalk/
  WeCom/Tencent Meeting account validation.

### Wave R5: P1 task/calendar boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-task-calendar-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.13`.
- Added `manifest.task_calendar_boundary_proof` for
  `task-calendar-investor`.
- The proof records authorized input counts, candidate/matched/filtered counts,
  upstream task/calendar source counts, source app/platform counts, time,
  due/start, reminder, meeting URL, project/calendar, duration, multi-day,
  invalid-time, completed-task, and overdue-task boundaries.
- The proof explicitly does not claim a complete task list, complete calendar,
  complete task/calendar context, direct task/calendar reconnect, or direct Wiki
  writes.
- Fixture validation reads mixed `ticktick` and `calendar` events, filters one
  life-calendar item, keeps four investment task/calendar items, and proves the
  boundary proof appears in `manifest.json`.
- This improves P1 task/calendar Wiki safety, but still does not claim real
  TickTick OAuth validation, real calendar account validation, or mixed-corpus
  false-positive backtesting.

### Wave S: P1 meeting artifacts platform coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-meeting-platform-coverage-validation-2026-07-08.md`

Findings:

- Added authorized ZIP export import to `meeting-artifacts`.
- Added `manifest.platform_coverage` for expected P1 meeting platforms:
  Feishu, DingTalk, WeCom, and Tencent Meeting.
- Preserved archive member paths in `raw_ref.path` as `archive.zip::member`.
- Updated package summary with observed and missing meeting platforms.
- Fixture validation covers local-file partial coverage, all expected meeting
  platforms, credential filtering, and ZIP path traversal skipping.

### Wave S2: P1 meeting and collaboration audit pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-meeting-collaboration-audit-validation-2026-07-08.md`

Findings:

- Added `manifest.field_coverage`, `meeting_surface_summary`, `source_audit`,
  and `evidence_policy` to `meeting-artifacts`.
- Added ZIP provenance to `meeting-artifacts` raw refs and strengthened ZIP
  safety for POSIX traversal, backslash traversal, absolute paths, and Windows
  drive-letter members.
- Added ZIP import support to `collaboration-exports` for DingTalk/WeCom
  authorized packages.
- Added collaboration `field_coverage`, `collaboration_surface_summary`,
  `source_audit`, and generic-collector evidence policy.
- Kept the generic/lens boundary explicit: meeting/collaboration events enter
  Lake, but `meeting-minutes` and related lenses classify investment evidence
  before Wiki use.

### Wave S3: P1 meeting and collaboration source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-meeting-collaboration-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `meeting-artifacts` to `0.3.0` and `collaboration-exports` to
  `0.2.0`.
- Added package-level source audit fields for input count, resolved file count,
  top-level extension counts, parsed record count, emitted event count, and
  path-level parse results.
- Added ZIP member audit fields for total member count, member extension
  counts, skipped member count, skipped member extension counts, and skip
  reason counts.
- Updated package summaries to surface skipped archive members.
- Fixture tests now assert the safe member is collected while POSIX traversal,
  backslash traversal, and Windows drive-letter ZIP members are skipped and
  counted.

### Wave S4: P1 Feishu CollectorX package pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-feishu-collector-package-validation-2026-07-08.md`

Findings:

- Upgraded `feishu` from migrated-review utility status to `0.2.0`
  `baseline+audit`.
- Kept legacy Feishu OAuth/API commands intact and added a read-only
  `feishu_api.py collect` path for authorized local exports.
- Added parsing for JSON/JSONL/NDJSON, CSV/TSV, HTML, Markdown, TXT, and ZIP
  Feishu exports.
- Added standard output package: `lake/feishu/events.jsonl`, `manifest.json`,
  and `SUMMARY.md`.
- Manifest now reports field coverage, Feishu surface summary, source audit,
  ZIP skipped-member counts/reasons, path-level parse results, and generic/lens
  evidence policy.
- Fixture validation covers messages, documents, file refs, meetings,
  recordings, credential filtering, gap output, and ZIP traversal safety.

### Wave S5: P1 meeting-minutes surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-meeting-minutes-surface-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.7`.
- Added `meeting-minutes` surface classification for roadshow minutes,
  research meetings, investment committee records, expert calls, earnings
  calls, decision points, risk discussions, and follow-up actions.
- Added manifest/evidence `meeting_minutes_surface_summary` fields for
  expected/missing surfaces, primary surface counts, upstream collectors,
  source platforms, participants, meeting URLs, attachment refs, recording
  refs, symbol matches, and time coverage.
- Added a mixed upstream fixture for `meeting-artifacts`, `feishu`,
  `dingtalk`, and `wecom`, plus a non-investment meeting that must be filtered
  out before Wiki evidence generation.

### Wave S6: P1 meeting-minutes boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-meeting-minutes-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.14`.
- Added `manifest.meeting_minutes_boundary_proof` for `meeting-minutes`.
- The proof records authorized input counts, candidate/matched/filtered counts,
  upstream meeting/collaboration source counts, source platform counts,
  participant coverage, meeting-link coverage, attachment/recording reference
  coverage, symbol matches, and time coverage.
- The proof explicitly does not claim complete meeting history, complete
  workspace coverage, complete meeting context, default recording-body
  collection, direct meeting-platform reconnect, or direct Wiki writes.
- Fixture validation reads mixed `meeting-artifacts`, `feishu`, `dingtalk`, and
  `wecom` events, filters one non-investment meeting, keeps four investment
  meeting events, and proves the boundary proof appears in `manifest.json`.
- This improves P1 meeting Wiki safety, but still does not claim real
  Feishu/DingTalk/WeCom/Tencent Meeting account validation, participant identity
  normalization, recording-body authorization, or false-positive backtesting.

### Wave T: P1 WeChat favorites action coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-wechat-favorites-action-coverage-validation-2026-07-08.md`

Findings:

- Added authorized ZIP export import to `wechat-favorites`.
- Added `manifest.action_coverage` for expected user actions: favorite, read,
  share, and saved file.
- Preserved file/ZIP member provenance in `raw_ref.path`.
- Added source account count to the manifest without claiming investment
  article status.
- Fixture validation covers JSON favorites, HTML saved public-account article,
  ZIP shared article, credential filtering, and ZIP path traversal skipping.

### Wave T2: P1 WeChat favorites audit and source pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-wechat-favorites-audit-validation-2026-07-08.md`

Findings:

- Added per-event `text_length` and archive member/source archive provenance
  in `raw_ref`.
- Added `manifest.field_coverage` for item type, action type, title, source
  account, URL, action time, tags, text preview, and event time.
- Added `manifest.article_surface_summary` so FinClaw can see URL, source
  account, tag, text, and public-account article availability before lensing.
- Added `manifest.source_audit`, `manifest.content_policy`, and
  `manifest.evidence_policy` to keep the generic collector/Lake/lens boundary
  explicit.
- Hardened ZIP import against POSIX traversal and Windows drive/traversal
  members.

### Wave T3: P1 WeChat favorites source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-wechat-favorites-source-audit-validation-2026-07-08.md`

Findings:

- Added `collect_records_with_audit` while keeping the existing `parse_path`
  and `parse_zip` APIs compatible.
- `wechat_favorites.py collect --out-dir` now writes `manifest.source_audit`
  with requested inputs, missing inputs, resolved files, extension coverage,
  parsed/emitted counts, skipped file reasons, ZIP member counts, skipped ZIP
  member reasons, path-level parse results, limit status, and path-safety
  flags.
- Missing input now produces both a gap event and an auditable
  `input_missing` reason instead of only a zero-result package.
- The generic/lens boundary remains explicit: saved article and action events
  enter Lake, while `wechat-article-favorites` classifies investment relevance
  for Wiki evidence.
- Fixture validation covers favorite/read/share/saved-file actions,
  unsupported input files, unsafe ZIP members, missing input gap audit,
  credential-key filtering, and preview-only content policy.

### Wave T4: P1 WeChat article lens surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-wechat-article-surface-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.8`.
- Added `wechat-article-favorites` surface classification for broker research,
  company fundamentals, market strategy, industry themes, valuation methods,
  portfolio cases, risk warnings, and macro policy.
- Added manifest/evidence `wechat_article_surface_summary` fields for
  expected/missing surfaces, primary surface counts, saved/read/share/saved-file
  actions, item types, upstream collectors, source-account type counts,
  source-account count, public-account article count, URL/tag/text/time
  coverage, and symbol matches.
- Added a mixed upstream fixture with four user article actions plus one
  non-investment saved article that must be filtered out.

### Wave T5: P1 WeChat article boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-wechat-article-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `investor-source-collectors` to `0.1.15`.
- Added `manifest.wechat_article_boundary_proof` for
  `wechat-article-favorites`.
- The proof records authorized input counts, candidate/matched/filtered counts,
  upstream `wechat-favorites` source counts, saved/read/share/saved-file action
  counts, public-account article counts, source-account type counts, URL/tag/
  text/action-time coverage, and symbol matches.
- The proof explicitly does not claim complete WeChat favorites, complete
  WeChat read history, public-account full crawl, public article body mirroring,
  direct WeChat reconnect, or direct Wiki writes.
- Fixture validation reads five upstream WeChat favorite/article actions,
  filters one non-investment saved article, keeps four investment article
  actions, and proves the boundary proof appears in `manifest.json`.
- This improves P1 WeChat article Wiki safety, but still does not claim real
  WeChat favorites database validation, public-account read-history validation,
  account/tag allowlists, or false-positive backtesting.

### Wave U: P1 financial news usage coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p1-financial-news-usage-coverage-validation-2026-07-08.md`

Findings:

- Added authorized ZIP export import to `financial-news-usage`.
- Added `manifest.platform_coverage` for CLS, WallstreetCN, and Gelonghui.
- Added `manifest.action_coverage` for read, favorite, search, subscribe, and
  alert actions.
- Preserved file/ZIP member provenance in `raw_ref.path` as
  `archive.zip::member`.
- Kept the collector scoped to user usage traces; it still does not crawl or
  mirror public news content.
- Fixture validation covers JSON usage, saved HTML page, ZIP alert event,
  credential filtering, browser-history finance-domain filtering, and ZIP path
  traversal skipping.

### Wave U2: P1 financial news usage audit and source pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-financial-news-usage-audit-validation-2026-07-08.md`

Findings:

- Added per-event `text_length`, ZIP `source_archive`, and `archive_member`
  provenance.
- Added `manifest.field_coverage` for action, platform, title, URL, domain,
  source app, source, channel, query, symbols, tags, article ID, text preview,
  and event time.
- Added `manifest.usage_surface_summary` for URL/domain coverage, source apps,
  source/channel coverage, queries, symbols, tags, text, browser-history events,
  alerts, and subscriptions.
- Added `manifest.source_audit`, `manifest.content_policy`, and
  `manifest.evidence_policy` to keep personal usage evidence separate from
  public news crawling.
- Hardened ZIP import against POSIX traversal and Windows drive/traversal
  members.

### Wave U3: P1 financial news usage source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-financial-news-usage-source-audit-validation-2026-07-08.md`

Findings:

- Added `collect_from_inputs_with_audit` while keeping the existing
  `collect_from_inputs` API compatible.
- `financial_news_usage.py collect --out-dir` now writes
  `manifest.source_audit` with requested inputs, missing inputs, resolved
  files, extension coverage, parsed/emitted counts, skipped file reasons, ZIP
  member counts, skipped ZIP member reasons, browser-history source apps,
  path-level parse results, limit status, and path-safety flags.
- Missing input now produces both a gap event and an auditable `input_missing`
  reason.
- Browser history remains domain-filtered to CLS, WallstreetCN, and Gelonghui.
- Personal usage boundary remains explicit: no public news crawling or news
  corpus mirroring.
- Fixture validation covers JSON usage, saved HTML page, ZIP alert event,
  Chromium history, unsupported input files, unsafe ZIP members, missing input
  gap audit, credential filtering, and content/evidence policy.

### Wave U4: P1 financial news usage topic surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-financial-news-topic-surface-validation-2026-07-08.md`

Findings:

- Upgraded `financial-news-usage` to `0.2.4`.
- Added per-event `usage_topics`, `primary_usage_topic`, and
  `usage_topic_terms`.
- Added manifest/evidence usage topic summaries for macro policy, market
  strategy, industry themes, company fundamentals, HK/US markets, risk events,
  trading opportunities, and portfolio alerts.
- Tightened topic terms during validation so `风险偏好` is not counted as a
  risk event and a generic `电报` channel is not counted as a trading
  opportunity.
- Fixture validation covers platform/action/topic coverage, browser-history
  domain filtering, ZIP alert provenance, unsafe ZIP member skipping, and
  content/evidence policy.

### Wave U5: P1 financial news usage boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-financial-news-usage-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `financial-news-usage` to `0.2.5`.
- Added `manifest.usage_boundary_proof`.
- The proof records authorized input counts, parsed/emitted counts,
  platform/action/topic coverage, source refs, ZIP member safety, browser
  history source apps, domain-filtered browser-history event counts, content
  pointer coverage, alert/subscription counts, and limit/missing-input status.
- The proof explicitly does not claim complete usage history, complete account
  boundary, public news full crawl, public article body mirroring,
  platform-wide data, unrelated browser history collection, app/account
  reconnect, or direct Wiki writes.
- Fixture validation covers normal authorized exports, ZIP alert provenance,
  Chromium browser-history domain filtering, missing input gap behavior, and
  proof-level transitions.
- This improves P1 finance-news usage evidence safety, but still does not claim
  real CLS/WallstreetCN/Gelonghui app cache validation, account APIs,
  subscription-store adapters, Safari/Windows/Linux history validation, or
  topic false-positive review on noisy real exports.

### Wave V: P2 HK/US brokerage coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-coverage-validation-2026-07-08.md`

Findings:

- Upgraded `hk-us-brokerage` to `0.2.1`.
- Added authorized ZIP package import for CSV/TSV, JSON/JSONL/NDJSON, XLSX, and
  XLSM broker statement members.
- Added `manifest.broker_coverage` for Futu, Tiger, and IBKR.
- Added `manifest.trade_surface_coverage` for assets, positions, executions,
  orders, cashflows, dividends, and FX.
- Added `manifest.field_coverage` for recommended strong numeric/business
  fields, including margin, tax, settlement dates, gross/net amounts, FX
  amounts, and exchange rate.
- Preserved file/ZIP member provenance in `raw_ref.path` as
  `archive.zip::member`.
- Fixture validation covers Futu CSV, Tiger nested JSON, Futu XLSX, IBKR ZIP,
  credential filtering, all expected brokers, all expected trade surfaces, all
  recommended strong fields, and ZIP path traversal skipping.

### Wave V2: P2 HK/US brokerage audit and value pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-audit-validation-2026-07-08.md`

Findings:

- Added ZIP `source_archive` and `archive_member` provenance to raw refs.
- Added `manifest.strong_trade_surface_summary` for assets, positions,
  executions, orders, cashflows, dividends, FX, account IDs, currencies,
  symbols, amounts, fees, tax, margin, and PnL availability.
- Added `manifest.asset_value_summary` with reported total assets, cash, and
  buying power by currency, plus multi-currency observation.
- Added `manifest.source_audit` for source refs, archive member events, archive
  count, and section/sheet provenance.
- Added `manifest.evidence_policy` to keep the collector read-only and explicit
  that no complete brokerage boundary is claimed without real account
  validation.
- Hardened ZIP import against POSIX traversal and Windows drive/traversal
  members.

### Wave V3: P2 HK/US brokerage source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-source-audit-validation-2026-07-08.md`

Findings:

- Added `collect_from_inputs_with_audit` while keeping the existing
  `collect_from_inputs` API compatible.
- `hk_us_brokerage.py collect --out-dir` now writes `manifest.source_audit`
  with requested inputs, missing inputs, resolved files, extension coverage,
  parsed/emitted counts, skipped file reasons, ZIP member counts, skipped ZIP
  member reasons, path-level parse results, limit status, and path-safety
  flags.
- Missing input now produces both a gap event and an auditable `input_missing`
  reason.
- ZIP limit accounting now reports only records actually emitted to the lake.
- The read-only strong-trade boundary remains explicit: no passwords, cookies,
  tokens, order placement, order cancellation, or complete brokerage-boundary
  claim without real account validation.
- Fixture validation covers Futu CSV, Tiger nested JSON, Futu XLSX, IBKR ZIP,
  unsupported input files, unsafe ZIP members, missing input gap audit,
  credential filtering, ZIP limit accounting, field coverage, value summaries,
  and read-only evidence policy.

### Wave V4: P2 HK/US brokerage account boundary pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-account-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `hk-us-brokerage` to `0.2.4`.
- Added `manifest.account_boundary_summary` and evidence coverage summary for
  broker/account IDs, event counts by account, observed strong-trade subtypes
  by account, per-account missing surfaces, and full-surface account
  candidates.
- Added `manifest.currency_market_summary` for observed currencies, markets,
  broker-currency pairs, broker-market pairs, FX pairs, and multi-currency
  observation.
- Added `manifest.fee_tax_margin_summary` for fee, tax, margin requirement,
  and maintenance margin availability and totals by currency.
- Kept `complete_account_boundary_claimed` false so FinClaw can use exact user
  business numbers from authorized exports without pretending one export proves
  the full broker account boundary.
- Fixture validation covers Futu, Tiger, and IBKR account IDs, a Tiger account
  containing all seven strong-trade surfaces, multi-currency USD/HKD assets and
  FX, tax/fee/margin values, ZIP provenance, unsafe ZIP member skipping, and
  evidence summary routing.

### Wave V5: P2 HK/US brokerage boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-hk-us-brokerage-boundary-proof-validation-2026-07-08.md`

Findings:

- Upgraded `hk-us-brokerage` to `0.2.5`.
- Added `manifest.brokerage_boundary_proof` as the single FinClaw gate for
  authorized input presence, Futu/Tiger/IBKR coverage, strong trade-surface
  coverage, recommended numeric/business fields, account IDs, asset values,
  multi-currency evidence, fee/tax/margin evidence, source audit counts, and
  Investor Wiki flow.
- Added the same brokerage-boundary proof to
  `investor_wiki_evidence.v1.json.coverage_summary` so SoulMirror/FinClaw can
  inspect the proof without opening the raw manifest.
- Kept business numbers unsanitized for user-authorized brokerage facts while
  explicitly keeping false claims off: no complete account boundary, no
  complete brokerage history, no trading password, no order mutation, no
  broker-native API validation, no public community crawl, and no direct Wiki
  write.
- Package `SUMMARY.md` now surfaces the brokerage-boundary proof level.
- Fixture validation covers weak partial, strong partial, and missing-input
  proof levels.

### Wave W: P2 professional terminal coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-pro-terminal-coverage-validation-2026-07-08.md`

Findings:

- Upgraded `pro-terminal-usage` to `0.2.1`.
- Added authorized ZIP package import for JSON/JSONL/NDJSON, CSV/TSV,
  XLSX/XLSM, HTML, Markdown, TXT, INI, CONF, and LOG workflow members.
- Added `manifest.terminal_coverage` for Wind, Choice, iFinD, and Bloomberg.
- Added `manifest.activity_coverage` for workspace, watchlist, search,
  download, model-template, and factor-attention activities.
- Added `manifest.workflow_field_coverage` for recommended workflow metadata:
  workspace, project, module, function code, menu path, query, symbols,
  universe, industries, regions, factors, datasets, fields, template name,
  frequency, date range, download format, and file name.
- Kept the collector scoped to workflow metadata; it still does not mirror
  vendor databases or licensed content bodies.
- Fixture validation covers Wind JSON, Choice HTML, Bloomberg nested JSON,
  Choice/Wind XLSX, iFinD ZIP, credential/license filtering, all expected
  terminals, all expected activities, all recommended workflow fields, and ZIP
  path traversal skipping.

### Wave W2: P2 professional terminal audit and license pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-pro-terminal-audit-validation-2026-07-08.md`

Findings:

- Added ZIP `source_archive` and `archive_member` provenance to raw refs.
- Added per-event `content_length` while keeping content previews capped.
- Added `manifest.workflow_surface_summary` for workspace, project, module,
  function code, menu path, query, symbols, universe, industries, regions,
  factors, datasets, fields, template, download format, content preview, and
  source section availability.
- Added `manifest.source_audit` for source refs, archive member events, archive
  count, and section/sheet provenance.
- Added `manifest.license_policy` and `manifest.evidence_policy` to keep the
  collector scoped to personal workflow metadata, not vendor database mirrors or
  licensed content redistribution.
- Hardened ZIP import against POSIX traversal and Windows drive/traversal
  members.

### Wave W3: P2 professional terminal source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-pro-terminal-source-audit-validation-2026-07-08.md`

Findings:

- Added `collect_from_inputs_with_audit` while keeping the existing
  `collect_from_inputs` API compatible.
- `pro_terminal_usage.py collect --out-dir` now writes `manifest.source_audit`
  with requested inputs, missing inputs, resolved files, extension coverage,
  parsed/emitted counts, skipped file reasons, ZIP member counts, skipped ZIP
  member reasons, path-level parse results, limit status, and path-safety
  flags.
- Missing input now produces both a gap event and an auditable `input_missing`
  reason.
- ZIP limit accounting now reports only records actually emitted to the lake.
- The license-safe workflow boundary remains explicit: no vendor database
  mirrors, licensed content bodies, public market data mirrors, credentials, or
  license material.
- Fixture validation covers Wind JSON, iFinD CSV, Choice HTML, Bloomberg nested
  JSON, Choice/Wind XLSX, iFinD ZIP, unsupported input files, unsafe ZIP
  members, missing input gap audit, credential/license filtering, ZIP limit
  accounting, workflow field coverage, and license/evidence policy.

### Wave W4: P2 professional terminal workflow topic pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-pro-terminal-workflow-topic-validation-2026-07-08.md`

Findings:

- Upgraded `pro-terminal-usage` to `0.2.4`.
- Added per-event `workflow_topics`, `primary_workflow_topic`, and
  `workflow_topic_terms`.
- Added workflow topic coverage to `manifest.workflow_surface_summary` and
  `investor_wiki_evidence.v1.json`, including topic counts, primary topic
  counts, terminal/topic counts, activity/topic counts, and missing expected
  workflow topics.
- Covered macro policy, market strategy, industry themes, company
  fundamentals, valuation models, credit/fixed income, factor/quant,
  portfolio monitoring, data export, and HK/US market workflow themes.
- Kept the license-safe boundary unchanged: topic classification uses the
  user's authorized workflow metadata and capped previews, not vendor database
  mirroring or licensed content redistribution.
- Fixture validation covers Bloomberg credit/search/download/template/factor
  workflows, Choice/Wind workbook watchlist and macro export workflows, iFinD
  watchlist ZIP provenance, unsafe ZIP member skipping, evidence summary
  routing, and all expected workflow topics.

### Wave W5: P2 professional terminal workflow-boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-pro-terminal-workflow-boundary-validation-2026-07-08.md`

Findings:

- Upgraded `pro-terminal-usage` to `0.2.5`.
- Added `manifest.workflow_boundary_proof` as the single FinClaw gate for
  authorized input presence, Wind/Choice/iFinD/Bloomberg coverage, activity
  coverage, workflow-field coverage, workflow-topic coverage, workflow surfaces,
  source audit counts, license-safe boundaries, and Investor Wiki flow.
- Added the same workflow-boundary proof to
  `investor_wiki_evidence.v1.json.coverage_summary` so SoulMirror/FinClaw can
  inspect the proof without opening the raw manifest.
- Kept the collector scoped to user personal workflow metadata. False claims
  remain explicit: no complete terminal history, no real licensed-account
  validation, no vendor database mirror, no licensed content body mirror, no
  public market data mirror, no credentials, no license keys, no order mutation,
  and no direct Wiki write.
- Package `SUMMARY.md` now surfaces the workflow-boundary proof level and
  license mirror state.
- Fixture validation covers medium partial, strong partial, and missing-input
  proof levels.

### Wave X: P2 social activity coverage pass 1

Status: `completed-baseline`

Validation record:

- `docs/validations/investor-p2-social-activity-coverage-validation-2026-07-08.md`

Findings:

- Upgraded `social-activity` to `0.2.1`.
- Added authorized ZIP package import for JSON/JSONL/NDJSON, CSV/TSV,
  XLSX/XLSM, HTML, Markdown, and TXT activity members.
- Added `manifest.platform_coverage` for Weibo, Bilibili, and Xiaohongshu.
- Added `manifest.action_coverage` for follow, like, favorite, watch, comment,
  and share actions.
- Added `manifest.weak_signal_field_coverage` for creator IDs/URLs, item IDs,
  tags, topics, symbols, watch progress, engagement counts, comment previews,
  and content previews.
- Added `manifest.weak_evidence_policy` so downstream FinClaw components can
  machine-read that social evidence is weak, requires corroboration, and cannot
  become a standalone investment conclusion.
- Clarified `social-investment-influence` lens registration to exclude
  standalone investment conclusions.
- Fixture validation covers Weibo JSON, Bilibili CSV, Xiaohongshu HTML,
  Xiaohongshu nested JSON, Bilibili/Weibo XLSX, Weibo ZIP, credential filtering,
  all expected platforms/actions/weak fields, weak-evidence policy, and ZIP path
  traversal skipping.

### Wave X2: P2 social activity audit and weak-evidence pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-social-activity-audit-validation-2026-07-08.md`

Findings:

- Added ZIP `source_archive` and `archive_member` provenance to raw refs.
- Added per-event `content_length` while keeping content/comment previews
  capped.
- Added `manifest.influence_surface_summary` for creator, creator ID/URL,
  content URL/domain, item ID, tags, topics, symbols, engagement counts,
  comment/content preview, and source section availability.
- Added `manifest.source_audit` for source refs, archive member events, archive
  count, and section/sheet provenance.
- Added `manifest.content_policy` to keep collection preview-only and prevent
  platform-wide scraping or full creator-profile scraping.
- Strengthened `manifest.weak_evidence_policy` with generic-collector and real
  validation flags.
- Hardened ZIP import against POSIX traversal and Windows drive/traversal
  members.

### Wave X3: P2 social activity source audit hardening

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-social-activity-source-audit-validation-2026-07-08.md`

Findings:

- Upgraded `social-activity` to `0.2.3`.
- Added `collect_from_inputs_with_audit` while preserving the existing
  `collect_from_inputs` compatibility wrapper.
- Added `manifest.source_audit` fields for requested inputs, missing inputs,
  supported extensions, extension coverage, skipped file counts, skipped file
  reasons, parsed/emitted counts, path-level parse results, and limit
  truncation.
- Added ZIP member audit for member counts, emitted member events, skipped ZIP
  member counts, skipped ZIP member reasons, and unsafe path refusal.
- Updated the CLI so package manifests receive the collection audit instead of
  inferring sources only from emitted events.
- Fixture validation covers Weibo JSON, Bilibili CSV, Xiaohongshu HTML,
  Xiaohongshu nested JSON, Bilibili/Weibo XLSX, Weibo ZIP, unsupported input
  files, unsafe ZIP members, missing input gap audit, credential filtering, ZIP
  limit accounting, weak-evidence policy, and preview-only content policy.

### Wave X4: P2 social activity topic and lens-surface pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-social-activity-topic-surface-validation-2026-07-08.md`

Findings:

- Upgraded `social-activity` to `0.2.4` and
  `investor-source-collectors` to `0.1.9`.
- Added per-event `social_topics`, `primary_social_topic`, and
  `social_topic_terms` for macro, strategy, industry, fundamental,
  fund/wealth, trading review, risk control, portfolio watch, creator
  education, and HK/US weak influence themes.
- Added social-topic coverage to `manifest.influence_surface_summary`,
  including topic counts, primary topic counts, platform/topic counts,
  action/topic counts, and missing expected social topics.
- Added `social_influence_surface_summary` to the `social-investment-influence`
  lens evidence so FinClaw can see platform, action, creator, engagement, and
  weak social-topic coverage after investment filtering.
- Kept the weak-evidence boundary explicit: social traces require
  corroboration and cannot become standalone investment conclusions.
- Fixture validation covers investment-topic classification, entertainment
  false-positive guard, all expected social topics in package fixtures, lens
  surface summaries, source audit, ZIP provenance, unsafe ZIP member skipping,
  and preview-only content policy.

### Wave X5: P2 social activity and influence boundary proof pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p2-social-activity-boundary-proof-validation-2026-07-08.md`

Findings:

- Upgraded `social-activity` to `0.2.5` and `investor-source-collectors` to
  `0.1.16`.
- Added `manifest.social_activity_boundary_proof` as the generic social gate
  for authorized input presence, Weibo/Bilibili/Xiaohongshu platform coverage,
  action coverage, weak-signal field coverage, social-topic coverage, influence
  surfaces, source audit counts, content-preview policy, required lens flow, and
  explicit no-investment-conclusion claims.
- Added `manifest.social_influence_boundary_proof` to the
  `social-investment-influence` lens so FinClaw can see platform/action/topic/
  creator coverage, preview-only content surfaces, weak evidence strength,
  corroboration requirements, and false claims.
- Added evidence `coverage_summary.source_boundary_proof_summary` so
  SoulMirror can inspect the social influence boundary from
  `investor_wiki_evidence.v1.json` without opening the raw manifest.
- Kept both layers weak-evidence-only: no standalone investment conclusion, no
  complete social activity history, no platform-wide scrape, no full creator
  profile scrape, no full content mirror, no private platform credentials, and
  no direct Wiki write.
- Fixture validation covers medium partial, strong partial, and missing-input
  social activity proof levels plus social influence lens proof and evidence
  proof summaries.

### Wave Y: Investor Wiki evidence contract pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-wiki-evidence-contract-validation-2026-07-08.md`

Findings:

- Added `collectorx.investor_wiki` as the shared FinClaw/SoulMirror evidence
  contract helper for `external.investor / 7 dimensions / 20 subdimensions`.
- Added `tools/validate_investor_wiki_evidence.py` and
  `tools/test_investor_wiki_contract.py`, and wired the contract test plus
  first-loop evidence validation into `tools/validate_project.py`.
- Connected canonical dimension coverage to evidence packages emitted by
  `eastmoney-portfolio`, `xueqiu-investor-activity`, `china-wealth-assets`,
  `hk-us-brokerage`, `pro-terminal-usage`, and `financial-news-usage`.
- Preserved conservative evidence semantics: strong trade/asset facts can
  support portfolio/execution/risk/decision-log dimensions, while Snowball,
  terminal, and finance-news usage remain attention/workflow/information-source
  evidence.
- Fixture validation now asserts concrete Wiki subdimension support for
  Snowball industry-circle, China wealth portfolio preference, HK/US brokerage
  execution discipline, professional-terminal analysis ability, finance-news
  information source, and EastMoney 7/20 coverage.
- This wave improves Wiki consumability and FinClaw gating; it does not claim
  new real-account validation.

### Wave Z: Watchlist Investor Wiki evidence pass

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-watchlist-evidence-contract-validation-2026-07-08.md`

Findings:

- Added `investor_wiki_evidence.v1.json` package output to
  `xueqiu-watchlist` and `ths-watchlist`.
- Both collectors now reuse the shared `collectorx.investor_wiki` contract and
  emit canonical 7-dimension/20-subdimension coverage.
- Watchlist evidence supports market-view, value-preference, industry-circle,
  information-learning-style, style-profile, and information-source
  subdimensions with conservative weak/medium support levels.
- The evidence policy remains explicit: self-selected watchlists are attention
  universe signals, not broker-confirmed holdings, trades, orders, cashflows, or
  complete portfolio facts.
- Fixture validation covers standard package output, evidence package
  generation, contract dimensions, non-strong-trade policy, source audit, ZIP
  provenance for Xueqiu, and gap behavior.

### Wave AA: FinClaw package ingestion gate

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/finclaw-package-ingestion-gate-validation-2026-07-08.md`

Findings:

- Added `tools/validate_collector_package.py` so FinClaw can validate any
  collector output directory before durable Lake ingestion or investor Wiki
  distillation.
- The validator checks `manifest.json`, `lake/<collector-id>/events.jsonl`,
  event JSONL readability, `collectorx.event.v1` required fields, privacy
  booleans, `raw_ref`, `data`, collector-id consistency, and optional
  `investor_wiki_evidence.v1.json` contract validity.
- Added a machine-readable `--json` mode for product/job-runner integration and
  a `--require-evidence` mode for vertical collectors or lenses that must
  produce Wiki evidence.
- Updated `tools/run_first_investor_loop.py` to write `manifest.json`; the
  project smoke test now validates that first-loop package with
  `--require-evidence`.
- Updated the integration guide and productization control board so package
  validation is an explicit FinClaw gate before Wiki distillation.
- This wave improves production gating across P0/P1/P2, but does not claim new
  real-account or real-device validation for individual collectors.

### Wave AB: P1 TickTick SoulMirror live collector alignment

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/investor-p1-ticktick-soulmirror-validation-2026-07-08.md`

Findings:

- Aligned `collectors/generic/ticktick.yaml` to the SoulMirror
  YAML + AgentRunner + skill contract.
- Added `collect_for_soulmirror.py` as the live collector entrypoint. It
  returns a dependency-light JSON array snapshot and leaves durable Lake writes,
  diffing, and snapshot state to the SoulMirror daemon.
- Missing authorization now fails with `ticktick_auth_required` instead of
  returning `[]`, so FinClaw does not mistake "not connected" for "no tasks".
- Hardened the AgentRunner prompt and skill instructions so scheduled/immediate
  collection never starts OAuth and never writes a structured auth error into
  the snapshot/result file.
- Added `auth.py connect` support for a FinClaw-managed OAuth Broker through
  `TICKTICK_OAUTH_BROKER_URL`; the OAuth client secret stays server-side.
- Added `task collect-all` to the management CLI for stable snapshot export.
- Kept `ticktick_events.py` as an offline authorized JSON/ZIP conversion helper,
  writing `exports/ticktick/events.jsonl` instead of daemon-owned
  `lake/ticktick/events.jsonl`.
- Fixture validation covers missing auth, a fake authorized OpenAPI server,
  active/completed tasks, project-name mapping, inbox fallback, dedupe, token
  non-leakage, the offline export helper, and the YAML/SKILL prompt contract
  that keeps authorization out of the collection path.
- This improves the P1 task-planning source, but does not claim real TickTick
  account validation until the managed OAuth Broker is deployed and a real
  recurring-task/timezone backtest is run.

### Wave AC: FinClaw catalog invocation contract gate

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/finclaw-catalog-invocation-gate-validation-2026-07-08.md`

Findings:

- Strengthened `tools/validate_project.py` catalog validation so product entries
  cannot point to missing collector YAML, missing skills, or missing Python
  scripts.
- Catalog category must match the collector YAML folder.
- Catalog readiness must be declared in `readiness_levels`.
- Lens entries must include `--source <collector-id>`.
- Non-SoulMirror catalog entries must declare a concrete `<out-dir>` target.
- SoulMirror catalog entries must use `apiVersion: soulmirror/v1`.
- The gate caught and fixed the `qq` catalog command: `--db-dir` is a top-level
  `qq_query.py` option, and the catalog now writes compact collect JSON plus
  `lake/qq/events.jsonl` under `<out-dir>`.
- This improves FinClaw product-call safety, but does not claim QQ standard
  package readiness yet.

### Wave AD: Supporting QQ standard package pass

Status: `completed-deep-beta`

Validation record:

- `docs/validations/qq-standard-package-validation-2026-07-08.md`

Findings:

- Added `collect --out-dir <out-dir>` to `qq_query.py` so FinClaw can call QQ
  as a standard CollectorX package collector.
- The package now writes `lake/qq/events.jsonl`, `manifest.json`,
  `qq.collect.json`, and `SUMMARY.md`.
- The manifest records source audit, filter policy, field coverage,
  communication-surface counts, owner-UIN presence without leaking the UIN, and
  generic communication evidence policy.
- Missing or unreadable QQ databases now produce an explicit gap package with
  `collection_readiness.status=needs_readable_qq_db`, so FinClaw can show the
  user the correct next action.
- Fixture validation covers normal package output, package validator
  compatibility, and missing-database gap output.
- This improves QQ as a supporting communication channel for the investor
  avatar, but it still requires real authorized/decrypted QQ NT message
  validation and investor communication lens backtesting before production
  exposure.

### Wave AE: FinClaw skill metadata consistency gate

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/finclaw-skill-metadata-gate-validation-2026-07-08.md`

Findings:

- Added `validate_skill_metadata()` to `tools/validate_project.py`.
- Every skill referenced by `collectors/finclaw-investor-catalog.json` must now
  have a `.collectorx.json` metadata file and a `VERSION` file.
- Metadata version must exactly match the skill `VERSION`, and metadata must
  declare a stable `slug` or `collector` plus a non-empty description.
- Added missing metadata for `wechat-export` and `ticktick-cli`.
- Corrected drifted metadata versions/descriptions for `calendar-collector`,
  `china-wealth-assets`, `email-collector`, `notes-collector`,
  `xueqiu-watchlist`, and `xueqiu-investor-activity`.
- This improves GitHub/FinClaw discovery safety and prevents product catalog
  calls from pointing at stale skill metadata. It does not claim new
  real-account validation for any individual collector.

### Wave AF: FinClaw catalog coverage and invocation precondition gate

Status: `completed-baseline+audit`

Validation record:

- `docs/validations/finclaw-invocation-contract-coverage-validation-2026-07-08.md`

Findings:

- Added `collectors/finclaw-invocation-contracts.json` as the machine-readable
  authorization and product-surface contract for FinClaw product calls.
- Every catalog entry now has authorization mode, product surface, evidence
  role, user action, preflight, failure state, and lens upstream requirements
  when applicable.
- Added `ths-watchlist` to `collectors/finclaw-investor-catalog.json`, closing
  the gap where the Tonghuashun watchlist collector existed but was not
  discoverable through the FinClaw investor catalog.
- Added explicit `catalog_exclusions` for `doubao`, which has a generic
  CollectorX YAML but is not currently part of the investor-avatar catalog.
- Strengthened `tools/validate_project.py` so collector YAML files must be
  cataloged or explicitly excluded, invocation contracts must exactly cover
  catalog entries, lens contracts must use `lake-lens`, and production/
  supporting surfaces must match readiness intent.
- This improves FinClaw user-precondition handling and catalog completeness. It
  does not claim new real-account validation for any individual collector.

## P0 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `wechat` + `wechat-investment-dialogue` | `wechat` G1/G2 standard package path is implemented with event JSONL, manifest field/filter/source audit, and generic-to-lens evidence policy; `wechat-investment-dialogue` now supports chat/sender allow/deny policy, source-policy audit, explicit filtered-all gap status, WeChat dialogue boundary proof, and dialogue surface summary; real-source precondition blocked on current Mac | G2/G3: prepare WeChat 4.x keys, run on real `wechat` lake, tune contact/group/sender allowlists, backtest around actual trades |
| 2 | `research-documents` | G2/G3 partial on macOS metadata/content extraction; filesystem default-root code paths fixture-tested for macOS/Windows/Linux; extraction policy, per-input audit, skipped reasons, screenshot default metadata-only boundary, explicit `--include-image-ocr` tesseract adapter, research document surface summary, research corpus boundary proof, and collection audit are fixture-tested | Real Windows/Linux device validation, more real XLSX/DOCX/PDF/image samples, Chinese OCR quality review, Wiki backtest against real trades/reviews |
| 3 | `email` + `email-research` | G1/G2 local email export import baseline plus Apple Mail EMLX, Maildir, ZIP package, sanitized attachment refs, IMAP attachment refs, per-input import audit, skipped file/ZIP-member reasons, path-level parse results, mailbox boundary proof, and research-attachment filename matching; mailbox registration still missing | G2/G3: register mailbox, run on real mailbox events and real local exports, broker/IR sender backtest, no-full-body Wiki leakage review |
| 4 | `ths-watchlist` | G1/G2 authorized Tonghuashun watchlist import path with standard Lake output, manifest, source audit, field coverage, 7/20 Investor Wiki evidence, and explicit attention-universe boundary; now discoverable through the FinClaw investor catalog and invocation contract | G2/G3: real Tonghuashun watchlist export/local-store validation, Windows/macOS/Linux path validation, trade/research corroboration backtest |
| 5 | `xueqiu-watchlist` + `xueqiu-investor-activity` | G1/G2 strengthened local export/package paths with ZIP provenance, activity XLSX/XLSM/HAR support, activity-boundary proof, pagination completeness summary, credential/query stripping audit, sanitization, SoulMirror sync, standard 7/20 evidence packages, and explicit non-broker-trade evidence policy; no one-click real account adapter | G2/G3: real Snowball account/HAR samples, pagination, watchlist/favorites/posts/comments/follows/portfolio validation |
| 6 | `china-wealth-assets` | G1/G2 strengthened local export/package path with platform coverage, field coverage, account boundary summary, partial asset-boundary proof strength, asset surface summary, currency summary, transaction-side summary, asset value summary, HAR/ZIP provenance, credential/query stripping audit, raw sanitization, and SoulMirror sync; no one-click real account adapter | G2/G3: real Alipay/Tiantian/Danjuan/Qieman/bank wealth HAR/export samples, per-platform adapters, complete account-boundary proof |

## P1 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `investment-notes` | G2/G3 partial on macOS Obsidian-style notes; G1/G2 import path for Youdao/Evernote/Markdown/HTML/JSON/CSV/TSV/ENEX/ZIP; generic notes manifest reports platform coverage, field coverage, table import audit, source audit, content policy, ZIP provenance, and generic-collector evidence policy; lens manifest/evidence reports review/rules/checklist/valuation/research note-type surface, source-app surface, preview/full-content surface, and investment note boundary proof | Validate real Notion/Youdao/Evernote exports/APIs, user allowlists, false-positive review, Windows/Linux vault path validation |
| 2 | `task-calendar-investor` | G1/G2 baseline for authorized TickTick/Dida JSON/ZIP and generic calendar ICS/JSON/CSV/TSV/ZIP exports; TickTick live path now follows SoulMirror YAML + AgentRunner + skill, returns a stable task snapshot through `collect_for_soulmirror.py`, fails with `ticktick_auth_required` when disconnected, and keeps daemon-owned `lake/ticktick/events.jsonl` separate from offline `exports/ticktick/events.jsonl`; calendar reports duration/multi-day/invalid-time/conflict quality; lens manifest/evidence reports research-task/trade-plan/review/earnings/research-meeting/risk-check surface, upstream source surface, reminder/time coverage, calendar time-quality surface, and task/calendar boundary proof | Deploy managed TickTick OAuth Broker, run real TickTick account validation, validate real calendar exports/accounts, recurring tasks/timezones, false-positive review |
| 3 | `meeting-minutes` | G1/G2 strengthened for local/platform/ZIP meeting artifacts plus Feishu/DingTalk/WeCom collaboration exports; manifests report platform coverage, field coverage, meeting/collaboration source summaries, source audit, ZIP provenance, generic-collector evidence policy, and lens-level roadshow/research/IC/expert/earnings/decision/risk/follow-up surface summaries plus meeting-minutes boundary proof; real account APIs pending | Real Feishu/DingTalk/WeCom/Tencent Meeting artifacts, participant normalization, attachments/recording refs, false-positive review |
| 4 | `wechat-article-favorites` | G2/G3 partial for local authorized saved-article files; G1/G2 file/folder/ZIP import with favorite/read/share/saved-file action coverage, field coverage, article source summary, source audit, ZIP provenance, content policy, generic-collector evidence policy, and lens-level broker/fundamental/strategy/industry/valuation/portfolio/risk/macro article surface summaries plus WeChat article boundary proof | Real WeChat favorites/public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation, false-positive review |
| 5 | `financial-news-usage` | G1/G2 strengthened for authorized usage/saved pages, ZIP packages, Chromium/Safari browser-history copies, and platform/action/topic coverage; manifests now include field coverage, usage topic summary, usage surface summary, per-input source audit, skipped file/ZIP-member reasons, path-level parse results, browser-history source apps, ZIP provenance, usage boundary proof, content policy, and vertical evidence policy | Real CLS/WallstreetCN/Gelonghui app/account adapters, real subscription/alert stores, Safari/Windows/Linux path validation, platform inference on noisy exports, topic false-positive review |

## P2 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `hk-us-brokerage` | G1/G2 strengthened for authorized CSV/JSON/Excel/ZIP export packages with broker, trade-surface, strong-field coverage, strong-trade surface summary, account-boundary summary, currency/market summary, fee/tax/margin summary, asset value summary, unified brokerage-boundary proof, per-input source audit, skipped file/ZIP-member reasons, path-level parse results, ZIP provenance, and read-only evidence policy; real local broker export missing | G2/G3: real Futu/Tiger/IBKR exports or read-only screens, broker-specific column maps, complete account-boundary proof, multi-currency assets, margin, tax, dividends, FX, and Windows/macOS/Linux path validation |
| 2 | `pro-terminal-usage` | G1/G2 strengthened for authorized CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow packages with terminal, activity, workflow-field coverage, workflow-topic coverage, workflow surface summary, unified workflow-boundary proof, per-input source audit, skipped file/ZIP-member reasons, path-level parse results, ZIP provenance, license policy, and evidence policy; real native terminal export not validated | G2/G3: real Wind/Choice/iFinD/Bloomberg workflow exports, watchlists, searches, downloads, templates, datasets, fields, function codes, workflow-topic false-positive review, license-safe validation |
| 3 | `social-investment-influence` | G1/G2 strengthened for authorized JSON/CSV/Excel/HTML/TXT/ZIP social activity packages with weak-evidence policy, platform coverage, action coverage, weak-field coverage, social-topic coverage, influence surface summary, social activity boundary proof, lens social-surface summary, social influence boundary proof, per-input source audit, skipped file/ZIP-member reasons, path-level parse results, ZIP provenance, limit truncation audit, and preview-only content policy; strict local saved-record validation remains partial | Real Weibo/Bilibili/Xiaohongshu exports, platform/domain allowlists, creator allowlists, engagement fields, social-topic false-positive review, weak-evidence backtest |

## Git Practice

- Keep each wave small enough to review.
- Run `bash test_collectors.sh` before commit.
- Commit with a message that names the collector wave.
- Push `main` after a green validation run.
- If a collector remains baseline or placeholder, say so in
  `docs/production-readiness.md` instead of implying production readiness.
