# P0 Xueqiu Preflight Diagnosis Validation - 2026-07-09

This validation covers `xueqiu-investor-activity` version `0.3.8`.

## Scope

- Collector: `xueqiu-investor-activity`
- Goal: add a FinClaw-safe preflight that decides whether the current machine
  or user-authorized inputs can attempt real Xueqiu activity collection.
- Sources covered: authorized exports, saved pages, ZIP packages, logged-in HAR
  exports, copied Chromium/Safari browser history, and browser-history
  candidates that still require an explicit user copy.
- Non-sources: public news, whole-site timelines, browser cache files, direct
  real-account network adapters, broker trades, orders, holdings, and fund
  flows.

## Added Behavior

- `xueqiu_activity.py diagnose` emits
  `collectorx.xueqiu_activity_preflight.v1` JSON.
- `--diagnose-out` writes the same safe JSON.
- `--out-dir` writes a standard CollectorX data-quality gap package with
  `data.gap=xueqiu_preflight_diagnosis_only`.
- `--scan-browser-profiles` counts local browser history database candidates
  without reading those databases and without emitting paths.
- Diagnosis reports:
  - `collection_readiness.can_attempt_collect`
  - `can_attempt_har_collect`
  - `can_attempt_browser_history_collect`
  - `can_attempt_local_export_collect`
  - `can_prepare_authorized_browser_history_copy`
  - `can_attempt_real_account_network_collect=false`
  - `can_claim_broker_trade_collection=false`
- Events, manifest, diagnosis JSON, and SoulMirror sync metadata no longer emit
  local paths; they use `source_id`, extension, row, HAR entry, and ZIP member
  metadata instead.
- Text and raw payload output redacts inline credential assignments and masks
  Chinese mobile numbers. URLs with credential-like query strings are emitted
  without the query string.

## Privacy Boundary

- HAR request headers, cookies, authorization headers, query strings, and
  response payloads are not emitted by diagnosis.
- Browser-history preflight does not emit URLs or titles.
- Browser-profile scan does not read direct profile databases; it only counts
  candidates that the user may copy into an authorized folder.
- Public news and market timelines are not collected as personal facts.
- Xueqiu remains attention-network, opinion, saved-content, and model-portfolio
  evidence only; it is not a broker trade source.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity.py \
  skills/xueqiu-investor-activity/scripts/xueqiu_activity/parser.py \
  skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

```bash
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
```

```bash
.venv/bin/python skills/xueqiu-investor-activity/scripts/xueqiu_activity.py diagnose \
  --scan-browser-profiles \
  --collected-at 2026-07-09T13:00:00+08:00
```

```bash
.venv/bin/python skills/xueqiu-investor-activity/scripts/xueqiu_activity.py diagnose \
  --input examples/fixtures/xueqiu-investor-activity/preflight_network.har \
  --out-dir /tmp/xueqiu_preflight_fixture_package \
  --collected-at 2026-07-09T13:05:00+08:00 \
  >/tmp/xueqiu_preflight_fixture.json

.venv/bin/python tools/validate_collector_package.py \
  /tmp/xueqiu_preflight_fixture_package \
  --collector xueqiu-investor-activity \
  --require-evidence \
  --json
```

```bash
git diff --check
```

## Results

- Syntax validation passed.
- Xueqiu investor activity tests passed.
- Fixture preflight package validation passed:
  - `valid=true`
  - `event_count=1`
  - `gap_event_count=1`
  - `usable_event_count=0`
  - `gap_only=true`
- Current-machine browser profile diagnosis returned:
  - `collection_readiness.status=needs_authorized_browser_history_copy`
  - `can_attempt_collect=false`
  - `can_prepare_authorized_browser_history_copy=true`
  - `browser_profile_probe.candidate_count=4`
  - `browser_profile_probe.source_app_counts.chromium_history=4`
  - `direct_profile_databases_read=false`
- Whitespace validation passed.

## Fixture Coverage

- Added
  `examples/fixtures/xueqiu-investor-activity/preflight_network.har`.
- Fixture contains a Xueqiu HAR request with cookie/authorization/query-token
  material and an unrelated non-Xueqiu request.
- Tests assert that diagnosis and packages do not emit:
  - local temp paths
  - `SHOULD_NOT_LEAK`
  - `xq_a_token`
  - original mobile numbers
- Tests also assert a copied Chromium `History` file can be diagnosed without
  outputting history URLs or titles.

## Remaining Real Validation

- Run `diagnose --input` against a real user-exported Xueqiu HAR and verify
  the user can proceed to `collect` after approving the file.
- Run `diagnose --input` and `collect --input` against a user-copied real
  Chromium/Safari history database.
- Validate real Xueqiu account surfaces for follows, posts, comments,
  favorites, watchlist, followed portfolios, owner portfolios, and rebalancing
  histories.
- Validate real pagination behavior across timeline/favorite/comment/portfolio
  endpoints before claiming anything stronger than partial authorized input.
- Keep direct account login/API automation out of readiness until product/legal
  review approves the source boundary.
