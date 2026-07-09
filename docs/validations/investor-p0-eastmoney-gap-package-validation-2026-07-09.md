# P0 EastMoney Gap Package Validation - 2026-07-09

## Scope

This validation covers `eastmoney-portfolio` version `0.7.4`.

The wave hardens EastMoney filtered-all authorization-scope output so FinClaw
can ingest a traceable package without treating collection-state evidence as a
real user investment fact.

## What Changed

- `eastmoney_scope_policy_filtered_all` now emits a validator-safe Lake event.
- The normalized Lake event is `kind=profile` with
  `data.source_kind=data_gap`.
- Gap events route to `collectorx.data_quality.collection_gaps`.
- Manifest and structured profile now separate:
  - `event_count`
  - `usable_event_count`
  - `gap_event_count`
  - `strong_trade_event_count`
  - `lake_kind_counts`
- `investor_wiki_evidence.v1.json` counts only retained non-gap EastMoney
  business events. Pure gap packages report `generated_from.event_count=0`.

## Validated Scenarios

- Windows code-level fixture package.
- Linux code-level probe fixture.
- Full strong-trade fixture package with asset, position, execution, order, and
  fund-flow rows.
- Retained authorization-scope package with one EastMoney trade execution.
- Filtered-all authorization-scope package with one data-quality gap and zero
  usable business events.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/eastmoney-portfolio/scripts/eastmoney/local_collect.py \
  skills/eastmoney-portfolio/tests/test_local_collect.py

.venv/bin/python skills/eastmoney-portfolio/tests/test_local_collect.py
.venv/bin/python skills/eastmoney-portfolio/tests/test_parser.py
```

The fixture suite also invokes:

```bash
python tools/validate_collector_package.py <out-dir> \
  --collector eastmoney-investor-v2 \
  --require-evidence \
  --json
```

for Windows simulation, full strong-trade, retained scope-policy, and
filtered-all gap packages.

## Assertions

- Filtered-all package:
  - `manifest.event_count=1`
  - `manifest.usable_event_count=0`
  - `manifest.gap_event_count=1`
  - `manifest.strong_trade_event_count=0`
  - `manifest.lake_kind_counts.profile=1`
  - Lake event `kind=profile`
  - Lake event `data.gap=eastmoney_scope_policy_filtered_all`
  - Lake event `data.profile_type=eastmoney_collection_gap`
  - `investor_wiki_evidence.v1.json.generated_from.event_count=0`
  - `investor_wiki_evidence.v1.json.generated_from.raw_event_count=1`
  - `investor_wiki_evidence.v1.json.generated_from.gap_event_count=1`
- Strong-trade fixture:
  - `manifest.strong_trade_event_count=8`
  - `manifest.gap_event_count=3`
  - Lake kind counts include `trade=5`, `holding=3`, and profile gap/status
    events.
- All generated packages pass the shared CollectorX package validator with
  Investor Wiki evidence required.

## Remaining Production Boundaries

- Current production-candidate proof is on the current macOS environment and
  fixture-backed Windows/Linux code paths.
- Windows and Linux still require real-device EastMoney validation.
- More account states should be sampled: unlocked, locked, no positions,
  partial permissions, multi-account, and broker-specific table variants.
- This collector remains read-only: it must not ask for trading passwords,
  mutate orders, transfer funds, mirror raw network payloads, or claim complete
  broker history without observed strong tables.
