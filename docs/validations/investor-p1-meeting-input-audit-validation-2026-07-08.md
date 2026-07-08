# P1 Meeting Input Audit Validation - 2026-07-08

This validation records the `meeting-artifacts` input-audit hardening pass.

No platform account token, cookie, meeting password, recording body, or private
meeting payload is committed.

## Scope

- Collector: `meeting-artifacts` `0.3.1`
- FinClaw target: generic meeting/transcript/subtitle Lake input for the
  downstream `meeting-minutes` investor lens.
- Non-goal: real Feishu/DingTalk/WeCom/Tencent Meeting account adapters or
  direct investment-meeting classification.

## Added Audit Fields

`manifest.source_audit` now includes:

- `requested_inputs`
- `input_missing_count`
- `skipped_file_count`
- `skipped_reason_counts`
- `skipped_extension_counts`
- `input_results`
- `skipped_file_samples`

The existing ZIP provenance and skipped-member audit remain unchanged.

## Fixture Coverage

The fixture validates a mixed input set:

- A valid folder containing `.md` minutes and `.vtt` transcript files.
- One unsupported `.mp4` file in the folder.
- One missing `.srt` path passed as an explicit input.

The collector still emits the two valid meeting events while reporting the
missing path and unsupported extension in `source_audit`.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/meeting-artifacts/scripts/meeting_artifacts/parser.py \
  skills/meeting-artifacts/scripts/meeting_artifacts.py \
  skills/meeting-artifacts/scripts/meeting_artifacts/events.py \
  skills/meeting-artifacts/tests/test_meeting_artifacts.py

.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
```

## Result

The meeting artifact collector can now explain why user-provided files were not
collected, which is required for a production FinClaw collector UX. The generic
collector still does not write investor Wiki evidence directly; the
`meeting-minutes` lens remains responsible for investment filtering.
