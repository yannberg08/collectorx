# P0/P2 Xueqiu and Social Fixture E2E Validation - 2026-07-09

Status: `completed-offline-fixture`

## Scope

This pass adds stable, checked-in offline fixtures for the P0
`xueqiu-investor-activity` collector and the P2 `social-activity` to
`social-investment-influence` flow.

It validates repeatable package and lens behavior. It does not claim real
Xueqiu, Weibo, Bilibili, or Xiaohongshu account validation.

## Fixtures Added

- `examples/fixtures/xueqiu-investor-activity/activity_export.json`
- `examples/fixtures/social-activity/social_activity_export.json`

The Xueqiu fixture covers:

- watchlist
- post/review
- favorite
- followed user
- portfolio activity

The social fixture covers:

- Weibo favorite and follow
- Bilibili watch and like
- Xiaohongshu favorite
- investment-topic records and an entertainment decoy

## Test Coverage Added

- `skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py`
  - validates 5 usable Xueqiu activity events from the fixed fixture
  - checks `activity_event_count`, activity surface counts, evidence
    `generated_from` raw/gap/usable alignment, non-broker-trade posture, and
    7/20 Investor Wiki evidence contract
  - confirms secret-shaped fixture markers do not appear in emitted events
- `skills/social-activity/tests/test_social_activity.py`
  - validates 5 generic social events from the fixed fixture
  - confirms generic `social-activity` remains weak evidence and cannot feed
    Investor Wiki directly
  - feeds the generated `lake/social-activity/events.jsonl` into
    `social-investment-influence`
  - validates 3 retained weak influence events and confirms the entertainment
    like plus plain creator follow do not become lens facts
  - confirms the lens remains weak evidence requiring corroboration and cannot
    claim an investment conclusion

## Validation Commands

```bash
.venv/bin/python skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py
.venv/bin/python skills/social-activity/tests/test_social_activity.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/test_collector_package_validator.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
```

Manual package checks:

```bash
rm -rf /tmp/xueqiu_fixture_probe
.venv/bin/python skills/xueqiu-investor-activity/scripts/xueqiu_activity.py collect \
  --input examples/fixtures/xueqiu-investor-activity/activity_export.json \
  --out-dir /tmp/xueqiu_fixture_probe \
  --collected-at 2026-07-09T11:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/xueqiu_fixture_probe \
  --collector xueqiu-investor-activity \
  --require-evidence \
  --json

rm -rf /tmp/social_fixture_probe /tmp/social_lens_fixture_probe
.venv/bin/python skills/social-activity/scripts/social_activity.py collect \
  --input examples/fixtures/social-activity/social_activity_export.json \
  --out-dir /tmp/social_fixture_probe \
  --collected-at 2026-07-09T11:00:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/social_fixture_probe \
  --collector social-activity \
  --json
.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source social-investment-influence \
  --input /tmp/social_fixture_probe/lake/social-activity/events.jsonl \
  --out-dir /tmp/social_lens_fixture_probe \
  --collected-at 2026-07-09T11:10:00+08:00
.venv/bin/python tools/validate_collector_package.py \
  /tmp/social_lens_fixture_probe \
  --collector social-investment-influence \
  --require-evidence \
  --json
```

## Results

- Xueqiu fixture package: 5 usable activity events, evidence present, validator
  `valid=true`.
- Social fixture package: 5 usable social activity events, no direct Investor
  Wiki evidence, validator `valid=true`.
- Social investment lens package: 3 usable weak influence events, evidence
  present, validator `valid=true`.
- Gap/data-quality routes remain excluded from Wiki facts.

## Boundary

- This validates stable offline fixture and package semantics only.
- Xueqiu still needs real account/HAR/browser-history pagination validation.
- Weibo, Bilibili, and Xiaohongshu still need real export/browser-history path
  validation, creator/domain allowlists, topic false-positive review, and weak
  evidence backtesting against stronger research/trade sources.
