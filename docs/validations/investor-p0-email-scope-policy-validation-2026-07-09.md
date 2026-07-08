# P0 Email Scope Policy Validation - 2026-07-09

This validation records the P0 `email` collector pass that adds explicit user
authorization scope filters before IMAP or local email records enter the Lake.
No real mailbox content, credentials, cookies, tokens, or private bodies are
committed.

## Scope

- Collector: `email-collector`
- Version: `0.5.6`
- FinClaw route: generic `email` Lake first, then `email-research` lens for
  investor Wiki evidence.

## Added Behavior

- `email_api.py collect` and `email_api.py import` accept allow/deny filters for
  mailbox, folder, sender, sender domain, recipient, subject, attachment name,
  and keyword.
- The policy is an authorization boundary only. It does not classify investment
  relevance and does not replace `email-research`.
- Manifest `collection_audit.email_scope_policy` records configured filters,
  candidate email count, retained count, filtered count, reason counts, and
  `filtered_all`.
- Manifest `mailbox_boundary_proof.authorization_scope_boundary` exposes the
  same policy boundary to FinClaw gating.
- When every candidate email is filtered, the collector emits
  `email_scope_policy_filtered_all` and readiness reports
  `scope_policy_filtered_all`.

## Fixture Coverage

- IMAP fixture fetches two messages from `INBOX` and `Sent`, then keeps only the
  authorized folder.
- Local JSON export fixture has four messages and verifies mailbox/folder,
  sender-domain, recipient, subject, attachment, keyword, and deny-keyword
  policy behavior.
- Filtered-all fixture verifies the package emits a gap event instead of
  claiming the authorized export is missing.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/scripts/email_collector/events.py \
  skills/email-collector/tests/test_events.py
.venv/bin/python skills/email-collector/tests/test_events.py
.venv/bin/python skills/email-collector/scripts/email_api.py collect --help
.venv/bin/python skills/email-collector/scripts/email_api.py import --help
```

Project-level gates passed:

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Result:

- Passed.

## Expected Manifest Signals

- `collection_audit.email_scope_policy.configured`
- `collection_audit.scope_policy_candidate_email_count`
- `collection_audit.scope_policy_retained_email_count`
- `collection_audit.scope_policy_filtered_email_count`
- `collection_audit.scope_policy_filter_reason_counts`
- `collection_audit.email_scope_policy_filtered_all`
- `mailbox_boundary_proof.authorization_scope_boundary`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.

## Remaining Real Validation

- Register a real mailbox with `password_env` and verify sender-domain and
  folder policies against a real broker/IR mailbox sample.
- Validate real Apple Mail, Thunderbird, Maildir, and Chinese email-client local
  roots under the same scope-policy filters.
- Run leakage review on real outputs: full body remains opt-in, attachment
  bodies remain excluded, and path/account secrets remain masked.
