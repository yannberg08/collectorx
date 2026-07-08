# P0 Research Scope Audit Validation - 2026-07-08

This validation records the productization pass for the `research-documents`
lens. No private file paths, raw document text, or extracted user content are
committed.

## Scope

- Collector/lens: `research-documents`
- Skill: `skills/investor-source-collectors` `0.1.1`
- Upstream boundary: generic `filesystem` remains metadata-only.
- FinClaw target: `collectorx.event.v1` lake plus
  `finclaw.investor_wiki_evidence.v1`, not direct Wiki writes.

## Changes Validated

- `manifest.collection_audit` now records:
  - input and resolved file counts
  - candidate record counts
  - matched, non-matched, and filtered counts
  - extension counts and skipped extension counts
  - parser counts
  - content-read event counts
  - content extraction status counts
- `manifest.collection_audit.content_extraction_policy` now states:
  - content extraction applies to the `research-documents` lens
  - user-selected files/folders are the only input boundary
  - `filesystem` is metadata-only
  - DOCX/PDF/XLSX/XLSM/XLS/PPTX body, table, or slide extraction requires explicit
    `--include-content`
  - screenshots are metadata-only in this pass; OCR is not claimed
  - unsupported extensions are skipped
  - the collector does not write final Wiki pages directly
- `collectors/lenses/research-documents.yaml` exposes the same content policy to
  registry-level orchestration.
- File-title scoring was tightened so broad one-word hints such as a lone
  "股票" or "基金" do not become Wiki evidence without stronger research
  context.

## Fixture Proof

Validated by `skills/investor-source-collectors/tests/test_investor_sources.py`:

- Authorized `--include-content` extraction:
  - XLSX via `openpyxl`
  - legacy XML Spreadsheet `.xls`
  - PPTX via OOXML slide XML
  - DOCX via `python-docx`
  - PDF via `pdfplumber`
  - manifest reports content-read events and extracted statuses
- No `--include-content`:
  - DOCX with a research title is kept as metadata-only
  - no `content` or `content_extract` payload is emitted
  - manifest reports zero content-read events
- False-positive and unsupported-file guard:
  - a metadata-only file with a broad title hint is filtered
  - an unsupported `.py` file is skipped even if its name contains a research
    word
  - final evidence package has no usable Wiki coverage for that negative fixture

## Current Gate

- `research-documents`: `baseline+audit`
- macOS local extraction: previously validated with real local candidates
- Windows/Linux filesystem default-root code paths: fixture-tested via
  `filesystem-collector`
- Real Windows/Linux device validation: not yet done
- Screenshot OCR: intentionally not claimed
- G4 Wiki backtest against real trades and review records: still required

## Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/classifier.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py

.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Both commands passed in this validation pass.
