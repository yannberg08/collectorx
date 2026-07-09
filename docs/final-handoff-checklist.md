# FinClaw Investor Collector Final Handoff Checklist

Date: 2026-07-09

This is the final handoff checklist for the CollectorX P0/P1/P2 investor-avatar
collector closeout. It records the state that FinClaw product, QA, scheduling,
and follow-up validation should use after the scope freeze.

## Repository State

- Repository: `/Users/pengyingan/Desktop/collectorx`
- Branch: `main`
- GitHub remote: `origin/main`
- Handoff source of truth:
  - `collectors/finclaw-investor-catalog.json`
  - `collectors/finclaw-invocation-contracts.json`
  - `tools/finclaw_catalog.py closeout --json`
  - `docs/investor-collector-closeout.md`
  - `docs/finclaw-integration-guide.md`

## Current Catalog Counts

CollectorX currently exposes 30 FinClaw investor catalog entries.

Priority distribution:

| Priority | Count |
| --- | ---: |
| P0 | 12 |
| P1 | 13 |
| P2 | 4 |
| supporting | 1 |

Category distribution:

| Category | Count |
| --- | ---: |
| generic | 13 |
| lens | 8 |
| vertical | 9 |

Readiness distribution:

| Readiness | Count |
| --- | ---: |
| `production-candidate` | 1 |
| `deep-beta` | 2 |
| `baseline+audit` | 27 |

Launch-tier distribution:

| Launch tier | Count |
| --- | ---: |
| `guarded-production-candidate` | 1 |
| `invite-only-deep-beta` | 2 |
| `authorized-import-or-local-beta` | 18 |
| `downstream-lens-beta` | 8 |
| `managed-authorization-beta` | 1 |

Validation-gap distribution:

| Scope | Count |
| --- | ---: |
| `post_guarded_launch_validation` | 1 |
| `pre_production_validation` | 29 |

All 30 entries still have explicit remaining validation work recorded. The
single production candidate is a guarded launch candidate, not a fully finished
production claim.

## Catalog Entry Inventory

| Collector | Priority | Category | Readiness | Launch tier | Validation scope |
| --- | --- | --- | --- | --- | --- |
| `eastmoney-portfolio` | P0 | vertical | `production-candidate` | `guarded-production-candidate` | `post_guarded_launch_validation` |
| `ths-portfolio` | P0 | vertical | `deep-beta` | `invite-only-deep-beta` | `pre_production_validation` |
| `ths-watchlist` | P0 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `wechat` | P0 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `wechat-investment-dialogue` | P0 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `filesystem` | P0 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `research-documents` | P0 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `email` | P0 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `email-research` | P0 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `xueqiu-watchlist` | P0 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `xueqiu-investor-activity` | P0 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `china-wealth-assets` | P0 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `meeting-artifacts` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `dingtalk` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `wecom` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `feishu` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `meeting-minutes` | P1 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `notes` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `investment-notes` | P1 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `ticktick` | P1 | generic | `baseline+audit` | `managed-authorization-beta` | `pre_production_validation` |
| `calendar` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `task-calendar-investor` | P1 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `wechat-favorites` | P1 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `wechat-article-favorites` | P1 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `financial-news-usage` | P1 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `hk-us-brokerage` | P2 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `pro-terminal-usage` | P2 | vertical | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `social-activity` | P2 | generic | `baseline+audit` | `authorized-import-or-local-beta` | `pre_production_validation` |
| `social-investment-influence` | P2 | lens | `baseline+audit` | `downstream-lens-beta` | `pre_production_validation` |
| `qq` | supporting | generic | `deep-beta` | `invite-only-deep-beta` | `pre_production_validation` |

## Launch Decisions

| Launch class | Entries | Product wording |
| --- | --- | --- |
| Guarded production candidate | `eastmoney-portfolio` | User-authorized, read-only, guarded one-click collection after preflight. Must still show remaining Windows/Linux and broader account validation gaps. |
| Invite-only deep beta | `ths-portfolio`, `qq` | Beta only. Suitable for real-device sample expansion and controlled user validation. |
| Import/local beta | Generic and vertical `baseline+audit` collectors | User selects an authorized file, folder, ZIP, export, browser-history copy, local app root, or managed authorization path. Do not claim full account automation. |
| Downstream lens beta | All lens collectors | Run only after the required upstream Lake events exist. Lenses do not collect raw accounts directly. |
| Managed authorization beta | `ticktick` | Requires the SoulMirror/FinClaw managed authorization runner; do not treat as a plain command-only collector. |

