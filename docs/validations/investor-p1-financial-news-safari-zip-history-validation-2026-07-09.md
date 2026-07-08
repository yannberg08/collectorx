# P1 Financial News Safari ZIP History Validation - 2026-07-09

This validation records the Safari and ZIP-packaged browser-history pass for
the `financial-news-usage` vertical collector.

## Scope

- Skill: `financial-news-usage` `0.2.7`
- Source: `financial-news-usage`
- FinClaw target: user-authorized CLS, WallstreetCN, and Gelonghui usage traces
  from local exports, saved pages, copied browser history, or authorized ZIP
  packages.

## Productization Change

The collector now accepts authorized Safari `History.db` in two practical user
paths:

- a direct copied `History.db` file under an authorized input directory;
- a ZIP package containing a browser-history member such as
  `Safari/History.db`.

ZIP browser-history members are parsed as SQLite databases, not decoded as
text. Emitted events keep user-visible provenance in `raw_ref.path` as
`archive.zip::member`, plus `source_archive` and `archive_member`.

`manifest.source_audit` and `usage_boundary_proof.source_artifact_boundary`
now expose:

- `browser_history_input_count`;
- `browser_history_event_count`;
- `browser_history_source_apps`;
- `browser_history_source_app_counts`.

Safari records preserve `visit_count` when present and map `load_successful`
into behavior-level load status. Browser-history rows are still domain-filtered
to CLS, WallstreetCN, and Gelonghui before they enter the Lake.

## Validation Commands

```bash
.venv/bin/python -m py_compile \
  skills/financial-news-usage/scripts/financial_news_usage/parser.py \
  skills/financial-news-usage/scripts/financial_news_usage.py \
  skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python skills/financial-news-usage/tests/test_financial_news_usage.py
.venv/bin/python tools/test_finclaw_catalog.py
.venv/bin/python tools/test_finclaw_batch_runner.py
.venv/bin/python tools/validate_project.py
PYTHON=.venv/bin/python bash test_collectors.sh
git diff --check
```

## Verified Behavior

- Direct Safari `History.db` fixture emits only CLS and Gelonghui finance-news
  visits; unrelated `example.com` rows are excluded.
- ZIP-packaged `Safari/History.db` emits the same domain-filtered events and
  preserves archive/member provenance.
- Temporary extraction paths are not leaked into events.
- `manifest.source_audit.browser_history_input_count` counts both direct and
  ZIP-member history inputs.
- `manifest.source_audit.browser_history_source_app_counts` reports
  `{"safari_history": 4}` for the direct-plus-ZIP regression fixture.
- `manifest.usage_behavior_summary` records Safari visit counts and load
  status counts.
- `usage_boundary_proof.proof_level` remains
  `authorized_financial_news_usage_with_browser_history`.
- The collector continues to avoid public-news crawling, public article
  mirroring, unrelated browser history, credentials, and platform-wide data.

## Remaining Gaps

- Real CLS, WallstreetCN, and Gelonghui app cache validation.
- Real account API validation.
- Real subscription and alert-store field differences.
- Real Safari/macOS `History.db` sample validation.
- Windows/Linux browser-history path validation.
- Topic and behavior false-positive review on noisy real exports.
