# P0 Research Documents Gap Package Validation - 2026-07-09

This validation covers `investor-source-collectors` version `0.1.26`, specifically
the P0 `research-documents` lens.

## Scope

- Collector/lens: `research-documents`
- Upstream boundary: authorized local research files, `filesystem`, or `notes`
- Gap target: `collectorx.data_quality.collection_gaps`

## What Changed

- Fully filtered document authorization-scope runs now emit one validator-safe
  profile gap event with `data.payload.gap=research_documents_scope_policy_filtered_all`.
- Readiness reports `collection_readiness.status=scope_policy_filtered_all`
  instead of treating the run as a successful empty capture.
- Manifest output separates:
  - `event_count`
  - `usable_event_count`
  - `research_document_event_count`
  - `gap_event_count`
- Readiness output separates:
  - `can_enter_investor_source_lake`
  - `can_enter_data_quality_lake`
  - `can_feed_investor_wiki_evidence`
- `investor_wiki_evidence.v1.json.generated_from.event_count` counts only
  non-gap research-document facts; gap-only packages keep it at `0` while
  recording `raw_event_count` and `gap_event_count`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/tests/test_investor_sources.py

.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py

rm -rf /tmp/research_docs_gap_cli /tmp/research_docs_gap_fixture
mkdir -p /tmp/research_docs_gap_fixture
printf '半导体 DCF 估值 买入理由 风险提示\n' > \
  /tmp/research_docs_gap_fixture/keep-valuation.md
.venv/bin/python skills/investor-source-collectors/scripts/investor_sources.py collect \
  --source research-documents \
  --input /tmp/research_docs_gap_fixture/keep-valuation.md \
  --out-dir /tmp/research_docs_gap_cli \
  --allow-keyword 新能源 \
  --collected-at '2026-07-09T10:10:00+08:00'
.venv/bin/python tools/validate_collector_package.py \
  /tmp/research_docs_gap_cli \
  --collector research-documents \
  --require-evidence \
  --json
```

## Results

- Syntax validation passed.
- `skills/investor-source-collectors/tests/test_investor_sources.py` passed.
- The CLI filtered-all package passed `tools/validate_collector_package.py`.
- The generated package reported:
  - `collection_readiness.status=scope_policy_filtered_all`
  - `manifest.event_count=1`
  - `manifest.usable_event_count=0`
  - `manifest.research_document_event_count=0`
  - `manifest.gap_event_count=1`
  - `collection_readiness.can_enter_data_quality_lake=true`
  - `investor_wiki_evidence.v1.json.generated_from.event_count=0`
  - `investor_wiki_evidence.v1.json.generated_from.raw_event_count=1`
  - `investor_wiki_evidence.v1.json.generated_from.gap_event_count=1`

## Boundary

This pass does not claim real Windows/Linux private corpus validation or OCR
quality validation. It hardens package semantics so FinClaw can ingest
collection gaps without turning them into Investor Wiki research facts.
