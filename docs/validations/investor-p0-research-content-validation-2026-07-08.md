# P0 Research Content Validation - 2026-07-08

This validation records an explicit-authorization content extraction pass for
local research documents. Raw user files, paths, and extracted text are not
committed.

## Research Documents Lens

Collector path:

- Generic metadata source: `filesystem`
- Investor lens/content reader: `research-documents` via
  `skills/investor-source-collectors`

Result:

- Added optional content extraction behind `--include-content`.
- Default behavior remains conservative: metadata-only for binary documents.
- Explicit content extraction supports:
  - Markdown/TXT/HTML text files
  - CSV/TSV tables
  - XLSX/XLSM via `openpyxl`
  - XML/HTML/text-style `.xls` exports and optional binary `.xls` fallback
  - PPTX slide text via OOXML slide XML
  - DOCX via `python-docx`
  - PDF via `pdfplumber`
- Extracted text is capped and recorded with parser/status metadata.
- Collector still writes only lake events and investor evidence packages; it
  does not directly write final Wiki pages.

Fixture validation:

- XLSX valuation table, legacy XML Spreadsheet `.xls`, PPTX roadshow deck,
  DOCX roadshow note, and PDF factor report fixtures are converted into
  `collectorx.event.v1` file events when `--include-content` is supplied.
- Each fixture event records `raw_ref.content_read: true`.
- Each fixture event records `payload.content_extract.status: extracted`.

Real local candidate validation:

- Candidate files found: 30.
- `research-documents --include-content` emitted 28 research evidence events.
- Event kind counts: 28 file events.
- Classification average confidence: `0.807`.
- Matched event count: 28.
- Content extraction confirmed for 6 PDF events via `pdfplumber`.
- Wiki coverage: 10 usable investor subdimensions.

Current gate:

- Metadata-only filesystem collection: G2/G3 partial on macOS.
- Explicit research-document content extraction: G2/G3 partial on macOS.
- Windows/Linux path validation: not done.
- Curated false-positive review: not done.

Remaining before production:

- Add Windows/Linux path and encoding validation.
- Add more real XLS/XLSX/PPTX/DOCX/PDF samples under private validation.
- Add user-facing controls for content extraction scope, file size, and folder
  allowlists.
- Backtest extracted research evidence against real decisions/trades.
- Keep generic `filesystem` metadata-only; content reading must stay an
  explicit research lens action.
