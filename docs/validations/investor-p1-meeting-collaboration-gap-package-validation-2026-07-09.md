# P1 Meeting/Collaboration Gap Package Validation - 2026-07-09

This validation records the gap-package hardening pass for P1 meeting and
collaboration collectors.

## Scope

- Meeting collector: `meeting-artifacts` `0.3.4`
- Collaboration collector: `collaboration-exports` `0.2.2`
- Downstream lens: `meeting-minutes`
- Platforms covered by this pass:
  - generic meeting artifacts
  - DingTalk collaboration exports
  - WeCom collaboration exports

## What Changed

- `meeting-artifacts` now emits profile gap events for:
  - missing authorized meeting input;
  - authorized input with no readable records;
  - source-platform/participant/keyword scope-policy filtered-all runs.
- `collaboration-exports` now emits profile gap events for:
  - missing authorized DingTalk/WeCom input;
  - authorized input with no readable records;
  - source-platform/record-kind/chat/sender/participant/keyword scope-policy
    filtered-all runs.
- Meeting manifests now separate:
  - `event_count`
  - `meeting_artifact_event_count`
  - `gap_event_count`
- Collaboration manifests now separate:
  - `event_count`
  - `collaboration_event_count`
  - `gap_event_count`
- Normal meeting/collaboration events now have a non-empty `time` fallback when
  exported artifacts do not provide an event time.

## Boundary

Gap events route to `collectorx.data_quality.collection_gaps`. They explicitly
do not claim meeting facts, collaboration facts, investment meeting facts,
investment conclusions, complete meeting/workspace history, service-token
collection, recording-body collection, or direct investor Wiki writes.

Only retained non-gap meeting/collaboration events should feed the
`meeting-minutes` lens.

## Verification

```bash
.venv/bin/python -m py_compile \
  skills/meeting-artifacts/scripts/meeting_artifacts.py \
  skills/meeting-artifacts/scripts/meeting_artifacts/events.py \
  skills/meeting-artifacts/tests/test_meeting_artifacts.py \
  skills/collaboration-exports/scripts/collaboration_exports.py \
  skills/collaboration-exports/scripts/collaboration_exports/parser.py \
  skills/collaboration-exports/tests/test_collaboration_exports.py

.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
.venv/bin/python skills/collaboration-exports/tests/test_collaboration_exports.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Results:

```text
meeting-artifacts tests passed.
collaboration-exports tests passed.
finclaw catalog tests passed.
finclaw batch runner tests passed.
CollectorX validation passed.
```

The targeted tests validate normal, missing-input, and filtered-all packages
through `tools/validate_collector_package.py` for `meeting-artifacts`,
`dingtalk`, and `wecom`. The full project validation and collector smoke suite
also passed after the documentation/catalog updates.

## Remaining Work

- Real Feishu/DingTalk/WeCom/Tencent Meeting account/export validation.
- Participant and speaker identity normalization against real samples.
- Attachment and recording reference validation without collecting recording
  bodies by default.
- False-positive review in `meeting-minutes` against real non-investment
  workplace meetings.
