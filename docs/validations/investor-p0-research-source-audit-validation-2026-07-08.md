# P0 Research Document Source Audit Validation - 2026-07-08

This validation records the path-level source-audit hardening pass for the
`research-documents` investor lens.

## Scope

Collector/lens path:

- Generic upstream: `filesystem-collector` and `notes-collector`
- Lens: `research-documents`
- FinClaw target: research reports, financial statements, valuation models,
  announcement annotations, screenshots/images as metadata-only evidence, and
  related investor Wiki evidence after lens filtering

This pass strengthens user-authorized local research inputs. It does not crawl
public report databases, scan the whole disk, read arbitrary file bodies, or
perform screenshot OCR.

## Product Changes

- Upgraded `investor-source-collectors` to `0.1.4`.
- Added requested-input and missing-input audit fields.
- Added per-file `path_results` with extension, status, parser, candidate
  count, emitted event count, and limit-truncation flags.
- Added `skipped_reason_counts` alongside skipped extension counts.
- Added `limit_reached` to distinguish complete small runs from capped package
  runs.
- Added screenshot/image metadata-only audit:
  - `screenshot_metadata_only_file_count`
  - `ocr_performed=false`
  - per-path `content_policy=screenshot_metadata_only_no_ocr`
- Kept content extraction policy unchanged:
  - Generic `filesystem` is metadata-only.
  - DOCX/PDF/XLSX/XLSM content extraction requires explicit
    `--include-content`.
  - OCR requires a future separate adapter and user authorization.

## Fixture Validation

Validated scenarios:

- DOCX, PDF, and XLSX content extraction with explicit `--include-content`.
- Binary DOCX metadata-only mode without `--include-content`.
- Missing input path audit.
- Unsupported extension skip audit.
- Broad title false-positive guard for weak names such as "股票计划".
- Screenshot/image metadata-only/no-OCR policy in manifest and path results.
- Limit truncation on a multi-record CSV.
- Investor Wiki evidence remains empty when no investment evidence survives the
  lens.

Commands:

```bash
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/parser.py skills/investor-source-collectors/scripts/investor_sources.py skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Result:

- Passed.

## Current Gate

- Research document lens path: G1/G2 baseline+audit.
- Explicit content extraction: fixture validated for DOCX/PDF/XLSX.
- Screenshot/image handling: metadata-only/no-OCR policy fixture validated.
- Real Windows/Linux device validation: not done in this pass.
- Real private research corpus backtest: not done in this pass.

## Not Claimed

- No public report database crawling.
- No whole-disk scan.
- No OCR.
- No arbitrary file-body reading without `--include-content`.
- No final Wiki writing directly from raw files.
- No production-candidate claim for broader private PDF/XLSX/DOCX samples.
- No trade/review backtest on real user data.

## Remaining Before Production Candidate

- Validate broader real PDF/XLSX/DOCX samples from the user's authorized corpus.
- Validate real Windows/Linux filesystem roots.
- Decide whether a separate OCR adapter is worth building for screenshots.
- Backtest `research-documents` evidence against real trades, reviews, notes,
  and meeting records before using it in investor Wiki conclusions.
