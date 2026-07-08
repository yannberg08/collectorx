# P0 Research Binary XLS Boundary Validation - 2026-07-09

This validation records a productization pass for the P0
`research-documents` lens.

## Scope

- Skill: `investor-source-collectors`
- Version: `0.1.21`
- Lens: `research-documents`
- Source role: user-authorized research material evidence.
- Default body-read policy: false. Content extraction still requires
  `--include-content`.

## Implemented

- Split `.xls` parser labels into explicit variants:
  - `legacy-xls-xml`
  - `legacy-xls-html`
  - `legacy-xls-delimited`
  - `legacy-xls-text`
  - `openpyxl-renamed-xls`
  - `xlrd-biff`
- Added binary `.xls` policy fields to
  `manifest.collection_audit.content_extraction_policy`:
  - `legacy_xls_parser_variants`
  - `binary_xls_biff_requires_xlrd`
  - `binary_xls_biff_parser_available`
  - `binary_xls_without_xlrd_records_extract_failed`
- Added deterministic degradation validation with `COLLECTORX_DISABLE_XLRD=1`.
- When binary BIFF `.xls` is authorized but `xlrd` is unavailable, the emitted
  event records:
  - `raw_ref.parser: xlrd-biff`
  - `raw_ref.content_read: false`
  - `payload.content_extract.status: extract_failed`
  - `payload.content_extract.error: xlrd_unavailable_for_binary_xls`

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

## Explicit Non-Claims

- This pass does not validate a real private binary `.xls` file with `xlrd`
  installed.
- This pass does not read research bodies without `--include-content`.
- This pass does not change the generic `filesystem` collector; it remains
  metadata-only.
- This pass does not claim complete research-corpus coverage.
- This pass does not perform Wiki backtesting against real trades or reviews.
