# P1 Notes Platform Coverage Validation - 2026-07-08

This validation records the third productization pass for `notes-collector`.

## Scope

Collector path:

- Generic source: `notes`
- Skill: `skills/notes-collector`
- Lens target: `investment-notes`

This pass improves the generic notes lake package. It does not promote generic
notes directly into the investor Wiki.

## Product Changes

- Added authorized ZIP import support for note export packages.
- ZIP import only reads supported note files and skips unsafe members with
  absolute paths or `..` path parts.
- Added Obsidian source inference for authorized local export folders.
- Added `manifest.platform_coverage`:
  - expected P1 platforms: `obsidian`, `notion`, `youdao`, `evernote`
  - observed platforms
  - observed expected platforms
  - missing expected platforms
  - source app event counts
  - unknown event count
  - `real_account_validation=false`
- Added `collection_readiness.platform_coverage_status`.
- Added Notion `--token-env` so API authorization can avoid command-history
  token exposure.

## Fixture Validation

Validated scenarios:

- Obsidian-style vault produces `collectorx.event.v1` and partial platform
  coverage.
- Mixed Youdao JSON, Evernote ENEX, and Markdown exports produce normalized
  note events and source counts.
- ZIP package containing a Notion Markdown export is parsed as `notion`.
- ZIP member `../unsafe.md` is skipped.
- A fixture containing Obsidian, Notion, Youdao, and Evernote records reports
  `all_expected_platforms_observed`.

Command:

```bash
.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

Result:

- Passed.

## Current Gate

- Authorized local export/ZIP import: G1/G2 baseline.
- macOS Obsidian-style local validation: prior G2/G3 partial.
- Real Notion/Youdao/Evernote account/API validation: not done in this pass.
- Windows/Linux vault path validation: not done in this pass.

## Remaining Before Production Candidate

- Validate a real Notion account/API using `--token-env`.
- Validate real Notion ZIP/Markdown exports from a user account.
- Validate real Youdao Cloud Note exports.
- Validate real Evernote/Yinxiang ENEX exports with resources/attachments.
- Add user-selected allowlists for vault folders, notebooks, and tags.
- Backtest `investment-notes` false positives before writing investor Wiki
  conclusions.
