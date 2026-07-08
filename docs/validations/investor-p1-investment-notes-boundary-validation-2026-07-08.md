# P1 Investment Notes Boundary Validation - 2026-07-08

This validation records the P1 pass that adds investment-note boundary proof to
the `investment-notes` lens.

## Scope

- Skill: `investor-source-collectors`
- Version: `0.1.12`
- Lens: `investment-notes`
- Upstream role: already-collected `notes` lake events only.
- FinClaw target: reviews, rules library, trade checklist, valuation
  assumptions, research notes, and decision-framework evidence.

## Productization change

- `manifest.investment_note_boundary_proof` now records:
  - candidate, matched, and filtered counts;
  - authorized input counts and requested input paths;
  - source-app coverage;
  - preview-only versus full-content evidence counts;
  - tag/path/URL coverage;
  - investment-note type surface counts;
  - no claim of complete notes-vault coverage, complete note context, or direct
    notes reconnect.
- `investor_wiki_evidence.v1.json.coverage_summary.source_surface_summary`
  already carries the investment-note surface summary and now has manifest-level
  boundary proof to match it.

## Validation commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
```

## Verified behavior

- Obsidian, Notion, and Youdao note fixtures are retained as investment notes.
- A non-investment Evernote/life note candidate is filtered out.
- The proof emits `authorized_investment_notes_preview_only` for preview-only
  upstream notes.
- The proof records candidate count, matched count, filtered count, source-app
  coverage, tag/path counts, preview-only count, and note-type counts.
- The proof keeps `complete_notes_vault_claimed` and
  `complete_note_context_claimed` false.

## Remaining production gaps

- Real Notion, Youdao, and Evernote account exports/APIs still need validation.
- User allowlists and folder/tag policies need backtesting on real note vaults.
- Windows/Linux vault paths and sync-directory behavior need real-device checks.
- False-positive review is still required before readiness can move beyond
  `baseline+audit`.
