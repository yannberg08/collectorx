# P0 Filesystem Scope Policy Validation - 2026-07-09

This validation covers the P0 generic `filesystem` collector after adding
explicit user authorization scope filters before local file metadata enters the
Lake. The collector remains metadata-only and does not read file bodies.

## Scope

- Skill: `filesystem-collector`
- Version: `0.3.1`; gap package ingestion was later hardened in version
  `0.3.2` with
  `docs/validations/investor-p0-filesystem-gap-package-validation-2026-07-09.md`.
- Collector: `filesystem`
- Downstream lens: `research-documents`
- FinClaw route: authorized local file metadata for research-material discovery.

## Added Behavior

- `filesystem_query.py collect` accepts allow/deny filters for extension, path,
  file name, directory, and metadata keyword.
- Legacy `--extension` remains supported as a backward-compatible
  `--allow-extension` alias.
- Manifest `source_audit.filesystem_scope_policy` records configured filters,
  candidate file count, retained event count, filtered file count, filter reason
  counts, and filtered-all state.
- Manifest `filesystem_boundary_proof.authorization_scope_boundary` exposes the
  same policy boundary to FinClaw gating.
- When every candidate file is filtered, readiness reports
  `scope_policy_filtered_all`. As of version `0.3.2`, this state also emits a
  `filesystem_scope_policy_filtered_all` profile gap event.
- The policy is an authorization boundary only. It does not classify investment
  relevance and does not read file content.

## Fixture Coverage

- Partial-retention fixture keeps one authorized research workbook while
  filtering one file by extension, one by path, and one by deny-keyword.
- Filtered-all fixture verifies a readable metadata candidate with a
  non-matching file-name allowlist reports `scope_policy_filtered_all`.
- Existing coverage still validates metadata-only behavior, hidden-file skips,
  ignored-directory skips, unsupported-extension skips, source audit, and
  macOS/Windows/Linux default-root planning.

## Verification Commands

```bash
.venv/bin/python -m py_compile \
  skills/filesystem-collector/scripts/filesystem_query.py \
  skills/filesystem-collector/scripts/filesystem_collector/scanner.py \
  skills/filesystem-collector/tests/test_filesystem_collector.py
```

```bash
.venv/bin/python skills/filesystem-collector/tests/test_filesystem_collector.py
.venv/bin/python skills/filesystem-collector/scripts/filesystem_query.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- Filesystem fixture validation passed.
- CLI help shows the new filesystem scope-policy arguments.
- FinClaw catalog tests passed.
- FinClaw batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Expected Manifest Signals

- `source_audit.filesystem_scope_policy`
- `source_audit.filesystem_scope_policy_filtered_all`
- `collection_readiness.status=scope_policy_filtered_all` when all candidates
  are excluded.
- `filesystem_boundary_proof.authorization_scope_boundary`
- `filesystem_boundary_proof.file_content_collected=false`
- `filesystem_boundary_proof.whole_disk_scan_claimed=false`

## Remaining Real Validation

- Run on real user-selected research folders across macOS, Windows, and Linux.
- Tune default scope-policy presets for research folders, downloads, cloud
  drives, screenshots, and valuation workbooks.
- Backtest upstream filesystem metadata into `research-documents` against real
  trade/review timelines.
