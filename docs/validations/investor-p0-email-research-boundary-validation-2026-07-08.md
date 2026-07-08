# P0 Email Research Boundary Validation - 2026-07-08

## Purpose

Validate that the P0 `email-research` lens can turn authorized `email`
Lake events into investor Wiki evidence with explicit surface classification
and mailbox/content boundaries.

## Scope

- `skills/investor-source-collectors/scripts/investor_sources/events.py`
- `skills/investor-source-collectors/tests/test_investor_sources.py`
- `skills/investor-source-collectors/VERSION`
- `skills/investor-source-collectors/.collectorx.json`
- `collectors/lenses/email-research.yaml`
- `collectors/finclaw-investor-catalog.json`
- `docs/finclaw-integration-guide.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- Generic `email` remains the raw mailbox/export collector.
- `email-research` is a lens: it consumes `lake/email/events.jsonl`, filters
  investment-related mail, and does not reconnect to mailboxes directly.
- The lens records email research surfaces for morning meetings, broker
  research reports, roadshow invitations, company IR threads,
  earnings/announcement alerts, research attachment refs, and portfolio alerts.
- `manifest.email_research_boundary_proof` records sender-domain, mailbox,
  folder, timestamp, message-id, body-preview, attachment-ref, and
  research-attachment coverage.
- Full email bodies are not placed into Wiki by default.
- Attachment bodies are not collected by the lens.
- The lens never claims complete mailbox history or complete thread context.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Fixture Validation

- Input contains four upstream `email` lake events:
  - broker morning meeting with a research attachment ref
  - company IR roadshow invitation with an attachment ref
  - earnings/announcement alert
  - unrelated personal photo mail
- `email-research` emits three investor evidence events and filters the
  unrelated personal mail.
- `manifest.lens_surface_summary` reports the expected surfaces, sender-domain
  counts, body-preview coverage, attachment-ref coverage, research attachment
  coverage, message-id coverage, and time coverage.
- `manifest.email_research_boundary_proof` reports
  `authorized_email_research_with_research_attachment_refs` and keeps
  full-body Wiki inclusion, attachment-body collection, direct email reconnect,
  and complete-mailbox claims false.
- The generated package passes `tools/validate_collector_package.py` with
  `--collector email-research --require-evidence`.

## Result

- Investor source collector tests passed.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This pass does not validate a real registered mailbox, real broker/IR sender
allowlists, attachment-body extraction, encrypted attachments, or real mailbox
no-full-body leakage review.
