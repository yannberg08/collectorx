# P0 Email Research Scope Policy Validation - 2026-07-09

This validation covers the P0 `email-research` lens after adding explicit user
authorization scope filters before mailbox-derived research evidence enters the
Investor Wiki evidence package. No mailbox credentials, full private mailbox
history, or attachment bodies are collected by this lens.

## Scope

- Skill: `investor-source-collectors`
- Version: `0.1.23`
- Lens: `email-research`
- Upstream collector: `email`
- FinClaw route: broker research, morning meeting, roadshow, IR, earnings alert,
  and attachment-reference evidence for the Investor Wiki.

## Added Behavior

- `investor_sources.py collect --source email-research` accepts allow/deny
  filters for sender, sender domain, folder, mailbox, subject, attachment
  filename, email research surface, and keyword.
- Scope policy is an authorization boundary only. It does not classify
  investment relevance and does not replace the upstream generic `email`
  collector policy.
- Manifest `collection_audit.email_research_scope_policy` records configured
  filters, filtered candidate count, reason counts, and filtered-all state.
- Manifest `email_research_boundary_proof.authorization_scope_boundary` exposes
  the same policy boundary to FinClaw gating.
- When every candidate email-research record is filtered, readiness reports
  `scope_policy_filtered_all` and the lens emits an explicit
  `email_research_scope_policy_filtered_all` gap.

## Fixture Coverage

- Partial-retention fixture keeps one authorized broker research email while
  filtering an IR roadshow email by sender-domain and a private broker email by
  deny-keyword behavior.
- Filtered-all fixture verifies an upstream broker email with a non-matching
  sender-domain allowlist emits an explicit filtered-all gap instead of looking
  like a missing email Lake.
- Cross-lens fixture verifies email-research-only scope parameters are ignored
  by non-email lenses and cannot accidentally filter Xueqiu activity evidence.
- Existing coverage still validates email-research surfaces, sender-domain
  counts, body-preview boundaries, attachment-reference boundaries,
  package validation, and no attachment-body collection.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/profiles.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
```

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Investor-source fixture validation passed.
- CLI help shows the new email-research scope-policy arguments.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Expected Manifest Signals

- `collection_audit.email_research_scope_policy`
- `collection_audit.email_research_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `email_research_boundary_proof.authorization_scope_boundary`
- `email_research_boundary_proof.authorization_scope_boundary.filter_reason_counts`

## Remaining Real Validation

- Register a real mailbox with `password_env` and run `email` followed by
  `email-research` under realistic broker/IR sender-domain and folder policies.
- Validate real Apple Mail, Thunderbird, and Maildir local roots feeding the same
  lens policy.
- Run no-full-body and no-attachment-body leakage review on real mailbox
  outputs before promoting beyond G2.
