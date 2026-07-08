# P0 Research Corpus Boundary Validation - 2026-07-08

This validation records the P0 pass that adds research-corpus boundary proof and
research-document surface summaries to the `research-documents` investor lens.

## Scope

- Skill: `investor-source-collectors`
- Version: `0.1.10`
- Lens: `research-documents`
- Upstream role: authorized `filesystem` or `notes` evidence only.
- FinClaw target: research reports, financial statements, valuation models,
  announcement notes, reviews, screenshots, and table models for investor Wiki
  distillation.

## Productization change

- `manifest.research_corpus_boundary_proof` now records:
  - authorized input count and requested inputs;
  - resolved files, missing inputs, skipped files, skipped reasons, and limit
    truncation;
  - extension coverage and parser coverage;
  - explicit content-read count, metadata-only count, screenshot metadata-only
    count, OCR event count, OCR status, and extraction status;
  - no claim of complete research-corpus coverage, whole-disk scan, or public
    report database crawling.
- `manifest.lens_surface_summary` now reports research-document surfaces:
  research report, financial statement, valuation model, announcement note,
  review note, screenshot/image, and table model.
- `investor_wiki_evidence.v1.json.coverage_summary.source_surface_summary`
  now carries the same `research-documents` surface summary so FinClaw/SoulMirror
  can inspect corpus quality before distilling Wiki pages.

## Validation commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
```

## Verified behavior

- DOCX/PDF/XLSX content extraction with `--include-content` emits
  `authorized_research_corpus_with_content` proof and counts parser coverage.
- Binary research files without `--include-content` remain metadata-only and
  emit `authorized_research_corpus_metadata_only` proof.
- Broad weak titles and unsupported files can produce
  `no_usable_research_evidence_after_filter`; these packages cannot enter
  FinClaw as user facts.
- Explicit image OCR with a configured local `tesseract` adapter emits
  `authorized_research_corpus_with_image_ocr` proof and screenshot/image surface
  counts.
- Evidence packages include the research-document surface summary under
  `coverage_summary.source_surface_summary.research-documents`.

## Remaining production gaps

- More real Chinese PDF/XLSX/DOCX/image samples are required.
- OCR quality must be reviewed against real broker screenshots and report pages.
- Windows/Linux real device paths still need validation beyond fixtures.
- Wiki claims still require backtesting against real trades, notes, meetings,
  and reviews before readiness can move beyond `baseline+audit`.