## Non-Negotiable Boundaries

- Do not add new P0/P1/P2 collectors during closeout.
- Do not rewrite complete migrated collectors such as `wechat-export`.
- Do not treat gap, preflight, empty, no-input, or filtered-all packages as
  Investor Wiki personal facts.
- Do not let one channel collect every data type. Each collector owns only its
  declared evidence surface.
- Do not promote `baseline+audit` or `deep-beta` to production without real
  account, real device, real export, or Wiki backtest evidence.
- Do not treat `production-candidate` as full production done. It is guarded
  launch plus explicit post-launch validation.
- Do not collect secrets, passwords, cookies, tokens, trading mutations, or
  licensed vendor content outside the collector boundary.

## FinClaw Invocation Checklist

FinClaw should call the catalog helper instead of hand-building commands:

```bash
.venv/bin/python tools/finclaw_catalog.py closeout --json
.venv/bin/python tools/finclaw_catalog.py validation-backlog --json
.venv/bin/python tools/finclaw_catalog.py validation-template --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence docs/validations/real-validation-evidence.json --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence docs/validations/real-validation-evidence.json --verify-artifacts --artifact-root docs/validations/artifacts --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence docs/validations/real-validation-evidence.json --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence docs/validations/real-validation-evidence.json --verify-artifacts --artifact-root docs/validations/artifacts --json
.venv/bin/python tools/finclaw_catalog.py doctor --json
.venv/bin/python tools/finclaw_catalog.py runbook --json
.venv/bin/python tools/finclaw_catalog.py batch-manifest --json
.venv/bin/python tools/finclaw_catalog.py plan <collector-id> --json --require-ready
```

Execution runners should use the returned `argv` array, not the display command
string. After a collector exits, run the returned `package_validation.argv`
before ingesting its output into Lake or running Investor Wiki distillation.
Use `docs/real-validation-evidence-ledger.md` for the QA evidence ledger before
asking to raise any collector readiness.

## Package Acceptance Checklist

Every accepted package should be validated with:

```bash
.venv/bin/python tools/validate_collector_package.py <out-dir> --collector <collector-id> --json
```

For vertical and lens collectors, require investor evidence:

```bash
.venv/bin/python tools/validate_collector_package.py <out-dir> --collector <collector-id> --require-evidence --json
.venv/bin/python tools/validate_investor_wiki_evidence.py <out-dir>/investor_wiki_evidence.v1.json
```

Do not ingest packages whose manifest says the retained business event count is
zero, whose readiness state is a data-quality gap, or whose evidence says it
cannot feed the Investor Wiki.

## Validation Commands

The closeout state has been verified with:

```bash
.venv/bin/python tools/finclaw_catalog.py closeout --json
.venv/bin/python tools/finclaw_catalog.py validation-backlog --json
.venv/bin/python tools/finclaw_catalog.py validation-template --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence <evidence-ledger.json> --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence <evidence-ledger.json> --verify-artifacts --artifact-root <artifact-root> --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence <evidence-ledger.json> --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence <evidence-ledger.json> --verify-artifacts --artifact-root <artifact-root> --json
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Remaining Work After Handoff

The next phase is real validation, not more collector expansion.

P0:

- EastMoney Windows/Linux real devices and broader account states.
- Tonghuashun multi-account and real GUI snapshot coverage.
- WeChat real Lake, contact/group/sender allowlists, and trade-adjacent
  backtests.
- Email real mailbox/root validation and no-full-body leakage review.
- Xueqiu real account/HAR/browser-history pagination validation.
- China wealth real platform exports, PDF/HAR/read-only screens, and
  cross-source double-counting checks.

P1:

- Notes, task/calendar, meeting/collaboration, WeChat favorites, and financial
  news usage real account/export validation.
- False-positive and Wiki evidence backtests on real user corpora.

P2:

- HK/US brokerage real statements or read-only screens.
- Professional terminal license-safe real workflow exports.
- Social activity real exports/browser history and weak-evidence backtests.

## Handoff Summary

CollectorX is now organized enough for FinClaw controlled integration:

- Use `eastmoney-portfolio` as the only guarded production candidate.
- Use `ths-portfolio` and `qq` as invite-only deep beta.
- Use all other P0/P1/P2 collectors as authorized beta/lens flows.
- Keep scope frozen until real validation evidence changes the readiness state.
