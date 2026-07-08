# P1 Meeting Decision/Action Validation - 2026-07-08

This validation records the meeting decision/action surface pass for
`meeting-artifacts` and the `meeting-minutes` investor lens.

## Scope

- Skill: `meeting-artifacts` `0.3.2`
- Skill: `investor-source-collectors` `0.1.19`
- Collector: `meeting-artifacts`
- Lens: `meeting-minutes`
- FinClaw target: roadshow, research meeting, investment committee, expert-call,
  earnings-call, decision, risk, and follow-up evidence for the investor avatar.

## Productization Change

Generic meeting artifacts now preserve meeting-decision structure from
authorized minutes/transcripts/platform exports:

- participant-role hints inferred from authorized participant fields;
- action items, decision points, risk items, and mentioned symbols extracted
  from structured fields and text;
- attachment refs and recording refs kept as pointers only;
- `artifact_ref_summary` explicitly records that external refs were not fetched
  and recording bodies were not collected.

`meeting-minutes` now propagates these fields into:

- `manifest.lens_surface_summary`;
- `manifest.meeting_minutes_boundary_proof.meeting_context_boundary`;
- `manifest.meeting_minutes_boundary_proof.decision_action_boundary`;
- `investor_wiki_evidence.v1.json` coverage summaries.

## Validation Commands

```bash
.venv/bin/python skills/meeting-artifacts/tests/test_meeting_artifacts.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile \
  skills/meeting-artifacts/scripts/meeting_artifacts/events.py \
  skills/meeting-artifacts/scripts/meeting_artifacts/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Verified Behavior

- Local minutes/transcript fixtures extract participant-role counts,
  action-item, decision-point, risk-item, and mentioned-symbol surfaces.
- Platform-export fixtures preserve recording refs as pointers and keep
  `recording_body_collected=false`.
- ZIP fixtures still skip unsafe members and preserve archive provenance.
- The mixed `meeting-minutes` lens fixture keeps four investment meetings,
  filters one non-investment meeting, and reports participant roles, decision
  points, action items, risk items, mentioned symbols, attachment refs,
  recording refs, and the stronger
  `authorized_meeting_minutes_with_decision_action_surface` proof level.
- Investor Wiki evidence receives the same decision/action surface counts while
  retaining the generic-to-lens boundary.

## Remaining Gaps

- Real Feishu/DingTalk/WeCom/Tencent Meeting account or export validation.
- Speaker identity normalization across real platforms.
- Real attachment/recording pointer validation under user authorization.
- Recording-body ingestion remains out of scope by default and requires a
  separate explicit authorization path.
- False-positive review against mixed personal/work/investment meeting corpora.
