# P0 Email Preflight Diagnosis Validation - 2026-07-09

## Scope

This validation covers `email-collector` version `0.5.9`.

The goal is to let FinClaw run a privacy-preserving readiness check before
attempting real mailbox collection. The check answers whether the user has a
registered IMAP account with available credential material or an authorized
local email root with candidate files.

This validation does not claim that a real mailbox was collected.

## Implemented

- `python skills/email-collector/scripts/email_api.py preflight --diagnose`
  emits `collectorx.email_preflight.v1`.
- `--diagnose-out <file>` writes the same JSON for FinClaw product preflight
  screens and runbooks.
- The diagnosis records:
  - registered account counts and enabled account counts
  - provider/domain summaries
  - password environment variable presence counts
  - local email root candidate counts
  - candidate format coverage for Apple Mail EMLX, Maildir, MBOX, Thunderbird
    mbox, JSON/CSV/ZIP, and related import formats
  - readiness flags for IMAP and local scan attempts
- The diagnosis does not:
  - log into IMAP
  - read message headers
  - read message bodies
  - read attachments
  - read local email file contents
  - emit secrets, password environment variable names, full email addresses,
    local paths, long numeric account fragments, or body text
- `collection_readiness` stays diagnosis-only:
  - `can_attempt_imap_collect`
  - `can_attempt_local_scan`
  - `can_claim_real_validation=false`
  - `can_enter_email_lake=false`
  - `can_feed_email_research_lens=false`

## Tests

Commands run:

```bash
.venv/bin/python -m py_compile skills/email-collector/scripts/email_api.py skills/email-collector/tests/test_events.py
.venv/bin/python skills/email-collector/tests/test_events.py
```

Result:

- `All email collector event tests passed!`

Fixture coverage added:

- Ready IMAP configuration with `password_env` present, while proving the
  secret value, password environment variable name, full mailbox address, and
  local root path are absent from diagnosis output.
- Local Maildir candidate root, while proving diagnosis does not read file
  contents and does not emit local paths, long numeric account fragments, or
  body text.

## Current Production Gap

The collector is still `baseline+audit`, not `production-candidate`.

Remaining work:

- Run the diagnosis on real user machines for Apple Mail, Thunderbird,
  Evolution/Maildir, and exported mailbox roots.
- Register and validate real mailbox accounts through `password_env`.
- Run real broker/IR sender-domain backtests for the downstream
  `email-research` lens.
- Perform no-full-body/no-attachment-body leakage review on real mailboxes.
