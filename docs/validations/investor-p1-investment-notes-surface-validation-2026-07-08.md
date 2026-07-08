# P1 Investment Notes Surface Validation - 2026-07-08

This validation records the `investment-notes` lens surface pass. No real note
service tokens, cookies, account credentials, or private note exports are
committed.

## Scope

- Skill: `investor-source-collectors` `0.1.5`
- Generic upstream: `notes` from `notes-collector`
- Lens target: `investment-notes`
- FinClaw target: investment reviews, rules libraries, trade checklists,
  valuation assumptions, and research notes.

## Lens Additions

`data.classification` for `investment-notes` events now includes:

- `investment_note_types`
- `primary_investment_note_type`
- `investment_note_type_terms`

Supported note types:

- `review_note`
- `rules_library`
- `trade_checklist`
- `valuation_assumption`
- `research_note`

`manifest.lens_surface_summary` and
`investor_wiki_evidence.v1.json.coverage_summary.source_surface_summary` now
record:

- note-type counts;
- primary note-type counts;
- missing expected note types;
- source-app counts;
- upstream collector counts;
- matched-symbol event count;
- preview-only vs full-content counts;
- tagged/path/URL event counts;
- explicit generic-notes lens boundary.

## Boundary

`notes-collector` remains generic and does not decide what belongs in the
investor Wiki. `investment-notes` performs lens filtering over user-authorized
note events and still does not write the final Wiki directly.

This pass does not claim:

- real Notion account/API validation;
- real Youdao account/export validation;
- real Evernote/Yinxiang account/export validation;
- real Windows/Linux vault validation;
- broad false-positive review on a real mixed note corpus.

## Fixture Proof

Validated by:

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

New fixture coverage:

- reads upstream `collectorx.event.v1` events produced by `notes`;
- keeps investment notes and filters a life note;
- classifies review, rules-library, trade-checklist, valuation-assumption, and
  research-note surfaces;
- propagates the surface summary into both manifest and
  `finclaw.investor_wiki_evidence.v1`.

## Remaining Work

- Backtest against a real mixed personal note corpus with user-approved
  allowlists.
- Validate real Notion, Youdao, and Evernote/Yinxiang exports or APIs.
- Validate Windows/Linux Obsidian vault paths on real devices.
- Keep full note bodies behind explicit authorization.
