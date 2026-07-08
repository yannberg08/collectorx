# P0 China Wealth PDF Statement Validation - 2026-07-09

This validation records a productization pass for the P0
`china-wealth-assets` collector.

## Scope

- Skill: `china-wealth-assets`
- Version: `0.4.5`
- Source role: user-authorized fund, wealth-management, and cash-management
  asset evidence.
- New input channel: authorized PDF statements.
- PDF parser: local `pdfplumber`.

## Implemented

- Added `.pdf` to supported direct inputs and ZIP package members.
- Added `parse_pdf()` using `pdfplumber` table/text extraction.
- PDF table extraction can produce structured asset events when statements
  expose columns such as:
  - platform
  - account
  - product code/name
  - market value
  - total asset
  - transaction amount
  - date
- PDF text fallback tries text-table and key-value extraction before retaining
  a statement snapshot.
- Manifest `collection_audit` now records:
  - `pdf_import_supported`
  - `pdf_parser`
  - `pdf_parser_available`
  - `pdf_text_ocr_used`
  - `pdf_file_count`
  - `pdf_page_count`
  - `pdf_table_count`
  - `pdf_table_record_count`
  - `pdf_text_record_count`
  - `pdf_parse_error_count`

## Fixture Validation

The fixture generates a real PDF statement with a table containing:

- A bank-wealth holding for account `cmb-001` with
  `market_value=20000.5`.
- An Alipay asset snapshot for account `ali-main` with
  `total_asset=12345.67`.

Expected result:

- 2 events are emitted.
- Event platforms are `bank-wealth` and `alipay`.
- Event subtypes are `wealth_holding` and `asset_snapshot`.
- Raw references include `parser=pdfplumber`, `pdf_page=1`, and
  `pdf_table=1`.
- Manifest PDF audit reports one PDF file, one page, one table, two table
  records, no OCR, and no parse error.
- Asset value summary preserves the exact numeric values.
- Asset-boundary proof remains partial and does not claim complete account
  coverage.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/china-wealth-assets/scripts/china_wealth.py \
  skills/china-wealth-assets/scripts/china_wealth/parser.py \
  skills/china-wealth-assets/tests/test_china_wealth.py

.venv/bin/python skills/china-wealth-assets/tests/test_china_wealth.py

python3 -m json.tool collectors/finclaw-investor-catalog.json
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_collector_package.py \
  --collector china-wealth-assets \
  --require-evidence <generated-pdf-statement-package>
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Explicit Non-Claims

- This pass does not validate a real Alipay, Tiantian Fund, Danjuan, Qieman, or
  bank account.
- This pass does not claim complete asset-boundary coverage from a single PDF.
- This pass does not perform OCR.
- This pass does not collect payment passwords, bank passwords, cookies,
  authorization headers, or request query strings.
- This pass does not place orders, redeem funds, transfer money, or mutate any
  account state.
