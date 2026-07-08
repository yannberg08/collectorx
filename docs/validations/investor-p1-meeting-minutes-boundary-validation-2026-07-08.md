# P1 Meeting Minutes Boundary Validation - 2026-07-08

This validation records the boundary-proof pass for the `meeting-minutes` lens.

## Scope

- Skill: `investor-source-collectors` `0.1.14`
- Lens: `meeting-minutes`
- Upstream generic collectors: `meeting-artifacts`, `feishu`, `dingtalk`,
  `wecom`
- FinClaw target: roadshows, research meetings, investment committee records,
  expert calls, earnings calls, decision points, risk discussions, and follow-up
  actions.

## Productization Change

`manifest.json` now includes `meeting_minutes_boundary_proof`.

The proof records:

- authorized input counts and requested inputs;
- candidate, matched, and filtered record counts;
- upstream collector, event-kind, and source platform counts;
- participant coverage, participant reference counts, meeting URL coverage,
  attachment reference coverage, recording reference coverage, symbol matches,
  and time coverage;
- the same meeting-minutes surface summary already propagated to Investor Wiki
  evidence coverage.

The proof explicitly keeps these boundaries false:

- complete meeting history claimed;
- complete workspace claimed;
- complete meeting context claimed;
- recording body collected by default;
- direct meeting platform reconnect;
- direct final Wiki writes.

## Validation Commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- The mixed meeting fixture reads five upstream candidates.
- The lens keeps four investment meeting events and filters one non-investment
  meeting.
- `meeting_minutes_boundary_proof.proof_level` is
  `authorized_meeting_minutes_with_artifact_refs`.
- The proof reports four events, five candidates, four matched events, and one
  filtered candidate.
- The proof reports upstream counts for `meeting-artifacts`, `feishu`,
  `dingtalk`, and `wecom`.
- The proof reports participant coverage, seven participant refs, two meeting
  URL events, two attachment-ref events, one recording-ref event, one matched
  symbol event, and four timed events.
- The proof does not claim complete meeting history, complete workspace,
  complete meeting context, direct reconnect, default recording-body collection,
  or direct Wiki writes.

## Remaining Gaps

- Real Feishu/DingTalk/WeCom/Tencent Meeting account or export validation.
- Participant identity normalization against real organization/contact data.
- Attachment and recording reference validation on real authorized exports.
- Explicit recording-body authorization and no-leakage review if body
  extraction is ever added.
- False-positive review against a mixed operational/investment meeting corpus.
