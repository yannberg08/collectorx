# P0 Research Image OCR Validation - 2026-07-08

## Scope

This pass adds an explicit screenshot/image OCR path to the P0
`research-documents` lens.

It does not change the generic `filesystem` collector. `filesystem` remains
metadata-only. It also does not make OCR the default behavior for screenshots.

## Invocation

```bash
python3 skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source research-documents \
  --input <authorized-research-folder-or-image> \
  --include-image-ocr \
  --out-dir <out-dir>
```

`--include-image-ocr` is intentionally separate from `--include-content`.
Reading XLS/XLSX/PPTX/DOCX/PDF bodies and reading screenshot text are two different
user authorization decisions.

## Behavior

- Uses a local `tesseract` adapter from `PATH` or `COLLECTORX_TESSERACT_CMD`.
- Writes OCR text only when the user passes `--include-image-ocr` and the local
  engine succeeds.
- Caps extracted OCR text with the same content limit used for other research
  document extraction.
- Records `raw_ref.image_ocr_requested`, `raw_ref.image_ocr_performed`,
  `raw_ref.content_read`, parser, status, and truncation metadata.
- Records `manifest.collection_audit.image_ocr_event_count`,
  `image_ocr_status_counts`, `ocr_performed`, and per-file OCR policy in
  `path_results`.
- If OCR is unavailable or fails, keeps metadata-only behavior and records the
  OCR status instead of pretending the screenshot was read.

## Validation Coverage

Validated by:

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

The fixture coverage includes:

- default screenshot/image handling remains metadata-only;
- OCR is not requested without `--include-image-ocr`;
- an explicit fake local `tesseract` adapter extracts investment-relevant text;
- OCR events carry `content_extract.status=extracted`;
- manifest audit records engine path, status counts, parser counts, and
  per-file OCR policy.

## Remaining Gaps

- Real private screenshot samples have not been validated in this pass.
- Chinese OCR quality needs review with actual broker screenshots, report pages,
  valuation tables, and annotated images.
- Windows/Linux engine path discovery needs real-device validation.
- The resulting evidence still needs backtesting against real trades, reviews,
  and notes before promotion beyond `baseline+audit`.
