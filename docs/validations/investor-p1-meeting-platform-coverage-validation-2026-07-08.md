# P1 Meeting Platform Coverage Validation - 2026-07-08

This validation records the third productization pass for `meeting-artifacts`.

## Scope

Collector path:

- Generic source: `meeting-artifacts`
- Skill: `skills/meeting-artifacts`
- Lens target: `meeting-minutes`

This pass improves the upstream generic meeting package. It does not promote
all meeting content into the investor Wiki.

## Product Changes

- Added authorized ZIP import for meeting artifact packages.
- ZIP import supports Markdown, TXT, HTML, JSON/JSONL/NDJSON, CSV/TSV, VTT,
  and SRT members.
- ZIP import skips absolute paths and `..` path traversal members.
- ZIP member provenance is preserved in `raw_ref.path` as
  `archive.zip::member`.
- Added `manifest.platform_coverage`:
  - expected P1 platforms: `feishu`, `dingtalk`, `wecom`, `tencent-meeting`
  - observed platforms
  - observed expected platforms
  - missing expected platforms
  - platform event counts
  - unknown event count
  - `real_account_validation=false`
- Package summary now includes observed and missing meeting platforms.

## Fixture Validation

Validated scenarios:

- Local Markdown minutes and VTT transcript produce generic
  `collectorx.event.v1` note events and partial platform coverage.
- DingTalk-style JSON export, WeCom-style CSV export, Tencent Meeting HTML
  export, and Feishu ZIP Markdown export produce normalized platform values.
- Fake credential field `token` is removed from emitted events.
- ZIP member `../unsafe.md` is skipped.
- All expected P1 meeting platforms report
  `all_expected_platforms_observed`.

Command:

```bash
.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
```

Result:

- Passed.

## Current Gate

- Authorized local/platform/ZIP export import: G1/G2 baseline.
- Prior macOS local-file candidate validation: G2/G3 partial.
- Real Feishu/DingTalk/WeCom/Tencent Meeting account/API validation: not done
  in this pass.
- Investment lens false-positive backtest: still needed before production.

## Remaining Before Production Candidate

- Validate real authorized exports from Feishu, DingTalk, WeCom, and Tencent
  Meeting.
- Build or port account adapters where user-authorized APIs are available.
- Normalize participant identities across email, phone, open user IDs, and
  local display names without storing credentials.
- Validate attachment/recording raw refs on real exports.
- Backtest `meeting-minutes` so non-investment company meetings do not enter
  investor Wiki conclusions.
