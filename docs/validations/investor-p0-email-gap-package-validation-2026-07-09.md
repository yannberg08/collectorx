# P0 Email Gap Package Validation - 2026-07-09

This validation records the gap-package hardening pass for the P0 email channel
and the `email-research` investor lens.

## Scope

- Generic collector: `email-collector` `0.5.7`
- Investor lens helper: `investor-source-collectors` `0.1.25`
- Lens covered by this pass: `email-research`

## What Changed

- `email` now emits validator-safe `kind=profile` gap events for:
  - missing IMAP registered account;
  - missing authorized local export;
  - IMAP no-message windows;
  - IMAP collection failures;
  - email authorization scope-policy filtered-all runs.
- `email` manifests now separate:
  - `event_count`
  - `email_event_count`
  - `gap_event_count`
- Email gap events carry candidate, retained, filtered, and reason-count
  metadata when scope-policy filtering is involved.
- Generic investor-source lens gaps now emit validator-safe profile events
  routed to `collectorx.data_quality.collection_gaps`.
- `email-research` filtered-all packages keep Investor Wiki evidence empty for
  generated facts while preserving a traceable data-quality gap in Lake.

## Boundary

Gap events do not claim email facts, email-research facts, investment
conclusions, complete mailbox history, mailbox passwords, OAuth tokens,
full-body capture by default, attachment-body capture, or direct investor Wiki
writes.

The generic `email` collector still does not classify investment relevance.
Only retained non-gap email events should feed the `email-research` lens.

## Verification

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/scripts/email_collector/events.py \
  skills/email-collector/tests/test_events.py \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/email-collector/tests/test_events.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Results:

```text
All email collector event tests passed.
investor-source-collectors tests passed.
finclaw catalog tests passed.
finclaw batch runner tests passed.
CollectorX validation passed.
```

The targeted tests validate normal, missing-account, missing-export, and
filtered-all email packages through `tools/validate_collector_package.py`.
They also validate the filtered-all `email-research` lens package with Investor
Wiki evidence required.

The full project validation and collector smoke suite passed after catalog,
contract, and documentation updates.

## Remaining Work

- Register a real mailbox through `password_env` and validate IMAP runs.
- Validate real Apple Mail, Thunderbird, and Maildir roots on macOS, Windows,
  and Linux.
- Run broker/IR sender and attachment-filename false-positive backtests on real
  mailboxes.
- Review full-body and attachment leakage on real private samples before
  exposing any content-expansion option.
