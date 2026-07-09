# P0 Filesystem Readiness Gate Validation - 2026-07-09

This validation covers `filesystem-collector` version `0.3.3`.

## Scope

- Generic collector: `filesystem`
- Downstream lens: `research-documents`
- Normal route: `lake/filesystem/events.jsonl`
- Gap route: `lake/data_quality/events.jsonl`
- Gap target: `collectorx.data_quality.collection_gaps`

## What Changed

- Replaced the legacy gap target
  `investor.data_quality.collection_gaps` with
  `collectorx.data_quality.collection_gaps`.
- Normal file metadata packages now set:
  - `usable_event_count`
  - `filesystem_event_count`
  - `file_event_count`
  - `gap_event_count`
- `collection_readiness` now includes:
  - `can_enter_filesystem_lake`
  - `can_enter_data_quality_lake`
  - `can_feed_research_documents_lens`
  - `can_feed_investor_wiki_directly=false`
- Filtered-all and no-metadata packages emit validator-safe profile gap events
  with legal `time`, `gap_kind=collection_gap`,
  `business_records_written=false`, `read_only=true`, and
  `wiki_targets=["collectorx.data_quality.collection_gaps"]`.
- Gap-only packages write only to `lake/data_quality/events.jsonl`; they do not
  create `lake/filesystem/events.jsonl` and cannot feed
  `research-documents` or Investor Wiki directly.
- Normal file metadata still writes to `lake/filesystem/events.jsonl` and can
  feed the `research-documents` lens.

## Fixture Coverage

- Normal metadata package:
  - one file event in `lake/filesystem/events.jsonl`
  - no `lake/data_quality/events.jsonl`
  - `can_enter_filesystem_lake=true`
  - `can_enter_data_quality_lake=false`
  - `can_feed_research_documents_lens=true`
  - package validator passes with `--collector filesystem`
- Filtered-all gap package:
  - no `lake/filesystem/events.jsonl`
  - one profile gap event in `lake/data_quality/events.jsonl`
  - `gap_event_count=1`
  - `can_enter_filesystem_lake=false`
  - `can_enter_data_quality_lake=true`
  - `can_feed_research_documents_lens=false`
- No-metadata gap package:
  - missing authorized root records a no-metadata profile gap
  - no raw local path is written into the gap event
  - `business_records_written=false`
  - `read_only=true`

## Validation Commands

```bash
.venv/bin/python skills/filesystem-collector/tests/test_filesystem_collector.py
```

```bash
.venv/bin/python skills/filesystem-collector/scripts/filesystem_query.py collect \
  --root /tmp/filesystem_readiness_normal_cli/input \
  --out-dir /tmp/filesystem_readiness_normal_cli/out \
  --format summary

.venv/bin/python tools/validate_collector_package.py \
  /tmp/filesystem_readiness_normal_cli/out \
  --collector filesystem
```

```bash
git diff --check
```

## Results

- Filesystem fixture tests passed.
- Manual normal fixture package passed
  `tools/validate_collector_package.py --collector filesystem`.
- `git diff --check` passed.

## Integration Notes

- Main-thread catalog and invocation contract updates should point filesystem
  gaps at `collectorx.data_quality.collection_gaps`.
- Main-thread readiness docs should treat `can_feed_research_documents_lens` as
  the upstream gate for `research-documents`.
- Package validators that want to validate gap-only data-quality routes by
  collector id may need a future route-aware mode; this pass keeps the required
  `--collector filesystem` validator check on a normal filesystem fixture.
