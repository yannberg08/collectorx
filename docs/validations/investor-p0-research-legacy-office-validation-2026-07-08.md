# P0 Research Legacy Office Validation - 2026-07-08

## Purpose

Validate that the P0 `research-documents` lens can extract user-authorized
legacy spreadsheet and presentation research material without weakening the
metadata-only default boundary.

## Scope

- `skills/investor-source-collectors/scripts/investor_sources/parser.py`
- `skills/investor-source-collectors/scripts/investor_sources/profiles.py`
- `skills/investor-source-collectors/tests/test_investor_sources.py`
- `collectors/lenses/research-documents.yaml`
- `skills/investor-source-collectors/SKILL.md`
- `docs/finclaw-integration-guide.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- Generic `filesystem` remains metadata-only.
- `research-documents` reads document bodies only when `--include-content` is
  explicitly supplied.
- `.xls` is treated as explicit content extraction when it is XML Spreadsheet,
  HTML table, text/CSV-style export, renamed OOXML, or binary BIFF with optional
  `xlrd` available.
- Binary `.xls` without a usable parser records an extraction failure instead
  of fabricating content.
- `.pptx` slide text is extracted from OOXML slide XML.
- Extracted `.xls` and `.pptx` events carry `raw_ref.content_read`,
  `payload.content_extract`, parser names, capped text, and research-surface
  classification.
- Events without source timestamps fall back to the explicit `collected_at`
  timestamp so package validation never receives empty event times.
- Investor source evidence children include `evidence_kinds`, satisfying the
  canonical Investor Wiki evidence contract.
- Manifest audit and research corpus boundary proof include parser counts,
  content-read counts, format coverage, and non-complete-corpus claims.

## Verification Commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-research-legacy-office \
  --collector research-documents \
  --require-evidence \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- Investor source collector tests passed.
- XML Spreadsheet `.xls` fixture produced a content-read file event.
- Plain-text `.xls` export fixture produced a content-read file event.
- Minimal PPTX fixture produced a content-read file event.
- Manifest audit reported three content-read events, extracted statuses, parser
  counts for `legacy-xls-xml`, `legacy-xls-text`, and `pptx-xml`, and per-path
  parser results.
- Research corpus boundary proof stayed partial and did not claim complete
  research-corpus coverage.
- The generated package passed `tools/validate_collector_package.py` with
  `--collector research-documents --require-evidence`.
- Previously defined source-policy, attachment, meeting-surface, and WeChat
  article-surface tests are now called by the script entry point and therefore
  run under project validation.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This pass does not validate private binary `.xls` files, password-protected
Office files, embedded images/charts in PPT decks, Windows/Linux real devices,
or Wiki backtests against real trades and review records.
