# P0 Email Local-Scan Validation - 2026-07-08

## Scope

Validate that `email` can collect from a user-authorized local mail root without
requiring a manually prepared export folder, while preserving the generic-email
boundary required before the `email-research` investor lens.

## Files Changed

- `skills/email-collector/scripts/email_api.py`
- `skills/email-collector/tests/test_events.py`
- `skills/email-collector/VERSION`
- `skills/email-collector/.collectorx.json`
- `skills/email-collector/SKILL.md`
- `collectors/generic/email.yaml`
- `collectors/finclaw-investor-catalog.json`
- `collectors/finclaw-invocation-contracts.json`
- Product docs and roadmap files.

## Product Behavior

- `email_api.py import --local-scan --container-root <authorized-email-root>`
  scans a user-authorized local mail root.
- `--platform auto|mac|windows|linux|generic` records the local adapter used for
  discovery.
- `--probe-export <path>` writes a safe probe report before package output.
- Existing `import --input` still supports EML, Apple Mail EMLX, Maildir, MBOX,
  JSON/JSONL/NDJSON, CSV/TSV, and ZIP packages.

## Boundary Assertions

- `email` remains a generic personal-channel Lake source.
- Investor Wiki use still requires the `email-research` lens.
- Full email bodies are excluded from events unless `--event-include-body` is
  explicitly supplied.
- Attachment bodies are never written; only filename, content type, and size
  refs are retained.
- Probe output, manifest local-scan fields, and event raw refs mask path email
  addresses and long numeric account fragments.
- The collector does not claim complete mailbox history.

## Fixture Validation

The new fixture creates a simulated local mail root with:

- Apple Mail `.emlx` message.
- Maildir `new/` RFC822 message.
- Unsupported local noise file.
- A path containing a private-looking email address and long numeric account
  fragment.

Expected result:

- 2 email events are emitted.
- Events use source `授权本机邮箱扫描`.
- `raw_ref.local_scan=true`, `raw_ref.source_platform=mac`, and format values
  are `emlx` and `maildir`.
- Manifest reports `source_type=authorized_email_export_or_local_scan`,
  `local_scan_requested=true`, candidate count 2, imported count 2, Apple
  Mail/Maildir counts, and proof level
  `authorized_local_email_scan_boundary`.
- Probe, manifest, and event raw refs do not leak the private path email or long
  numeric account fragment.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/email-collector/scripts/email_api.py \
  skills/email-collector/scripts/email_collector/events.py \
  skills/email-collector/tests/test_events.py
.venv/bin/python skills/email-collector/tests/test_events.py
python3 -m json.tool collectors/finclaw-investor-catalog.json
python3 -m json.tool collectors/finclaw-invocation-contracts.json
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```
