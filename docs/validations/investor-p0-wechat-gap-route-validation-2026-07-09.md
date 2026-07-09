# P0 WeChat Gap Route Validation - 2026-07-09

## Scope

This validation covers `wechat-export` version `0.11.3`.

The wave hardens the generic WeChat collector package so collection-state gaps
do not look like personal communication facts or usable upstream events for the
`wechat-investment-dialogue` investor lens.

## What Changed

- Normal WeChat messages still emit `collectorx.event.v1` events with
  `kind=message`.
- Normal message events continue to route to `internal.communication.wechat`.
- Preflight and no-message packages emit one profile gap event with:
  - `data.profile_type=wechat_collection_gap`
  - `data.subtype=collector_gap`
  - `data.action_type=collector_gap`
  - `wiki_targets=["collectorx.data_quality.collection_gaps"]`
- Manifest output now separates:
  - `event_count`
  - `message_event_count`
  - `usable_event_count`
  - `gap_event_count`
- Readiness now separates:
  - `can_enter_personal_channel_lake`
  - `can_enter_data_quality_lake`
  - `can_enter_investor_lens`

## Validated Scenarios

- Normal message package with two authorized fixture messages.
- No-message package when the query returns zero owner-relevant messages.
- Missing `db_storage` preflight package from the real CLI path.

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/wechat-export/scripts/wechat_query.py \
  skills/wechat-export/tests/test_collect_package.py

.venv/bin/python skills/wechat-export/tests/test_collect_package.py
.venv/bin/python skills/wechat-export/tests/test_keycrypto.py
.venv/bin/python skills/wechat-export/tests/test_mac4_keys.py
.venv/bin/python skills/wechat-export/tests/test_multi_shard.py
```

The package fixture also invokes:

```bash
python tools/validate_collector_package.py <out-dir> --collector wechat
```

for normal message, no-message gap, and missing-DB preflight gap packages.

## Assertions

- Normal message package:
  - `manifest.event_count=2`
  - `manifest.message_event_count=2`
  - `manifest.usable_event_count=2`
  - `manifest.gap_event_count=0`
  - `collection_readiness.can_enter_personal_channel_lake=true`
  - `collection_readiness.can_enter_data_quality_lake=false`
  - message event `wiki_targets=["internal.communication.wechat"]`
- No-message and preflight gap packages:
  - `manifest.event_count=1`
  - `manifest.message_event_count=0`
  - `manifest.usable_event_count=0`
  - `manifest.gap_event_count=1`
  - `collection_readiness.can_enter_personal_channel_lake=false`
  - `collection_readiness.can_enter_data_quality_lake=true`
  - `collection_readiness.can_enter_investor_lens=false`
  - gap event `wiki_targets=["collectorx.data_quality.collection_gaps"]`
  - gap event does not include message text, raw database pages, credential
    material, or direct investment conclusions.

## Remaining Production Boundaries

- This remains a generic communication collector; investor facts must come
  through `wechat-investment-dialogue`.
- Current real-source validation remains blocked on this Mac by WeChat 4.x
  key/SIP preconditions.
- Production validation still needs authorized real WeChat Lake output,
  user-tuned contact/group/sender allowlists, and trade-adjacent backtests.
