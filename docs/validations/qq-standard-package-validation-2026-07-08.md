# QQ Standard Package Validation - 2026-07-08

## Scope

This validation covers the supporting `qq` collector package contract for
FinClaw.

The goal is to make QQ callable like the other CollectorX package collectors:

```bash
python3 skills/qq-export/scripts/qq_query.py \
  --db-dir <authorized-qq-db-dir> \
  collect \
  --out-dir <out-dir>
```

## Validated Outputs

- `lake/qq/events.jsonl`
- `manifest.json`
- `qq.collect.json`
- `SUMMARY.md`

## What The Manifest Records

- readable database status and local source audit
- filter policy, including whether an owner UIN was provided without writing
  the UIN itself
- field coverage for chat, sender, time, and text
- private/group chat counts and message direction counts
- generic communication evidence policy
- collection readiness and next user action

## Test Coverage

Validated with:

```bash
.venv/bin/python -m py_compile \
  skills/qq-export/scripts/qq_query.py \
  skills/qq-export/tests/test_parser.py

.venv/bin/python skills/qq-export/tests/test_parser.py
```

The test suite covers:

- QQ message normalization
- SQLite message-table reading
- CollectorX event conversion
- `collect --out-dir` standard package output
- package-gate validation for the generated QQ package
- missing-database gap package output
- QQ NT wrapped database probe and clean-copy preparation
- decrypted QQ NT message table parsing
- contacts/groups/recent-contact entity parsing
- local key-capture precondition diagnostics

## Product Boundary

`qq` is a generic communication collector. It may enter the FinClaw Lake, but it
must not write investor Wiki evidence directly. FinClaw should run an investor
communication lens before using QQ-derived messages as investment rationale,
influence-source, or collaboration evidence.

## Remaining Gaps

- Real authorized/decrypted QQ NT message validation is still pending on the
  current machine because passphrase capture remains blocked by the local
  LLDB/SIP precondition.
- Windows/Linux paths need real-device validation with authorized readable QQ
  data.
- Investor communication lens routing and backtesting against trades/reviews is
  still required before broad production exposure.
