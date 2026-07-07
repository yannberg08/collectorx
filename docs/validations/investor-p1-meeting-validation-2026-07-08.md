# P1 Meeting Artifacts Validation - 2026-07-08

This validation records the first productization pass for meeting/minutes
evidence without committing private meeting content.

## Generic Meeting Artifacts Collector

Collector path:

- Generic source: `meeting-artifacts`
- Skill: `skills/meeting-artifacts`

Result:

- Added a runnable generic collector for user-authorized local meeting artifact
  files.
- Supported inputs: Markdown, TXT, JSON, JSONL/NDJSON, VTT, SRT.
- Output package:
  - `lake/meeting-artifacts/events.jsonl`
  - `manifest.json`
  - `SUMMARY.md`
- Generic meeting events route to `internal.collaboration.meetings`.
- Manifest sets `can_claim_investment_meeting_minutes: false`.

Fixture validation:

- Markdown minutes and VTT transcript are converted to `collectorx.event.v1`
  note events.
- Events do not directly route to investor Wiki.

## Meeting Minutes Lens

Lens path:

- `meeting-minutes` via `skills/investor-source-collectors`

Fixture validation:

- Keeps a roadshow/research minutes event.
- Filters an unrelated team logistics meeting.

Real local candidate validation:

- Candidate files found: 10.
- `meeting-artifacts` emitted 10 generic meeting events.
- `meeting-minutes` emitted 10 investor-meeting candidate events.
- Lens average confidence: `0.813`.
- Wiki coverage: 8 usable investor subdimensions.

Current gate:

- Local authorized meeting files: G2/G3 partial on macOS.
- Lens filter: G2 baseline.
- Platform API validation: not done.

Remaining before production:

- Real Feishu minutes/recording artifact validation.
- DingTalk, WeCom, and Tencent Meeting artifact adapters.
- Participant identity normalization.
- Attachment and recording raw-ref normalization.
- False-positive review on non-investment company meetings.
- Windows/Linux path validation for local meeting exports.
