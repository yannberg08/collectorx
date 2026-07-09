# FinClaw Package Readiness Validator - 2026-07-09

## Scope

This pass strengthens the global CollectorX package validator from structural
package checks to FinClaw investment-collector readiness checks.

## Validator Changes

- Cross-checks `manifest.event_count`, `usable_event_count`, and
  `gap_event_count` against the actual `lake/<collector>/events.jsonl` records.
- Cross-checks dedicated usable business counters, including brokerage,
  workflow, social-activity, social-influence, asset, watchlist, activity,
  usage, collaboration, meeting-artifact, email-research, research-document,
  filesystem/file, Feishu, WeChat-favorite, favorite, calendar, task, email,
  and note counters when they are present.
- Requires known collector packages to declare their primary usable business
  counter at the manifest level, such as `research_document_event_count` for
  `research-documents` and `asset_event_count` for `china-wealth-assets`.
- Rejects gap events unless they route only to
  `collectorx.data_quality.collection_gaps`.
- Rejects gap-only packages that claim business Lake entry or Investor Wiki
  evidence readiness through `manifest.collection_readiness`; package-level
  `can_enter_finclaw_lake` remains compatible with existing data-quality gap
  ingress semantics.
- Verifies `can_enter_data_quality_lake` agrees with actual gap-event presence
  when the readiness gate is declared.
- Enforces the social-activity readiness contract:
  `can_feed_investor_wiki_directly=false`, and gap-only social-activity packages
  cannot feed `social-investment-influence`.
- Verifies generated Investor Wiki evidence counts non-gap facts only:
  `generated_from.event_count` must match usable events, `raw_event_count` must
  match raw events when present, and `gap_event_count` must match actual gaps
  when present.
- Rejects evidence fact trees and route summaries that expose data-quality gap
  routes as Investor Wiki facts.

## Test Coverage

`tools/test_collector_package_validator.py` now covers:

- a valid business package with readiness counters and evidence
- a valid gap-only package with data-quality routing and zero Wiki facts
- an invalid gap route
- invalid manifest counts
- invalid gap-only business/Wiki readiness claims
- invalid social-activity direct Wiki readiness
- invalid gap-only social-activity lens readiness
- invalid evidence generated-from counts that treat gaps as facts
- route-aware data-quality packages such as filesystem gap packages that write
  to `lake/data_quality/events.jsonl`
- collector-specific primary counters for filesystem, Feishu, and
  WeChat-favorites
- known collector packages missing their required primary manifest counter

## Boundaries

- No `skills/**` collector implementations were changed.
- Collector catalog, invocation contract, README, and production docs were
  updated to describe the stricter shared readiness semantics introduced here.
- The semantic checks are field-aware: legacy packages without
  `collection_readiness` remain structurally valid, but any declared readiness
  or count fields must agree with the events.
