# P0 Filesystem Gap Package Validation - 2026-07-09

This validation covers the P0 generic `filesystem` collector after hardening
empty metadata package behavior. FinClaw can now ingest a traceable CollectorX
package when an authorized filesystem scan retains no file metadata.

## Scope

- Skill: `filesystem-collector`
- Version: `0.3.2`
- Collector: `filesystem`
- Downstream lens: `research-documents`
- Boundary: metadata-only, user-authorized roots only, no file body, no
  whole-disk claim, and no investment relevance claim.

## Added Behavior

- `filesystem_query.py collect --out-dir` writes one profile gap event when a
  scan produces no retained file metadata.
- Fully filtered scope-policy runs emit
  `data.gap=filesystem_scope_policy_filtered_all`.
- Missing, empty, unsupported, hidden-only, or otherwise no-metadata runs emit
  `data.gap=filesystem_no_metadata_events_collected`.
- Gap events expose counts and reason summaries but do not write raw local
  paths, file contents, credentials, or investment conclusions.
- Manifest `event_count` counts the gap event, while
  `file_surface_summary.metadata_event_count=0` keeps file metadata coverage
  honest.
- Manifest `collection_readiness.can_enter_finclaw=false` prevents gap-only
  packages from being treated as usable upstream input for `research-documents`.

## Fixture Coverage

- Filtered-all fixture verifies:
  - one profile event in `lake/filesystem/events.jsonl`
  - `data.gap=filesystem_scope_policy_filtered_all`
  - candidate count `1`, retained count `0`, filtered count `1`
  - no raw local path in the gap event
  - `manifest.collection_readiness.status=scope_policy_filtered_all`
  - `manifest.file_surface_summary.metadata_event_count=0`
  - package validation passes with
    `tools/validate_collector_package.py --collector filesystem`
- Missing-root fixture verifies:
  - one profile event with `data.gap=filesystem_no_metadata_events_collected`
  - missing-root and scanned-file counts
  - no raw missing path in the gap event
  - package validation passes with
    `tools/validate_collector_package.py --collector filesystem`

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
rm -rf /tmp/filesystem_scope_filtered_all_cli
mkdir -p /tmp/filesystem_gap_fixture
printf 'not read\n' > /tmp/filesystem_gap_fixture/research.md
.venv/bin/python skills/filesystem-collector/scripts/filesystem_query.py collect \
  --root /tmp/filesystem_gap_fixture \
  --out-dir /tmp/filesystem_scope_filtered_all_cli \
  --allow-file-name 估值
.venv/bin/python tools/validate_collector_package.py \
  /tmp/filesystem_scope_filtered_all_cli \
  --collector filesystem
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
PYTHON=.venv/bin/python bash test_collectors.sh
.venv/bin/python tools/validate_project.py
git diff --check
```

## Results

- Syntax validation passed for the filesystem CLI, scanner module, and tests.
- Filesystem fixture tests passed for normal metadata collection,
  filtered-all gap packages, and missing-root gap packages.
- Manual filtered-all CLI package produced exactly one profile gap event with
  `data.gap=filesystem_scope_policy_filtered_all`,
  `metadata_event_count=0`, and `can_enter_finclaw=false`.
- Manual filtered-all CLI package passed
  `tools/validate_collector_package.py --collector filesystem`.
- CLI help validation passed.
- JSON validation passed for the FinClaw investor catalog, invocation
  contracts, and filesystem metadata file.
- FinClaw catalog and batch-runner tests passed.
- Full collector regression suite passed.
- Project-level validation passed.
- `git diff --check` passed.

## Remaining Real Validation

- Run on real user-selected research folders across macOS, Windows, and Linux.
- Tune default scope-policy presets for research folders, downloads, cloud
  drives, screenshots, and valuation workbooks.
- Backtest upstream filesystem metadata into `research-documents` against real
  trade/review timelines.
