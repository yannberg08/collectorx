# FinClaw Runbook Upstream Auto-Link Validation - 2026-07-08

## Purpose

Verify that FinClaw runbooks can automatically connect deterministic investor
lens inputs to ready upstream collector outputs in the same batch run.

## Scope

- `tools/finclaw_catalog.py`
- `tools/test_finclaw_catalog.py`
- `docs/finclaw-integration-guide.md`
- `docs/production-readiness.md`
- `docs/investor-collector-productization-roadmap.md`

## Product Contract

- `runbook --json` auto-fills missing placeholders named
  `<upstream-id-events-jsonl>` when the upstream collector is selected,
  `ready_to_run=true`, and has a known output package directory.
- Auto-filled links appear in `auto_upstream_links`.
- Auto-linked lenses move from `needs_upstream_lake` to `ready_lenses`.
- User-provided `--set` values override auto-linking.
- `--no-auto-link-upstream` disables this behavior and keeps explicit upstream
  Lake selection.
- Ambiguous placeholders such as `authorized-research-folder-or-events` remain
  explicit.

## Verification Commands

```bash
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/finclaw_catalog.py runbook \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --json
.venv/bin/python tools/finclaw_catalog.py runbook \
  --priority P0 \
  --out-dir-root /tmp/collectorx-out \
  --no-auto-link-upstream \
  --json
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Result

- FinClaw catalog tests passed.
- P0 default runbook auto-linked WeChat and email Lake outputs into
  `wechat-investment-dialogue` and `email-research`.
- P0 default runbook grouped two lenses into `ready_lenses` and left
  `research-documents` in `needs_upstream_lake`.
- The `--no-auto-link-upstream` runbook left `email-research` in
  `needs_upstream_lake`.
- Project validation passed.
- Diff whitespace check passed.

## Remaining Limits

This validation does not infer ambiguous or multi-source lens inputs. Those
still require explicit product or user selection.
