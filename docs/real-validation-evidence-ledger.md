# FinClaw Real Validation Evidence Ledger

CollectorX closeout is frozen at the catalog and launch-tier level. The next
phase is evidence collection: QA records real user, real account, real device,
real export, package validation, and Wiki backtest results in a small JSON
ledger, then audits that ledger against the current validation backlog.

The ledger does not promote collector readiness. It only says whether a
collector has enough evidence to enter a human readiness review.

## Command

```bash
.venv/bin/python tools/finclaw_catalog.py validation-backlog --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence \
  --evidence docs/validations/real-validation-evidence.json \
  --json
.venv/bin/python tools/finclaw_catalog.py readiness-review \
  --evidence docs/validations/real-validation-evidence.json \
  --json
```

Use `--require-all-review-ready` in release automation only when every selected
backlog item must have enough evidence for readiness review:

```bash
.venv/bin/python tools/finclaw_catalog.py validation-evidence \
  --priority P0 \
  --evidence docs/validations/real-validation-evidence.json \
  --json \
  --require-all-review-ready
```

## Ledger Shape

```json
{
  "schema": "collectorx.finclaw_real_validation_evidence.v1",
  "records": [
    {
      "record_id": "eastmoney-win-real-001",
      "collector_id": "eastmoney-portfolio",
      "result": "pass",
      "decision": "post_guarded_gap_closed",
      "covers_production_gap": true,
      "evidence_types": [
        "real_user_authorization",
        "real_account",
        "real_device",
        "wiki_backtest"
      ],
      "artifacts": [
        {
          "kind": "validated_package",
          "path": "/qa/eastmoney-win-real-001/manifest.json",
          "sha256": "<sha256>"
        }
      ],
      "validated_at": "2026-07-09T18:00:00+08:00",
      "validated_by": "qa-owner",
      "notes": "Real authorized account, read-only run, package and Wiki evidence validated."
    }
  ]
}
```

## Accepted Evidence Rules

A record is enough for `ready_for_readiness_review` only when all of these are
true:

- `collector_id` matches a selected validation backlog entry.
- `result` is `pass`.
- `decision` is one of `gap_closed`, `post_guarded_gap_closed`, or
  `ready_for_readiness_review`.
- `covers_production_gap` is `true`.
- `evidence_types` contains at least one real-validation type:
  `real_user_authorization`, `real_account`, `real_device`, `real_export`,
  `real_readonly_screen`, `real_api_response`, `wiki_backtest`, or
  `package_validation`.
- `artifacts` or `artifact_refs` is non-empty.
- `validated_at` and `validated_by` are present.

Anything else remains `missing_evidence` or `insufficient_evidence`.

## Readiness Review Packet

`readiness-review` consumes the same ledger and emits:

- `eligible_reviews`: collectors with accepted evidence and required human
  checks.
- `blocked_reviews`: collectors still missing evidence or holding insufficient
  evidence.
- `review_type`: for example `post_guarded_validation_review`,
  `production_candidate_review`, `lens_beta_review`, or
  `managed_authorization_review`.
- `next_action`: either keep the current readiness and collect more evidence,
  consider clearing a guarded post-launch gap, or consider a readiness
  promotion.
- `catalog_update_allowed_by_tool`: always `false`.

## Readiness Boundary

Passing `validation-evidence` does not edit
`collectors/finclaw-investor-catalog.json`. A human release review must inspect
the artifacts, update the catalog readiness and production gap explicitly, run
the full validation suite, and commit that change separately.
