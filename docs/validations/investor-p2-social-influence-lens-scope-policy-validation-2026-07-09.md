# P2 Social Influence Lens Scope Policy Validation - 2026-07-09

## Scope

This validation covers `investor-source-collectors` `0.1.24`, specifically the
`social-investment-influence` lens that consumes authorized `social-activity`
Lake events from Weibo, Bilibili, and Xiaohongshu.

The goal is to add a Wiki-bound authorization boundary after the generic
`social-activity` collector. FinClaw can now narrow weak social influence
evidence by platform, action, source app, URL domain, creator, social topic, and
keyword before the lens writes Investor Wiki evidence.

## What Changed

- `investor_sources.py collect --source social-investment-influence` now accepts
  social influence scope flags:
  - `--allow-social-platform` / `--deny-social-platform`
  - `--allow-social-action` / `--deny-social-action`
  - `--allow-social-source-app` / `--deny-social-source-app`
  - `--allow-social-domain` / `--deny-social-domain`
  - `--allow-social-creator` / `--deny-social-creator`
  - `--allow-social-topic` / `--deny-social-topic`
  - `--allow-social-keyword` / `--deny-social-keyword`
- Manifest `collection_audit.social_influence_scope_policy` records configured
  filters, candidate counts, filtered counts, reason counts, and filtered-all
  state.
- Retained events include `data.social_influence_scope_policy` so each weak
  influence event can explain why it was allowed into the lens package.
- Fully filtered lens runs emit
  `social_influence_scope_policy_filtered_all`, report
  `collection_readiness.status=scope_policy_filtered_all`, and keep
  `collection_readiness.can_enter_finclaw=false`.
- `social_influence_boundary_proof.authorization_scope_boundary` mirrors the
  same policy for FinClaw/SoulMirror inspection.
- Pure lens gap packages keep
  `investor_wiki_evidence.v1.json.generated_from.event_count=0`.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/investor-source-collectors/scripts/investor_sources.py \
  skills/investor-source-collectors/scripts/investor_sources/parser.py \
  skills/investor-source-collectors/scripts/investor_sources/events.py \
  skills/investor-source-collectors/scripts/investor_sources/profiles.py \
  skills/investor-source-collectors/tests/test_investor_sources.py
```

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Project gates:

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
```

## Expected Signals

- Normal retained packages pass
  `tools/validate_collector_package.py --collector social-investment-influence
  --require-evidence`.
- Filtered-all lens packages contain one gap event with
  `data.payload.gap=social_influence_scope_policy_filtered_all`.
- `manifest.collection_readiness.status=scope_policy_filtered_all`.
- `manifest.collection_readiness.can_enter_finclaw=false`.
- `manifest.collection_audit.social_influence_scope_policy.filtered_all=true`.
- `manifest.social_influence_boundary_proof.authorization_scope_boundary`
  records the configured filters and filter reason counts.
- `investor_wiki_evidence.v1.json.generated_from.event_count=0` for pure gap
  packages.

## Product Boundary

- This is a weak-evidence lens, not a trading or research conclusion source.
- The policy narrows user-authorized social evidence before Wiki evidence
  generation; it does not assert that a social record is investment-relevant by
  itself.
- The lens does not crawl platforms, scrape public creator profiles, mirror full
  content, collect credentials, or claim complete social activity history.
- Real Weibo, Bilibili, and Xiaohongshu account/export validation, default
  creator/domain allowlists, social-topic false-positive review, and weak
  evidence backtests remain pending.
