# P0 Email Readiness Gate Validation - 2026-07-09

This validation covers `email-collector` version `0.5.8` and
`investor-source-collectors` version `0.1.27`.

## Scope

- Generic collector: `email`
- Investor lens: `email-research`
- Upstream/downstream flow: `lake/email/events.jsonl` -> `email-research`

## What Changed

- Email package readiness now separates:
  - `can_enter_email_lake`
  - `can_enter_data_quality_lake`
  - `can_feed_email_research_lens`
  - `email_event_count`
  - `gap_event_count`
- `mailbox_boundary_proof` mirrors `can_feed_email_research_lens`, so FinClaw
  can block the `email-research` lens when the upstream email package is only a
  collection gap.
- `email-research` manifests now include `email_research_event_count` alongside
  `usable_event_count` and `gap_event_count`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/scripts/email_collector/events.py \
  skills/email-collector/tests/test_events.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/email-collector/tests/test_events.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python -m json.tool skills/email-collector/.collectorx.json >/dev/null
.venv/bin/python -m json.tool skills/investor-source-collectors/.collectorx.json >/dev/null
.venv/bin/python -m json.tool collectors/finclaw-investor-catalog.json >/dev/null
.venv/bin/python -m json.tool collectors/finclaw-invocation-contracts.json >/dev/null
```

## Results

- Syntax validation passed.
- `skills/email-collector/tests/test_events.py` passed.
- `skills/investor-source-collectors/tests/test_investor_sources.py` passed.
- JSON metadata and FinClaw catalog/contract validation passed.
- Normal IMAP fixture packages now assert:
  - `can_enter_email_lake=true`
  - `can_enter_data_quality_lake=false`
  - `can_feed_email_research_lens=true`
- Missing-account gap packages now assert:
  - `can_enter_email_lake=false`
  - `can_enter_data_quality_lake=true`
  - `can_feed_email_research_lens=false`
- `email-research` filtered-all gap packages now assert:
  - `email_research_event_count=0`
  - `usable_event_count=0`
  - `gap_event_count=1`

## Boundary

This pass does not register a real mailbox on this machine. It hardens the
package contract so FinClaw can safely decide whether to run `email-research`
after an email package and can keep mailbox collection gaps out of Investor Wiki
facts.
