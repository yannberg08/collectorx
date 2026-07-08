# FinClaw Skill Metadata Gate Validation - 2026-07-08

This validation records the project-level metadata consistency gate for
catalog-callable CollectorX skills.

## Scope

- Add a reusable `tools/validate_project.py` gate for skill metadata.
- Require every skill referenced by `collectors/finclaw-investor-catalog.json`
  to have both `.collectorx.json` and `VERSION`.
- Require `.collectorx.json.version` to match the local `VERSION` file.
- Require machine-readable skill identity and description fields.
- Align existing stale metadata so FinClaw discovery does not see outdated
  versions.

## Code Changes

- Added `validate_skill_metadata()` to `tools/validate_project.py`.
- Wired the gate into the full project validation path.
- Added `.collectorx.json` for:
  - `skills/wechat-export`
  - `skills/ticktick-cli`
- Updated metadata versions/descriptions for:
  - `skills/calendar-collector`
  - `skills/china-wealth-assets`
  - `skills/email-collector`
  - `skills/notes-collector`
  - `skills/xueqiu-watchlist`
  - `skills/xueqiu-investor-activity`

## Validation

```bash
.venv/bin/python tools/validate_project.py
```

Result:

- Project validation passed.
- All catalog-referenced skill metadata files exist.
- All checked `.collectorx.json.version` values match `VERSION`.
- Existing parser/unit tests, CLI help checks, event examples, FinClaw catalog
  validation, metadata validation, and first-investor-loop package validation
  all passed.

## Non-Goals

- No new real-account validation is claimed.
- No collector readiness level was promoted.
- This does not replace package validation or investor Wiki evidence
  validation; it makes skill discovery metadata auditable before FinClaw calls a
  collector.
