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

## P0 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `wechat-investment-dialogue` | G1; real-source precondition blocked | G2/G3: prepare WeChat 4.x keys, run on real `wechat` lake, add contact/group allowlists, backtest around actual trades |
| 2 | `research-documents` | G2 partial / G3 partial on macOS metadata | Content extraction under explicit authorization, PDF/Excel/Markdown fixtures, Windows/Linux path validation |
| 3 | `email-research` | G1; mailbox registration missing | G2/G3: register mailbox, run on real mailbox events, broker/IR sender classifier, attachment raw refs |
| 4 | `xueqiu-investor-activity` | G2 partial local candidate parsing | G2/G3: real Snowball account adapter or authorized export workflow, pagination, favorites/posts/comments validation |
| 5 | `china-wealth-assets` | G2 partial local candidate parsing | G2/G3: per-platform adapters for Alipay/Tiantian/Danjuan/Qieman/bank wealth exports or read-only screens |

## P1 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `investment-notes` | G2/G3 partial on macOS Obsidian-style notes | Strengthen Notion/Youdao/Evernote adapters, user allowlists, false-positive review, Windows/Linux vault path validation |
| 2 | `task-calendar-investor` | G1/G2 baseline for authorized TickTick JSON; real API token missing | Complete TickTick OAuth validation, implement generic calendar collector, validate recurring tasks/timezones |
| 3 | `meeting-minutes` | G1 | G2: real Feishu/DingTalk/WeCom/Tencent Meeting artifacts and unified minutes schema |
| 4 | `wechat-article-favorites` | G1 | G2: implement WeChat favorites/public-account article action collector |
| 5 | `financial-news-usage` | G0 | G1/G2: build user activity adapters for CLS/WallstreetCN/Gelonghui |

## P2 Work Queue

| Order | Collector | Current gate | Next gate |
| --- | --- | --- | --- |
| 1 | `hk-us-brokerage` | G0 | G1/G2: Futu/Tiger/IBKR read-only exports for assets, positions, executions, orders, cashflows |
| 2 | `pro-terminal-usage` | G0 | G1/G2: licensed workflow collectors for Wind/Choice/iFinD |
| 3 | `social-investment-influence` | G1 | G2: generic social activity adapters and investment influence classifier validation |

## Git Practice

- Keep each wave small enough to review.
- Run `bash test_collectors.sh` before commit.
- Commit with a message that names the collector wave.
- Push `main` after a green validation run.
- If a collector remains baseline or placeholder, say so in
  `docs/production-readiness.md` instead of implying production readiness.
