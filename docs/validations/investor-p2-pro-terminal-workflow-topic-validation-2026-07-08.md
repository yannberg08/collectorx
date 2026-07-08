# P2 Professional Terminal Workflow Topic Validation - 2026-07-08

This validation records the workflow-topic pass for `pro-terminal-usage`.

## Scope

Collector path:

- Vertical source: `pro-terminal-usage`
- Skill: `skills/pro-terminal-usage`
- FinClaw target: professional terminal workflow evidence for the investor
  avatar's research habits, capability circle, monitoring rules, information
  sources, and review discipline

This pass remains workflow-metadata-only. It does not mirror Wind, Choice,
iFinD, Bloomberg, or other vendor databases; it does not copy licensed content
bodies, public market data, research report bodies, credentials, authorization
headers, or license material.

## Product Changes

- Upgraded `pro-terminal-usage` to `0.2.4`.
- Added per-event `workflow_topics`, `primary_workflow_topic`, and
  `workflow_topic_terms`.
- Added topic coverage to `manifest.workflow_surface_summary`:
  - expected workflow topics
  - workflow topic counts
  - primary workflow topic counts
  - terminal/topic counts
  - activity/topic counts
  - missing expected workflow topics
  - events with workflow topics
- Mirrored `workflow_surface_summary` into
  `investor_wiki_evidence.v1.json`.
- Covered macro policy, market strategy, industry themes, company
  fundamentals, valuation models, credit/fixed income, factor/quant,
  portfolio monitoring, data export, and HK/US market workflow themes.

## Fixture Validation

Validated scenarios:

- Wind/Choice/iFinD/Bloomberg package fixtures still emit the expected
  workspace, watchlist, search, download, model-template, and factor-attention
  events.
- Bloomberg credit workspace/search/template/factor records are classified into
  credit/fixed-income, industry, valuation, factor/quant, and HK/US workflow
  topics where supported by metadata.
- Wind macro export records are classified into macro policy and data export.
- Choice and iFinD watchlists are classified into strategy, portfolio
  monitoring, HK/US, or industry themes where supported by metadata.
- The manifest reports all expected workflow topics covered in the fixture.
- Evidence coverage mirrors workflow-topic availability for Wiki distillation.
- Source audit, ZIP provenance, unsafe ZIP member skipping, credential/license
  filtering, content preview cap, license policy, and evidence policy remain
  covered.

Commands:

```bash
python3 /Users/pengyingan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/pro-terminal-usage
python3 -m json.tool skills/pro-terminal-usage/.collectorx.json
python3 -m json.tool collectors/finclaw-investor-catalog.json
.venv/bin/python -m py_compile skills/pro-terminal-usage/scripts/pro_terminal_usage/parser.py skills/pro-terminal-usage/scripts/pro_terminal_usage.py skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
.venv/bin/python skills/pro-terminal-usage/tests/test_pro_terminal_usage.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

Result:

- Passed.

## Current Gate

- Authorized local workflow export import: G1/G2 baseline+audit.
- Terminal, activity, field, topic, source-audit, license, and evidence
  manifests: G1/G2 baseline+audit.
- Real Wind/Choice/iFinD/Bloomberg account or native export validation: not
  done in this pass.
- Licensed content redistribution claim: false.

## Remaining Before Production Candidate

- Validate real Wind user workspace/export artifacts.
- Validate real Choice user workspace/export artifacts.
- Validate real iFinD user workspace/export artifacts.
- Validate real Bloomberg workflow exports without mirroring licensed content.
- Backtest workflow-topic false positives on real user exports.
- Validate Windows/macOS/Linux path, workbook, encoding, and timezone variants.
