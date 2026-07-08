# FinClaw Invocation Contract Coverage Validation - 2026-07-08

This validation records the catalog-coverage and invocation-precondition gate
for FinClaw investor-avatar collectors.

## Scope

- Make every FinClaw investor catalog entry product-callable with a
  machine-readable invocation contract.
- Close the catalog gap for `ths-watchlist`.
- Make non-investor collector YAML exclusions explicit.
- Add project validation so future collectors cannot silently miss the catalog
  or invocation precondition layer.

## Code And Catalog Changes

- Added `collectors/finclaw-invocation-contracts.json`.
- Added `ths-watchlist` to `collectors/finclaw-investor-catalog.json`.
- Added `catalog_exclusions` for `doubao`, which remains outside the
  investor-avatar catalog until its investor-specific scope and evidence
  boundaries are reviewed.
- Updated `tools/validate_project.py` so:
  - every collector YAML is cataloged or explicitly excluded;
  - every catalog entry has one invocation contract;
  - contracts use declared authorization modes, product surfaces, and evidence
    roles;
  - lens contracts use `lake-lens` and declare upstream collectors;
  - production-candidate and supporting entries use matching product surfaces.
- Aligned `skills/ths-watchlist/.collectorx.json` status to `baseline+audit`.

## Validation

```bash
python3 -m json.tool collectors/finclaw-investor-catalog.json
python3 -m json.tool collectors/finclaw-invocation-contracts.json
python3 -m json.tool skills/ths-watchlist/.collectorx.json
.venv/bin/python tools/validate_project.py
```

Result:

- JSON validation passed.
- Project validation passed.
- The new `validate_invocation_contracts` gate ran and passed.
- The strengthened catalog coverage check confirms `ths-watchlist` is in the
  investor catalog and `doubao` has an explicit non-investor exclusion.

## Non-Goals

- No collector readiness was promoted to production.
- No new real-account validation is claimed.
- Invocation contracts do not replace real collector output validation; FinClaw
  must still validate every package and Investor Wiki evidence file before
  durable ingestion.
