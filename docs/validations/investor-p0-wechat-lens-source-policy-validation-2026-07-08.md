# P0 WeChat Lens Source Policy Validation - 2026-07-08

This pass productizes the `wechat-investment-dialogue` lens after the generic
`wechat` collector gained standard package output.

## Scope

- Lens: `wechat-investment-dialogue`
- Skill: `investor-source-collectors`
- Priority: P0
- Goal: let FinClaw scope investment-dialogue lens runs to user-approved
  contacts, groups, and senders before classification.

## Implemented

- Added CLI flags:
  - `--allow-chat`
  - `--deny-chat`
  - `--allow-sender`
  - `--deny-sender`
- Patterns can be repeated or comma-separated.
- Source policy is applied before investment classification.
- Source policy only narrows scope; it does not assert investment relevance.
- Kept events carry `data.source_policy` metadata when a policy is active.
- Manifest `collection_audit.source_policy` records:
  - configured allow/deny patterns
  - whether the policy is enabled
  - filtered candidate count
  - filter reason counts
  - `policy_does_not_assert_investment_relevance`
- If every candidate is filtered by source policy, the run emits a gap event
  with status `source_policy_filtered_all` instead of reporting
  `no_investment_evidence_matched`.

## Validation

Command run:

```bash
.venv/bin/python skills/investor-source-collectors/tests/test_investor_sources.py
```

Covered fixtures:

- `--allow-chat` keeps an approved investment group.
- `--deny-sender` removes a noisy sender inside an approved group.
- Investment classification still runs after source policy filtering.
- Manifest records source-policy filtered candidate counts and reasons.
- A fully filtered run reports `source_policy_filtered_all` and writes no Wiki
  targets.

## Status

- `wechat-investment-dialogue`: `baseline+audit`

## Remaining Gap

- Real WeChat lake validation is still blocked until authorized WeChat 4.x
  source access is available.
- User-specific contact, group, and sender allowlists still need real tuning.
- Trade-adjacent backtests against broker executions and notes are required
  before production-candidate.
