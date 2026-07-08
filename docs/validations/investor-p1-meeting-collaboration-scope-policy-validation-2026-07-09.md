# P1 Meeting/Collaboration Scope Policy Validation - 2026-07-09

## Scope

This validation covers the P1 meeting and collaboration generic collectors:

- `meeting-artifacts` `0.3.3`
- `collaboration-exports` `0.2.1`

The goal is to ensure authorized workplace artifacts can be narrowed before
generic Lake output, while investment relevance remains a downstream lens
decision.

## What Changed

- `meeting_artifacts.py collect` accepts:
  - `--allow-source-platform` / `--deny-source-platform`
  - `--allow-participant` / `--deny-participant`
  - `--allow-keyword` / `--deny-keyword`
- `collaboration_exports.py collect` accepts:
  - `--allow-source-platform` / `--deny-source-platform`
  - `--allow-record-kind` / `--deny-record-kind`
  - `--allow-chat` / `--deny-chat`
  - `--allow-sender` / `--deny-sender`
  - `--allow-participant` / `--deny-participant`
  - `--allow-keyword` / `--deny-keyword`
- Manifest source audit now includes `meeting_scope_policy` or
  `collaboration_scope_policy` with configured filters, candidate record count,
  filtered record count, filter reason counts, and
  `policy_does_not_assert_investment_relevance=true`.
- If all candidate records are excluded by policy, readiness reports
  `scope_policy_filtered_all`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/meeting-artifacts/scripts/meeting_artifacts.py \
  skills/meeting-artifacts/scripts/meeting_artifacts/events.py \
  skills/meeting-artifacts/scripts/meeting_artifacts/parser.py \
  skills/meeting-artifacts/tests/test_meeting_artifacts.py \
  skills/collaboration-exports/scripts/collaboration_exports.py \
  skills/collaboration-exports/scripts/collaboration_exports/parser.py \
  skills/collaboration-exports/tests/test_collaboration_exports.py
```

```bash
.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
```

```bash
.venv/bin/python skills/collaboration-exports/tests/test_collaboration_exports.py
```

## Results

- Syntax validation passed.
- Meeting fixture validation passed.
- Collaboration fixture validation passed.
- Meeting tests cover partial retention, source-platform filtering, participant
  allow filtering, keyword denial, and filtered-all status.
- Collaboration tests cover partial retention, source-platform filtering,
  chat/sender allow filtering, keyword denial, and filtered-all status.

## Product Boundary

- These generic collectors still do not write investor Wiki facts directly.
- Scope policy narrows authorized source records; it does not classify
  investment relevance.
- `meeting-minutes` and later investor lenses remain responsible for deciding
  whether a meeting or collaboration record is useful to the investment avatar.
- This pass does not claim real Feishu, DingTalk, WeCom, or Tencent Meeting
  account API validation.
- This pass does not claim complete workspace history, complete meeting
  history, speaker identity resolution, tenant permission validation, recording
  body collection, or false-positive backtesting.
