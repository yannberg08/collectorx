# P0 Email Source Audit Validation - 2026-07-08

This validation records the local-import source-audit hardening pass for the
generic `email` collector and the `email-research` lens boundary.

## Scope

Collector path:

- Generic source: `email`
- Lens target: `email-research`
- FinClaw target: broker research, IR, roadshow, and research-attachment
  evidence after lens filtering

This pass strengthens user-authorized local email imports. It covers EML, MBOX,
JSON/JSONL/NDJSON, CSV/TSV, and ZIP packages. It does not register or validate a
real mailbox account, and it does not change IMAP credentials handling.

## Product Changes

- Upgraded `email-collector` to `0.5.1`.
- Aligned `.collectorx.json` with `baseline+audit`.
- Added `source_type=authorized_email_export` to local import audits.
- Added `manifest.collection_audit` fields for requested inputs, missing
  inputs, resolved files, extension counts, skipped file counts, skipped file
  reasons, parsed/imported counts, path-level parse results, and `--limit`
  truncation.
- Added ZIP member audit for member count, member extension counts, imported
  member email count, skipped member count, skipped member reasons, and unvisited
  members due to `--limit`.
- Hardened ZIP member safety for POSIX traversal and Windows drive-letter
  members.
- Preserved the existing IMAP `collect --out-dir` account/folder audit path.

## Fixture Validation

Validated scenarios:

- Mixed local EML, JSON, and CSV import emits three email events.
- Unsupported local files are counted by extension and reason.
- Missing input paths emit an explicit local-import gap and `input_missing`
  audit.
- ZIP imports preserve `archive.zip::member` provenance.
- ZIP members using POSIX traversal and Windows drive paths are skipped as
  `unsafe_path`.
- Unsupported ZIP members are skipped as `unsupported_extension`.
- ZIP `--limit` accounting counts only imported records.
- Attachment refs and raw refs are sanitized so token-like values do not leak.
- Full bodies remain excluded by default.
- Attachment bodies are not written.

Commands:

```bash
.venv/bin/python -m py_compile skills/email-collector/scripts/email_api.py skills/email-collector/scripts/email_collector/events.py skills/email-collector/tests/test_events.py
.venv/bin/python skills/email-collector/tests/test_events.py
```

Result:

- Passed.

## Current Gate

- Local authorized import package path: G1/G2 baseline+audit.
- IMAP package path: G1/G2 baseline+audit, but real mailbox validation is still
  blocked by missing registered mailbox credentials on this machine.
- Generic-to-lens boundary: implemented. The generic email collector does not
  write investor Wiki conclusions directly.

## Not Claimed

- No real mailbox account validation.
- No OAuth flow validation.
- No broker/IR sender backtest on real mailboxes.
- No attachment body extraction.
- No full-body event output unless the user explicitly passes
  `--event-include-body`.
- No Windows/macOS/Linux real mailbox path validation beyond fixtures.

## Remaining Before Production Candidate

- Register a real mailbox using `password_env`.
- Run IMAP `collect --out-dir` on real mailbox folders.
- Run local import on real exported mailbox archives.
- Backtest `email-research` against known broker research, IR, roadshow, and
  trade-adjacent emails.
- Review no-full-body leakage on real mailboxes.
