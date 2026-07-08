# P2 Professional Terminal Usage Scope Policy Validation - 2026-07-09

## Scope

This validation originally covered `pro-terminal-usage` `0.2.7`, the vertical professional
terminal workflow collector for user-authorized Wind, Choice, iFinD, and
Bloomberg exports. Version `0.2.8` extends the filtered-all path into a
validator-safe gap package; see
`docs/validations/investor-p2-pro-terminal-gap-package-validation-2026-07-09.md`.

The goal is to narrow authorized terminal workflow records before Lake output
while preserving workflow metadata and intensity numbers for records the user
explicitly authorizes.

## What Changed

- `pro_terminal_usage.py collect` now accepts:
  - `--allow-terminal` / `--deny-terminal`
  - `--allow-activity` / `--deny-activity`
  - `--allow-workspace` / `--deny-workspace`
  - `--allow-project` / `--deny-project`
  - `--allow-dataset` / `--deny-dataset`
  - `--allow-field` / `--deny-field`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `source_audit.pro_terminal_scope_policy` records configured filters,
  candidate record count, filtered record count, filter reason counts, and
  `pro_terminal_scope_policy_filtered_all`.
- `workflow_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the user's terminal-workflow authorization policy.
- As of version `0.2.8`, if all candidate records are excluded by policy,
  readiness reports `scope_policy_filtered_all` and the collector emits one
  `pro_terminal_scope_policy_filtered_all` profile gap event instead of an
  empty package or synthetic workflow event.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/pro-terminal-usage/scripts/pro_terminal_usage.py \
  skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py \
  skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
```

```bash
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Professional terminal fixture validation passed.
- CLI help shows the new scope-policy arguments.
- Existing coverage still validates JSON/CSV/Excel/HTML/TXT/LOG/ZIP imports,
  nested workflow sections, workbook and ZIP provenance, unsafe ZIP-member
  skips, terminal/activity/field/topic coverage, workflow surface summary,
  workflow intensity summary, unified workflow-boundary proof, source audit,
  license policy, and evidence policy.
- New scope-policy tests cover partial retention by terminal/activity/
  workspace/project/dataset/field/keyword, filtered-all readiness, and the
  follow-up validator-safe gap package.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Product Boundary

- The collector only emits user-authorized professional-terminal workflow
  metadata.
- Scope policy narrows authorized records; it does not claim complete terminal
  history, complete research workflow coverage, or investment conclusions.
- This pass does not claim real Wind, Choice, iFinD, or Bloomberg native export
  validation, legal/license review, account-level validation, workflow-topic
  false-positive review, or Windows/Linux real path validation.
- This pass does not collect credentials, license keys, authorization headers,
  vendor database mirrors, public market data mirrors, or licensed content
  bodies.
