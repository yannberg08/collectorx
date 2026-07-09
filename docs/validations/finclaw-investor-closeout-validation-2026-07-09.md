# FinClaw Investor Collector Closeout Validation - 2026-07-09

This validation records the closeout handoff pass for the P0/P1/P2
investor-avatar collector program.

## Scope

This pass does not add collectors and does not rewrite migrated collectors such
as `wechat-export`. It adds a product/QA handoff layer so the repository can
stop expanding and move into real-user validation.

## Changed artifacts

- `docs/investor-collector-closeout.md`
- `README.md`
- `docs/finclaw-investor-collector-productization.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`
- `docs/final-handoff-checklist.md`

## Acceptance assertions

- The closeout document records the current catalog count: 30 FinClaw entries.
- Readiness is separated into 1 `production-candidate`, 2 `deep-beta`, and 27
  `baseline+audit` entries.
- The document freezes the P0/P1/P2 scope for this handoff and explicitly
  blocks further collector expansion during closeout.
- It states that most collectors remain beta until real account, real device,
  real export, or Wiki backtest evidence exists.
- It defines what each P0/P1/P2 collector can provide to the investor avatar
  and what it must not claim yet.
- It keeps gap, preflight, empty, and filtered-all outputs out of Investor Wiki
  facts.
- README, the productization control board, production readiness, and the
  roadmap point to the closeout handoff view.
- `tools/test_finclaw_catalog.py` now verifies that the closeout handoff keeps
  the current catalog count, readiness distribution, priority distribution, and
  every catalog id in sync with `collectors/finclaw-investor-catalog.json`.
- README and `docs/first-investor-loop.md` now use
  `PYTHON=.venv/bin/python bash test_collectors.sh`, matching the closeout
  checklist and avoiding host-Python 3.9 validation failures on this machine.
- `tools/validate_project.py` now enforces readiness-to-product-surface
  alignment: production candidates must use guarded production, non-supporting
  deep beta entries must use deep beta, baseline generic/vertical entries must
  stay on import/managed beta surfaces, and lenses stay on lens beta.
- `tools/finclaw_catalog.py closeout --json` now emits a machine-readable
  launch-tier and real-validation-gap report so FinClaw product surfaces can
  distinguish guarded production candidates, invite-only deep beta entries,
  downstream lenses, managed-authorization beta entries, and authorized
  import/local beta entries without reinterpreting prose docs.
- `tools/test_finclaw_catalog.py` verifies the closeout report schema, the
  30-entry catalog count, the 1/2/27 readiness distribution, the single guarded
  production candidate, and the 29 entries that still require real validation
  before production.
- The closeout report now separates `requires_real_validation_before_production`
  from `has_remaining_validation_gap` / `remaining_validation_scope`, so the
  EastMoney production candidate remains a guarded launch candidate with
  post-launch validation gaps instead of being treated as fully production done.
- `docs/final-handoff-checklist.md` records the final handoff checklist for
  FinClaw product, QA, scheduling, package acceptance, and remaining real
  validation work; the closeout acceptance view links to it directly.
- `tools/finclaw_catalog.py validation-backlog --json` now exposes the next
  real-user/device/export validation queue derived from the catalog and
  closeout report. It is a QA planning view only; it does not add collectors or
  raise readiness.
- `tools/finclaw_catalog.py validation-template --json` generates a fillable
  real-validation evidence ledger from the backlog. The unfilled template is
  intentionally blocked by `validation-evidence`.
- `tools/finclaw_catalog.py artifact-manifest --artifact-root <root> --path
  <artifact> --json` generates ledger-ready artifact paths and sha256 hashes.
- `tools/finclaw_catalog.py validation-evidence --evidence <ledger> --json`
  audits a QA evidence ledger against that backlog and only permits
  `ready_for_readiness_review` when a record passes, covers the production gap,
  includes real-validation evidence types, artifacts, timestamp, and reviewer.
  It still does not edit readiness.
- `validation-evidence` and `readiness-review` support `--verify-artifacts`
  with `--artifact-root` so release QA can require local artifact existence and
  sha256 matches before accepting a record.
- `tools/finclaw_catalog.py readiness-review --evidence <ledger> --json`
  turns accepted validation evidence into a human review packet with eligible
  and blocked entries, required checks, and a non-editing catalog policy.
- `tools/finclaw_catalog.py readiness-change-audit --candidate-catalog <path>
  --evidence <ledger> --artifact-root <root> --json --require-clean` blocks
  proposed catalog readiness, gate, or production-gap changes that are not
  backed by verified review evidence.
- `docs/real-validation-evidence-ledger.md` documents the evidence ledger shape
  and the readiness boundary.

## Verification commands

To verify this pass, run:

```bash
python3 -m json.tool collectors/finclaw-investor-catalog.json >/dev/null
python3 -m json.tool collectors/finclaw-invocation-contracts.json >/dev/null
.venv/bin/python tools/validate_project.py
.venv/bin/python tools/finclaw_catalog.py closeout --json
.venv/bin/python tools/finclaw_catalog.py validation-backlog --json
.venv/bin/python tools/finclaw_catalog.py validation-template --json
.venv/bin/python tools/finclaw_catalog.py artifact-manifest --artifact-root <artifact-root> --path <artifact-file> --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence <ledger> --json
.venv/bin/python tools/finclaw_catalog.py validation-evidence --evidence <ledger> --verify-artifacts --artifact-root <artifact-root> --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence <ledger> --json
.venv/bin/python tools/finclaw_catalog.py readiness-review --evidence <ledger> --verify-artifacts --artifact-root <artifact-root> --json
.venv/bin/python tools/finclaw_catalog.py readiness-change-audit --candidate-catalog <candidate-catalog.json> --evidence <ledger> --artifact-root <artifact-root> --json --require-clean
.venv/bin/python skills/eastmoney-portfolio/tests/test_local_collect.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

This validation is a documentation and release-control gate. It does not claim
new real-account coverage.
