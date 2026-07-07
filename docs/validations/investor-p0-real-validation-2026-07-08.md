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
