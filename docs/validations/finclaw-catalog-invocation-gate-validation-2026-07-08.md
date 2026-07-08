# FinClaw Catalog Invocation Gate Validation - 2026-07-08

## Scope

This pass strengthens the machine-readable FinClaw investor catalog so product
entries cannot quietly point to missing or malformed collector entrypoints.

## Changes

- Extended `tools/validate_project.py` catalog validation.
- Validates category-to-YAML-folder consistency.
- Validates referenced skill directories and `SKILL.md` files.
- Extracts Python script references from `cli` strings and verifies the files
  exist.
- Supports SoulMirror-style `<SKILL_DIR>/scripts/*.py` references.
- Requires lens entries to include `--source <collector-id>`.
- Requires non-SoulMirror entries to declare `<out-dir>`.
- Requires SoulMirror catalog entries to use `apiVersion: soulmirror/v1`.
- Fixed the `qq` catalog CLI so `--db-dir` is passed before the `collect`
  subcommand and outputs are written under `<out-dir>`.

## Validation Commands

```bash
.venv/bin/python - <<'PY'
from tools.validate_project import validate_investor_catalog
validate_investor_catalog()
print("catalog validation passed")
PY
```

```bash
PYTHON=.venv/bin/python bash test_collectors.sh
```

Expected result: all commands pass.

## Boundary

- This gate proves catalog entrypoints point to real local files.
- It does not prove every command can complete without user authorization.
- It does not upgrade QQ to a complete standard package collector; QQ still
  needs a future manifest/SUMMARY package pass.
