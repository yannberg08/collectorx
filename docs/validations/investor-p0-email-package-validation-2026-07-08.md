# P0 Email Package Validation - 2026-07-08

This validation records the second productization pass for generic `email` plus
the `email-research` investor lens. No real mailbox content, credentials,
cookies, tokens, or private email bodies are committed.

## Scope

- Generic collector: `email-collector` `0.4.1`
- Investor lens: `email-research` via `investor-source-collectors` `0.1.2`
- FinClaw target: generic `collectorx.event.v1` email lake, then
  `email-research` lens evidence for investor Wiki distillation.

## Generic Email Collector

Validated capabilities:

- Imports user-authorized local EML, MBOX, JSON/JSONL/NDJSON, CSV, TSV, and ZIP
  email packages.
- Preserves ZIP provenance as `archive.zip::member`.
- Skips unsafe ZIP path traversal members.
- Captures mailbox, folder, sender, recipients, cc, subject, date, message ID,
  body preview, and attachment refs.
- Keeps full body out of events by default; full body still requires explicit
  `--event-include-body`.
- Never writes attachment bodies into events.
- Sanitizes attachment refs and `raw_ref` by dropping token/cookie/password/
  secret/session/authorization-like keys.
- IMAP collection now carries attachment metadata refs, matching the local
  import contract.

Manifest additions:

- `body_policy`
- `attachment_policy`
- `collection_audit` with input file counts, extension counts, ZIP member
  counts, skipped ZIP member counts, and supported import extensions.

## Email Research Lens

Validated lens enhancement:

- `email-research` now recognizes clear research attachment filenames such as
  deep reports, morning notes, roadshow invites, meeting notes, financial
  statements, and announcements.
- A plain email with `半导体深度报告.pdf` as an attachment is retained as
  investor evidence.
- A generic personal attachment such as a holiday photo is filtered out.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/email-collector/tests/test_events.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Covered fixtures:

- Direct event conversion without full body.
- Attachment and raw-ref sensitive-key sanitization.
- Fake IMAP multi-folder collection with attachment refs.
- Mixed local EML/JSON/CSV import package.
- ZIP package import, ZIP member provenance, unsafe member skipping.
- Missing-input gap event.
- Registration refusal for local password storage.
- `email-research` attachment filename matching.

Both test commands passed in this validation pass.

## Current Gate

- `email`: `baseline+audit`
- `email-research`: `baseline+audit`
- Real mailbox IMAP validation: still blocked until a mailbox is registered with
  user authorization.
- Real mailbox leakage review: still required before production-candidate.
- Broker/IR sender and attachment backtest against real mailboxes: still
  required for G4.
