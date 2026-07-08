# P2 Professional Terminal Gap Package Validation - 2026-07-09

## Scope

This validation covers `pro-terminal-usage` `0.2.8`, the P2 vertical collector
for user-authorized Wind, Choice, iFinD, and Bloomberg workflow metadata.

The goal is to make no-input and authorization-scope-filtered runs observable
without turning collection gaps into professional-terminal workflow facts for
FinClaw or the Investor Wiki.

## What Changed

- Normal terminal workflow events now fall back to `collected_at` when a source
  record does not expose a usable time field, so emitted Lake events satisfy the
  shared CollectorX package contract.
- No-input and no-record runs emit a validator-safe profile gap event instead
  of relying on an ambiguous package state.
- Scope-policy filtered-all runs emit one
  `pro_terminal_scope_policy_filtered_all` profile gap event instead of an
  empty `events.jsonl`.
- Gap events include non-empty `time`, `data.subtype=collector_gap`,
  `data.status`, `data.profile_type`, candidate/retained/filtered counts,
  filter reason counts, and explicit false-claim flags for terminal workflow
  facts, complete terminal history, vendor database mirroring, licensed content
  body mirroring, public market data mirroring, credentials, license keys, and
  order mutation.
- Manifest output includes `workflow_event_count` and `gap_event_count` so the
  product can distinguish usable workflow metadata from collection
  observability.
- Investor Wiki evidence counts only usable terminal workflow records; pure gap
  packages keep `generated_from.event_count=0` and do not support any 7/20
  investor subdimension.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/pro-terminal-usage/scripts/pro_terminal_usage.py \
  skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py \
  skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
```

```bash
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
```

Manual filtered-all package check:

```bash
rm -rf /tmp/pro_terminal_filtered_all_cli /tmp/pro_terminal_gap_fixture
mkdir -p /tmp/pro_terminal_gap_fixture
printf '{"usage":[{"terminal":"Choice","activity_type":"download","workspace":"Macro Desk","dataset":"EDB","fields":"M2, CPI"}]}\n' \
  > /tmp/pro_terminal_gap_fixture/terminal.json
.venv/bin/python skills/pro-terminal-usage/scripts/pro_terminal_usage.py collect \
  --input /tmp/pro_terminal_gap_fixture/terminal.json \
  --out-dir /tmp/pro_terminal_filtered_all_cli \
  --allow-terminal wind \
  --collected-at 2026-07-08T04:30:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/pro_terminal_filtered_all_cli \
  --collector pro-terminal-usage \
  --require-evidence \
  --json
```

Project gates:

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Expected Signals

- `lake/pro-terminal-usage/events.jsonl` contains exactly one profile gap event
  for filtered-all and no-input packages.
- `manifest.event_count=1`.
- `manifest.workflow_event_count=0`.
- `manifest.gap_event_count=1`.
- `manifest.collection_readiness.status=scope_policy_filtered_all` for
  filtered-all packages.
- `manifest.collection_readiness.can_enter_finclaw=false`.
- `investor_wiki_evidence.v1.json.generated_from.event_count=0`.
- The gap event does not include the raw local input path, credential, cookie,
  token, license key, vendor database content, licensed content body, public
  market data mirror, order mutation, or a claimed terminal workflow fact.

## Product Boundary

- The collector remains a personal workflow metadata collector, not a market
  data, vendor database, or licensed content mirroring tool.
- Gap events are package observability only. They can tell FinClaw why a
  collection did not yield usable workflow evidence, but they cannot become
  Investor Wiki facts.
- This pass does not claim real Wind, Choice, iFinD, or Bloomberg native export
  validation, account-level license review, complete terminal history,
  workflow-topic false-positive review, or Windows/Linux real path validation.
