# P0 Xueqiu Evidence Observability Validation - 2026-07-09

## Scope

This validation covers:

- `xueqiu-watchlist` version `0.3.4`
- `xueqiu-investor-activity` version `0.3.7`

The change aligns both Xueqiu P0 collectors with the Investor Wiki evidence
observability format already used by China Wealth, Research Documents, and
EastMoney.

## Behavior

- `investor_wiki_evidence.v1.json.generated_from.event_count` counts only
  usable Xueqiu watchlist or activity events.
- `generated_from.raw_event_count` counts all Lake events emitted in the
  package.
- `generated_from.gap_event_count` counts profile collection-gap events.
- Gap events are routed only to `collectorx.data_quality.collection_gaps`.
- Gap events do not become Investor Wiki route facts.
- Gap-only packages keep all Investor Wiki dimension `evidence_count` values at
  zero.

## Covered Scenarios

- Normal usable watchlist package.
- Watchlist no-input gap package.
- Watchlist filtered-all authorization-scope gap package.
- Normal usable investor-activity package.
- Investor-activity no-input gap package.
- Investor-activity filtered-all authorization-scope gap package.

## Verification Commands

```bash
.venv/bin/python skills/xueqiu-watchlist/tests/test_parser.py
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
git diff --check
```

## Results

- `xueqiu-watchlist` fixture suite passed.
- `xueqiu-investor-activity` fixture suite passed.
- `git diff --check` passed.

## Integration Notes

- Main-thread catalog and invocation-contract files still need to consume the
  version bumps if they publish skill versions centrally.
- Existing vertical readiness gates are unchanged: business lake uses usable
  events, data-quality lake uses gap events, and Investor Wiki feed readiness
  remains false for gap-only packages.
