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

## Current Wave

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

## P0 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `wechat-investment-dialogue` | G1; real-source precondition blocked | G2/G3: prepare WeChat 4.x keys, run on real `wechat` lake, add contact/group allowlists, backtest around actual trades |
| 2 | `research-documents` | G2/G3 partial on macOS metadata and explicit content extraction | Windows/Linux path validation, more real XLSX/DOCX/PDF samples, false-positive review, extraction-scope UX |
| 3 | `email-research` | G1; mailbox registration missing | G2/G3: register mailbox, run on real mailbox events, broker/IR sender classifier, attachment raw refs |
| 4 | `xueqiu-investor-activity` | G1/G2 strengthened local export/package path; prior local candidate parsing; no real account adapter | G2/G3: real Snowball account adapter or authorized export workflow, pagination, favorites/posts/comments/follows/portfolio validation |
| 5 | `china-wealth-assets` | G1/G2 strengthened local export/package path; no real account export found in latest pass | G2/G3: per-platform adapters for Alipay/Tiantian/Danjuan/Qieman/bank wealth exports or read-only screens |

## P1 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `investment-notes` | G2/G3 partial on macOS Obsidian-style notes | Strengthen Notion/Youdao/Evernote adapters, user allowlists, false-positive review, Windows/Linux vault path validation |
| 2 | `task-calendar-investor` | G1/G2 baseline for authorized TickTick JSON; real API token missing | Complete TickTick OAuth validation, implement generic calendar collector, validate recurring tasks/timezones |
| 3 | `meeting-minutes` | G2/G3 partial for local authorized meeting files | Real Feishu/DingTalk/WeCom/Tencent Meeting artifacts, participant normalization, attachments/recording refs, false-positive review |
| 4 | `wechat-article-favorites` | G2/G3 partial for local authorized saved-article files | Real WeChat favorites/public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation |
| 5 | `financial-news-usage` | G2/G3 partial for local authorized usage/saved pages | Real CLS/WallstreetCN/Gelonghui app/account adapters, browser-history import, subscription/alert normalization, platform inference |

## P2 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `hk-us-brokerage` | G1 baseline for authorized local read-only exports; real local export missing | G2/G3: real Futu/Tiger/IBKR exports or read-only screens, per-broker column maps, multi-currency validation |
| 2 | `pro-terminal-usage` | G1 baseline for authorized local workflow exports; real native terminal export not validated | G2/G3: real Wind/Choice/iFinD/Bloomberg workflow exports, watchlists, searches, downloads, templates, license-safe validation |
| 3 | `social-investment-influence` | G2/G3 partial for strict local saved social records | Real Weibo/Bilibili/Xiaohongshu exports, platform/domain allowlists, creator allowlists, weak-evidence backtest |

## Git Practice

- Keep each wave small enough to review.
- Run `bash test_collectors.sh` before commit.
- Commit with a message that names the collector wave.
- Push `main` after a green validation run.
- If a collector remains baseline or placeholder, say so in
  `docs/production-readiness.md` instead of implying production readiness.
