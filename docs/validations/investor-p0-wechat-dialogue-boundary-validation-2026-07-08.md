# P0 WeChat Dialogue Boundary Validation - 2026-07-08

This validation records the P0 pass that adds dialogue-boundary proof and
dialogue surface summaries to the `wechat-investment-dialogue` lens.

## Scope

- Skill: `investor-source-collectors`
- Version: `0.1.11`
- Lens: `wechat-investment-dialogue`
- Upstream role: already-collected `wechat` lake events only.
- FinClaw target: investment discussions, buy/sell reasons, consultation
  network, sentiment/risk clues, research discussion, and review reflection.

## Productization change

- `manifest.wechat_dialogue_boundary_proof` now records:
  - candidate, matched, and filtered counts;
  - chat/sender allow and deny policies;
  - source-policy filtered counts and reasons;
  - chat count, sender count, owner/non-owner message count, group/private chat
    event counts, time/text coverage, and source-policy coverage;
  - no claim of complete WeChat history, complete dialogue context, raw WeChat
    database access, or direct WeChat reconnect.
- `manifest.lens_surface_summary` now reports WeChat investment dialogue
  surfaces: trade intention, buy/sell reason, position sizing, risk emotion,
  consultation network, research discussion, and review reflection.
- `investor_wiki_evidence.v1.json.coverage_summary.source_surface_summary`
  now carries the same `wechat-investment-dialogue` surface summary.

## Validation commands

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
.venv/bin/python -m py_compile skills/investor-source-collectors/scripts/investor_sources/events.py skills/investor-source-collectors/tests/test_investor_sources.py
```

## Verified behavior

- Investment chat fixtures emit `authorized_wechat_dialogue_partial` proof.
- Chat/sender allow and deny policy emits
  `authorized_wechat_dialogue_with_source_policy` proof and records policy
  boundaries without treating source policy as investment relevance.
- A fully filtered source-policy run emits `source_policy_filtered_all` proof and
  cannot enter FinClaw as Wiki evidence.
- Non-investment casual chat emits
  `no_usable_investment_dialogue_after_filter` proof and leaves Wiki coverage
  empty.
- Evidence packages include the dialogue surface summary under
  `coverage_summary.source_surface_summary.wechat-investment-dialogue`.

## Remaining production gaps

- Real WeChat 4.x lake validation is still blocked on this Mac by the current
  key/SIP precondition.
- User-tuned contact/group/sender allowlists must be validated on real chat
  histories.
- Trade-adjacent backtesting is still required before raising readiness beyond
  `baseline+audit`.
