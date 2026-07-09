# P1 Notes to Investment Notes Fixture E2E Validation

Date: 2026-07-09

Scope:

- Collector: `notes`
- Lens: `investment-notes`
- Fixture: `examples/fixtures/notes-investment-e2e/`
- Goal: prove that generic notes first enter the notes Lake as preview-only
  personal notes, and only the `investment-notes` lens promotes investment
  notes into Investor Wiki evidence.

## Fixture

The fixed fixture contains four Obsidian-style Markdown notes:

- `reviews/600519-trade-review.md`: trade review with symbol, buy reason,
  position sizing, risk, and mistake review.
- `rules/trade-checklist.md`: rules library and trade checklist.
- `valuation/semiconductor-valuation-assumptions.md`: valuation assumptions,
  DCF/PE/PB/ROE variables, margin of safety, and research follow-up.
- `life/weekend-plan.md`: non-investment life-note decoy.

## Commands

```bash
.venv/bin/python skills/notes-collector/tests/test_notes_collector.py
```

Manual package path:

```bash
.venv/bin/python skills/notes-collector/scripts/notes_api.py obsidian \
  --vault examples/fixtures/notes-investment-e2e/obsidian-vault \
  --export /tmp/collectorx-notes-e2e-h8fAl8/notes.json \
  --out-dir /tmp/collectorx-notes-e2e-h8fAl8/notes-out

.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-notes-e2e-h8fAl8/notes-out \
  --collector notes \
  --json

.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source investment-notes \
  --input /tmp/collectorx-notes-e2e-h8fAl8/notes-out/lake/notes/events.jsonl \
  --out-dir /tmp/collectorx-notes-e2e-h8fAl8/lens-out \
  --collected-at 2026-07-09T14:10:00+08:00

.venv/bin/python tools/validate_collector_package.py \
  /tmp/collectorx-notes-e2e-h8fAl8/lens-out \
  --collector investment-notes \
  --require-evidence \
  --json
```

## Results

- `notes-collector` emitted 4 generic note events.
- Notes manifest:
  - `note_event_count=4`
  - `gap_event_count=0`
  - `content_policy.full_content_event_count=0`
  - `content_policy.preview_only_event_count=4`
  - `evidence_policy.required_lens=investment-notes`
  - `collection_readiness.can_claim_investment_notes=false`
- Notes package validation: `valid=true`, `usable_event_count=4`.
- `investment-notes` emitted 3 retained investment-note events.
- The life-note decoy was excluded before Investor Wiki evidence.
- Lens manifest:
  - `candidate_record_count=4`
  - `matched_event_count=3`
  - `filtered_candidate_count=1`
  - `investment_note_boundary_proof.proof_level=authorized_investment_notes_preview_only`
  - `complete_notes_vault_claimed=false`
  - `direct_notes_reconnect=false`
  - `requires_upstream_notes_collector=true`
- Lens package validation with `--require-evidence`: `valid=true`,
  `usable_event_count=3`.

## Boundary

This is an offline fixture gate. It does not claim real Notion, Youdao,
Evernote, Windows, Linux, or broad private-vault validation. It proves the
CollectorX package contract and the generic-to-lens Wiki boundary for a stable
fixture so future changes cannot accidentally promote non-investment notes into
FinClaw Investor Wiki facts.
