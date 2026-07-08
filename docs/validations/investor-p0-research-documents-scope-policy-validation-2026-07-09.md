# P0 Research Documents Scope Policy Validation - 2026-07-09

## Scope

This validation covers `investor-source-collectors` `0.1.22`, specifically the
`research-documents` lens for user-authorized local research documents,
financial statements, valuation models, notes, spreadsheets, PDFs, slide decks,
and screenshots.

The goal is to narrow authorized research-document records before Lake and Wiki
evidence output while preserving the existing SoulMirror boundary: generic
`filesystem` remains metadata-only, and content/OCR reads still require explicit
user authorization.

## What Changed

- `investor_sources.py collect --source research-documents` now accepts:
  - `--allow-extension` / `--deny-extension`
  - `--allow-path` / `--deny-path`
  - `--allow-file-name` / `--deny-file-name`
  - `--allow-parser` / `--deny-parser`
  - `--allow-research-surface` / `--deny-research-surface`
  - `--allow-keyword` / `--deny-keyword`
- Manifest `collection_audit.document_scope_policy` records configured
  filters, candidate record count, filtered record count, filter reason counts,
  and filtered-all state.
- `research_corpus_boundary_proof.authorization_scope_boundary` gives FinClaw a
  stable place to inspect the user's document authorization policy.
- If all candidate research-document records are excluded by policy, readiness
  reports `source_policy_filtered_all` and the evidence package remains empty.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
```

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect --help
```

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Results

- Syntax validation passed.
- `investor-source-collectors` fixture validation passed.
- CLI help shows the new research-document scope-policy arguments.
- New tests cover partial retention by extension, path, file name, parser,
  research surface, and keyword, plus filtered-all readiness with no Wiki
  evidence.
- Existing research-document coverage still validates DOCX/PDF/XLSX/XLSM/XLS/
  PPTX extraction, legacy/binary XLS parser boundaries, screenshot metadata-only
  behavior, explicit image OCR authorization, path-level audit, limit
  truncation, and package validation.
- FinClaw catalog and batch runner tests passed.
- Project validation passed.
- Full collector regression suite passed.

## Product Boundary

- The lens only emits user-authorized research-document evidence.
- Scope policy narrows authorized records; it does not claim a complete research
  corpus, complete filesystem scan, or investment conclusion.
- Generic `filesystem` remains metadata-only.
- Content extraction still requires `--include-content`.
- Screenshot/image OCR still requires `--include-image-ocr` and a local
  tesseract adapter.
- This pass does not claim real Windows/Linux device validation, broader private
  PDF/XLS/XLSX/DOCX/PPTX/image sample validation, Chinese OCR quality review,
  real binary `.xls` with xlrd validation, or Wiki backtest against real trades.
