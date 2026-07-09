# P0 WeChat Local-Source Diagnosis Validation

Date: 2026-07-09

Scope:

- Collector: `wechat`
- Skill: `wechat-export`
- Version: `0.11.4`
- Goal: add a FinClaw-safe preflight that reports whether the current user
  environment can attempt WeChat collection before reading messages.

## Added Behavior

- `wechat_query.py --diagnose` emits `collectorx.wechat_preflight.v1` JSON.
- `wechat_query.py --diagnose-out <file>` writes the same JSON for FinClaw
  runbooks and product screens.
- Diagnosis records:
  - runtime platform
  - dependency availability
  - SIP status on macOS
  - sanitized store probe counts
  - sanitized key-material presence
  - `collection_readiness.status`
  - `collection_readiness.can_attempt_collect`
  - `collection_readiness.can_claim_real_validation=false`
- Diagnosis explicitly sets:
  - `message_text_read=false`
  - `contacts_read=false`
  - `raw_database_pages_read=false`
  - `credentials_collected=false`
  - `keys_emitted=false`
  - `paths_emitted=false`

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/wechat-export/scripts/wechat_query.py \
  skills/wechat-export/tests/test_collect_package.py

.venv/bin/python skills/wechat-export/tests/test_collect_package.py

.venv/bin/python skills/wechat-export/scripts/wechat_query.py \
  --diagnose \
  --db-dir /tmp/collectorx-missing-wechat-db \
  --diagnose-out /tmp/collectorx-wechat-diagnose.json

.venv/bin/python skills/wechat-export/scripts/wechat_query.py --diagnose \
  > /tmp/collectorx-wechat-diagnose-auto.json

.venv/bin/python -m json.tool /tmp/collectorx-wechat-diagnose-auto.json
```

## Results

- WeChat package tests passed.
- Missing `--db-dir` diagnosis returned:
  - `collection_readiness.status=needs_readable_wechat_db_dir`
  - `collection_readiness.can_attempt_collect=false`
  - `collection_readiness.can_claim_real_validation=false`
- The missing local path was not written to stdout or the saved diagnosis file.
- Auto diagnosis stdout was valid JSON.
- Current-machine auto diagnosis returned:
  - `platform=macos`
  - `store_probe.mac_detected_version=mac4`
  - `store_probe.db_storage_detected=true`
  - `store_probe.db_storage_exists=true`
  - `store_probe.db_storage_readable=true`
  - `store_probe.db_file_count=0`
  - `environment.sip_status=enabled`
  - `environment.sqlcipher3_available=false`
  - `key_probe.key_file_present=false`
  - `collection_readiness.status=needs_readable_wechat_db_dir`

## Boundary

This is a real preflight result on the current machine, not real WeChat message
collection. No messages, contacts, database pages, keys, credentials, or local
paths are emitted by the diagnosis. The next production gate remains a real
authorized `wechat --collect --out-dir` run that produces retained message
events, validates the package, and then feeds `wechat-investment-dialogue` with
user-approved chat/sender scope.
