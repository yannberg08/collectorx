# P2 Social Activity Scope Policy Validation - 2026-07-09

## Scope

This validation covers `social-activity` `0.2.7`, the generic weak-evidence
collector for user-authorized Weibo, Bilibili, and Xiaohongshu activity exports,
browser-history copies, and ZIP packages.

The goal is to narrow authorized social activity records before Lake output
while preserving weak influence metadata for records the user explicitly
authorizes.

## What Changed

- `social_activity.py collect` now accepts:
  - `--allow-platform` / `--deny-platform`
  - `--allow-action` / `--deny-action`
  - `--allow-source-app` / `--deny-source-app`
  - `--allow-domain` / `--deny-domain`
  - `--allow-creator` / `--deny-creator`
  - `--allow-topic` / `--deny-topic`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `source_audit.social_activity_scope_policy` records configured
  filters, candidate record count, filtered record count, filter reason counts,
  and `social_activity_scope_policy_filtered_all`.
- `social_activity_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the user's social activity authorization policy.
- If all candidate records are excluded by policy, readiness reports
  `scope_policy_filtered_all` and the collector does not emit a synthetic gap
  or success event.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/social-activity/scripts/social_activity.py \
  skills/social-activity/scripts/social_activity/parser.py \
  skills/social-activity/tests/test_social_activity.py
```

```bash
.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/social-activity/scripts/social_activity.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Social activity fixture validation passed.
- CLI help shows the new scope-policy arguments.
- Existing coverage still validates JSON/CSV/Excel/HTML/TXT/ZIP imports,
  Chromium browser-history copies, platform/action/field coverage, social-topic
  coverage, browser-history domain filtering, source audit, ZIP unsafe-member
  skips, weak-evidence policy, social activity boundary proof, and preview-only
  content policy.
- New scope-policy tests cover partial retention by platform/action/source-app/
  domain/creator/topic/keyword and filtered-all readiness.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Product Boundary

- The collector only emits user-authorized social activity metadata.
- Scope policy narrows authorized records; it does not claim complete platform
  history, complete creator influence, or investment conclusions.
- This pass does not claim real Weibo, Bilibili, or Xiaohongshu account export
  validation, real browser-path validation, default creator/domain allowlists,
  social-topic false-positive review, or weak-evidence backtest.
- This pass does not collect platform credentials, perform platform-wide
  scraping, mirror full creator profiles, mirror full content, or write investor
  Wiki evidence directly.
