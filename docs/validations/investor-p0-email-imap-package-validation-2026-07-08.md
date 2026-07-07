# P0 Email IMAP Package Validation - 2026-07-08

This validation records the P0 email collector pass that makes registered IMAP
mailboxes callable by FinClaw through the standard CollectorX package contract.
No real mailbox content, credentials, cookies, tokens, or private email bodies
are committed.

## Scope

- Generic collector: `email-collector` `0.5.0`
- Investor lens: `email-research` via `investor-source-collectors`
- FinClaw target: generic `collectorx.event.v1` email lake, then
  `email-research` lens evidence for investor Wiki distillation.

## Product Change

`email_api.py collect` now supports:

```bash
python3 skills/email-collector/scripts/email_api.py collect \
  --account all \
  --out-dir <out-dir>
```

The command writes:

- `lake/email/events.jsonl`
- `manifest.json`
- `SUMMARY.md`

Local authorized export import remains available through:

```bash
python3 skills/email-collector/scripts/email_api.py import \
  --input <authorized-email-export-or-folder> \
  --out-dir <out-dir>
```

## Manifest Coverage

The IMAP package manifest records:

- configured and selected account counts;
- account status counts;
- folder status counts;
- matched message count;
- fetched message count;
- skipped fetch count;
- per-account provider, host, folders, days, limit, and status;
- per-folder search/fetch counts and status;
- field coverage for mailbox, folder, sender, recipients, subject, body preview,
  attachment refs, and message IDs;
- body policy and attachment policy;
- generic-to-lens evidence policy.

Gap packages distinguish:

- `email_imap_account_missing`;
- `email_imap_no_messages`;
- `email_imap_collection_failed`.

## Boundaries

- Full email bodies are excluded by default and require explicit
  `--event-include-body`.
- Attachment bodies are never written into events.
- IMAP passwords or app passwords must come from environment variables in normal
  registration flows and are never written to package output.
- Generic `email` evidence does not become investor Wiki evidence directly.
  FinClaw must run `email-research` for broker research, IR, roadshow, and
  research attachment evidence.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/email-collector/tests/test_events.py
```

Covered fixtures:

- fake IMAP multi-folder collection into a standard package;
- account and folder audit counts;
- field coverage and evidence policy in manifest;
- missing registered mailbox gap package;
- local import package and ZIP provenance retained from prior pass;
- no full body by default;
- attachment and raw-ref sensitive-key sanitization.

## Real Validation Status

On this machine, `email_api.py status` reports no registered mailbox account.
Therefore this pass does not claim real mailbox G3 validation.

Next real-account steps:

- register a user-authorized mailbox with `--password-env`;
- run `collect --account all --out-dir <out-dir>` against the mailbox;
- run `email-research` on `lake/email/events.jsonl`;
- review broker/IR sender false positives;
- run a no-full-body leakage review on real mailbox output.
