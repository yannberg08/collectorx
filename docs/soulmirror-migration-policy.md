# SoulMirror Migration Policy

When a collector already exists in SoulMirror/Hermes and is validated, prefer
copying it into CollectorX as-is instead of redesigning it during migration.

## Rules

1. If a full skill exists under `~/.hermes/skills/<skill>/`, copy the skill
   directory verbatim into `skills/<skill>/` unless there is a licensing or
   secret-leakage reason not to.
2. Add or copy the collector YAML separately under `collectors/`.
3. Do not refactor during the same migration commit. Make behavior-changing
   improvements in a follow-up commit with tests.
4. Preserve provenance in `NOTICE.md` when the source is migrated from another
   local skill package.
5. If SoulMirror only exposes a daemon `driver` with no source code available,
   copy the YAML contract and implement an equivalent open CollectorX skill only
   after documenting the behavior.
6. Public market-data skills, such as quote/news/filing fetchers, are FinClaw
   research tools. Do not migrate them as personal-data collectors unless they
   collect user-owned usage traces.

## Current Local SoulMirror/Hermes Sources

| Source | Current CollectorX status |
| --- | --- |
| `wechat-export` | Present in `skills/wechat-export`; treated as generic collector |
| `feishu` | Present in `skills/feishu`; generic collector |
| `ticktick-cli` | Present in `skills/ticktick-cli`; generic task collector |
| `email-collector` | Present in `skills/email-collector`; generic email baseline |
| `notes-collector` | Present in `skills/notes-collector`; generic notes baseline |
| `qq-export` | Present in `skills/qq-export`; deep-designed generic communication collector |
| `ths-portfolio` | Present in `skills/ths-portfolio`; investor vertical collector |
| `eastmoney-portfolio` | Present in `skills/eastmoney-portfolio`; investor vertical collector |
| `xueqiu-watchlist` | Present in `skills/xueqiu-watchlist`; superseded by richer `xueqiu-investor-activity` roadmap |
| SoulMirror `filesystem` driver | YAML behavior copied; CollectorX has `filesystem-collector` equivalent because daemon source was not present locally |
| `cls-news`, `a-stock-data` | Not migrated as personal collectors; these are public research/data tools, not user-owned evidence |

## Migration Checklist

- Copy source skill without behavior changes.
- Run project validation.
- Mark category: `generic`, `vertical`, or `lens`.
- Add scope: collects/excludes.
- Add platform support notes.
- Add a production-readiness entry.

