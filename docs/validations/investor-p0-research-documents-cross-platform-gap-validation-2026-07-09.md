# P0 Research Documents Cross-Platform Gap Validation - 2026-07-09

## Scope

This pass hardens the `research-documents` lens for offline G2 readiness. It
does not claim real Windows or Linux device validation.

## Changes

- Added upstream filesystem-event path-style summaries for:
  - Windows drive paths
  - Windows UNC paths
  - macOS user-home paths
  - Linux user-home paths
  - POSIX absolute paths
  - ZIP members
  - relative paths
  - unknown paths
- Added source-platform summaries to `lens_surface_summary`,
  `research_corpus_boundary_proof.platform_path_boundary`, and Investor Wiki
  `coverage_summary.source_boundary_proof_summary.research-documents`.
- Added explicit false-claim gates:
  `complete_cross_platform_validation_claimed=false`,
  `real_windows_device_validation_claimed=false`, and
  `real_linux_device_validation_claimed=false`.
- Empty authorized directories now produce `no_readable_input` gap packages.
- Invalid JSON inputs now record `path_results[].status=unreadable`,
  `reason=invalid_json`, `skipped_reason_counts.invalid_json=1`, and a
  validator-safe `no_readable_input` data-quality gap package.
- `investor-source-collectors` now writes primary event counters for source
  profiles that map to known package-validator collector counters.
- The shared package validator now requires known collector primary counters at
  the manifest level.

## Validation

Commands:

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/test_collector_package_validator.py
```

Both commands passed.

## Boundary

- This validates route and package semantics for Windows/Linux/macOS-looking
  upstream filesystem paths.
- It does not validate real Windows or Linux devices.
- It does not validate broad private research corpora, real binary `.xls`
  parsing with `xlrd`, or Chinese screenshot OCR quality.
