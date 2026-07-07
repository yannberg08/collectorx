# P0 Investor Collector Real Validation - 2026-07-08

This validation records real local runs without committing private source data.

## Environment

- Machine: macOS local development machine
- Date: 2026-07-08
- Repo branch: `main`
- Privacy rule: raw user evidence stayed under `/tmp/collectorx-real-validation`
  and is not committed.

## WeChat Investment Dialogue

Collector path:

- Generic source: `wechat` via `skills/wechat-export`
- Lens: `wechat-investment-dialogue` via `skills/investor-source-collectors`

Result: blocked before source collection.

Observed condition:

- Mac WeChat 4.x key file was not available.
- System Integrity Protection was enabled.
- No reusable `all_keys.json` was found.

Outcome:

- No WeChat messages were read.
- No lens evidence was generated.
- This is an authorization/platform precondition gap, not a lens classifier
  failure.

Required next action:

- User must explicitly prepare Mac WeChat 4.x per-DB keys according to the
  `wechat-export` skill instructions.
- After that, rerun a bounded `wechat --collect` export and feed it into
  `wechat-investment-dialogue`.

Current gate:

- Lens code: G1 runnable baseline.
- Real source validation: blocked before G2/G3 by local authorization
  prerequisite.

## Research Documents

Collector path:

- Generic source: `filesystem` via `skills/filesystem-collector`
- Lens: `research-documents` via `skills/investor-source-collectors`

Run boundary:

- Scanned user-authorized local roots for metadata only.
- Extensions were limited to common document/table/image evidence types.
- File contents were not read.
- Raw paths and file names were not committed.

Result:

- `filesystem` produced 1000 metadata-only events.
- `research-documents` lens produced 454 investment-research candidate events.
- Manifest status: `events_collected`.
- Classification summary: average confidence `0.535`; matched events `454`.
- Wiki evidence coverage: 10 usable investor subdimensions.

Product finding:

- The generic `filesystem` collector was incorrectly suggesting
  `external.investor.research_documents` for every file. This was fixed so the
  generic collector only routes to `internal.knowledge.files`; investment
  routing now belongs to the `research-documents` lens.

Current gate:

- Metadata-only source collection: G2 partial on macOS.
- Lens evidence generation: G3 partial on real local metadata.
- Remaining before production: content extraction under explicit authorization,
  PDF/Excel fixture validation, Windows/Linux path validation, and false-positive
  review against a curated private sample.

## Email Research

Collector path:

- Generic source: `email` via `skills/email-collector`
- Lens: `email-research` via `skills/investor-source-collectors`

Result: blocked before source collection.

Observed condition:

- The local email collector had no registered mailbox accounts.

Outcome:

- No email messages were read.
- No mailbox evidence was generated.

Required next action:

- Register one or more user-authorized mailboxes with app-password or approved
  IMAP authorization.
- Run bounded mailbox collection into `collectorx.event.v1`.
- Feed the event JSONL into `email-research` and validate broker/IR sender
  classification and attachment raw refs.

Current gate:

- Lens code: G1 runnable baseline.
- Real mailbox validation: blocked before G2/G3 by missing mailbox registration.

## Xueqiu Investor Activity

Collector path:

- Vertical source: `xueqiu-investor-activity`

Run boundary:

- Searched local user-authorized directories for candidate Xueqiu-named files.
- Created temporary symlinks under `/tmp/collectorx-real-validation`.
- Raw paths, text previews, and source files were not committed.

Result:

- 22 candidate files were found.
- The baseline parser emitted 100 events.
- Manifest status: `events_collected`.
- Kind counts: 88 note events and 12 message events.
- Activity counts: 88 post-like records and 12 comment-like records.
- Coverage: opinion/review/discussion routes, not broker-confirmed trades.

Current gate:

- Local candidate parsing: G2 partial.
- Remaining before production: real account/export discovery, pagination,
  favorites/follows/watchlists/owner portfolio validation, false-positive
  review, and rate/terms boundary.

## China Wealth Assets

Collector path:

- Vertical source: `china-wealth-assets`

Run boundary:

- Searched local user-authorized directories for candidate fund/wealth files.
- Created temporary symlinks under `/tmp/collectorx-real-validation`.
- Raw paths and source files were not committed.

Result:

- 20 candidate files were found.
- The baseline parser emitted 1 holding event.
- Manifest status: `events_collected`.
- This is only partial authorized input, not a complete asset boundary.

Product finding:

- The manifest previously set `can_claim_complete_asset_boundary` to true when
  any non-gap event existed. This was too strong. It was changed to false by
  default with `asset_boundary_scope: partial_authorized_input`.

Current gate:

- Local candidate parsing: G2 partial.
- Remaining before production: per-platform adapters and real validation for
  Alipay, Tiantian Fund, Danjuan, Qieman, bank wealth products, and cash-like
  assets.
