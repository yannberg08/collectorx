# P1 Notes Gap Package Validation - 2026-07-09

This validation records the gap-package hardening pass for the generic
`notes` collector.

## Scope

- Skill: `notes-collector` `0.2.7`
- Source: `notes`
- Downstream lens: `investment-notes`
- FinClaw route: generic notes Lake plus data-quality collection gaps.

This pass does not expand the meaning of generic notes. It only makes empty
authorized-note runs observable and validator-safe.

## What Changed

- Missing user-authorized note input now emits one `collectorx.event.v1`
  profile event instead of an empty event file.
- Source-policy filtered-all runs now emit one `collector_gap` profile event
  instead of an empty event file.
- `manifest.json` now separates:
  - `event_count`
  - `note_event_count`
  - `gap_event_count`
- Gap events route to `collectorx.data_quality.collection_gaps`.
- Gap events explicitly state that no note fact, investment-note fact,
  investment conclusion, complete vault coverage, service token, path-traversal
  archive member, or Wiki direct-write claim was made.

## Gap Event Shapes

Missing input:

- `kind=profile`
- `data.profile_type=notes_collection_gap`
- `data.gap=notes_authorized_input_missing`
- `data.status=needs_authorized_notes_input`
- `manifest.collection_readiness.can_enter_finclaw=false`

Filtered-all source policy:

- `kind=profile`
- `data.profile_type=notes_collection_gap`
- `data.gap=notes_source_policy_filtered_all`
- `data.status=source_policy_filtered_all`
- `manifest.note_event_count=0`
- `manifest.gap_event_count=1`

## Verification

```bash
.venv/bin/python -m py_compile \
  skills/notes-collector/scripts/notes_api.py \
  skills/notes-collector/scripts/notes/events.py \
  skills/notes-collector/scripts/notes/parser.py \
  skills/notes-collector/tests/test_notes_collector.py

.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

Result:

```text
notes-collector tests passed.
```

The tests validate normal Obsidian/Notion/Youdao/Evernote/Markdown/Canvas/ZIP
packages, the filtered-all authorization-scope package, and the missing-input
package through `tools/validate_collector_package.py --collector notes`.

## FinClaw Interpretation

FinClaw can ingest the package because `lake/notes/events.jsonl` always
contains at least one valid event. Only retained `kind=note` events may feed the
`investment-notes` lens. `kind=profile` gap events are data-quality facts about
collection state, not investor Wiki facts.

## Remaining Work

- Real Notion/Youdao/Evernote account export/API validation.
- Real-user allowlist tuning across mixed personal and investment notes.
- Windows/Linux vault path validation.
- Broader false-positive backtest in `investment-notes`.
