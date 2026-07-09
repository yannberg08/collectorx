# CollectorX

CollectorX is an open collector framework for user-owned data. It is designed
to feed local-first lake, distill, wiki, and agent systems such as SoulMirror
and FinClaw-style vertical avatars.

## Core Position

CollectorX collects the user's own data. It is not a market-data or news-data
crawler.

In a FinClaw investor-avatar system:

- CollectorX collects personal evidence: messages, files, notes, tasks, email,
  trades, holdings, watchlists, and reviews.
- Public financial tools collect external data: market quotes, filings,
  earnings, news, research reports, and macro data.
- Distill apps combine both sides when needed, but only user-owned evidence
  should directly shape the personal wiki.

## Architecture

```text
collector skill
  -> CollectorX Event
  -> lake
  -> distill app
  -> general wiki / vertical wiki
  -> agent and product applications
```

A collector is composed of:

```text
collector = skill implementation + collector YAML
```

- `skills/<name>/` contains collection logic, docs, references, and tests.
- `collectors/<category>/<id>.yaml` contains scheduling, authorization, and
  routing metadata.
- `schemas/collectorx-event.schema.json` defines the normalized event contract.
- `examples/events/` contains event examples for downstream app designers.

## Collector Classes

CollectorX separates channels by responsibility:

- **Generic collectors** collect authorized personal channel evidence without
  deciding whether it is investment-related.
- **Vertical investor collectors** collect finance/investment-native sources
  such as brokerages, Xueqiu, fund/wealth accounts, professional terminals, or
  finance-app usage traces.
- **Investor lenses** consume generic lake events and route only investment
  evidence into `finclaw.investor_wiki_evidence.v1`.

See `docs/collector-taxonomy.md` for the full boundary table.

Operational docs:

- `collectors/finclaw-investor-catalog.json` is the machine-readable FinClaw
  investor-collector catalog: priority, readiness, CLI, product action,
  collection scope, exclusions, and remaining production gap.
- `collectors/finclaw-invocation-contracts.json` is the machine-readable
  authorization and product-surface contract for every FinClaw catalog entry:
  authorization mode, user step, preflight, failure state, and evidence role.
- `docs/finclaw-investor-collector-productization.md` is the human control board
  for the P0/P1/P2 investor-avatar collector program.
- `docs/production-readiness.md` records what is genuinely runnable versus what
  is still a placeholder or lens.
- `docs/finclaw-integration-guide.md` describes how FinClaw should discover,
  authorize, call, and gate collectors.
- `tools/validate_collector_package.py` validates a collector output directory
  before FinClaw ingests it into Lake or runs Wiki distillation.
- `tools/finclaw_catalog.py` gives FinClaw a stable CLI for listing catalog
  entries, inspecting authorization/preflight details, rendering invocation
  plans, producing a batch readiness matrix, and building a staged runbook from
  the catalog plus invocation contracts. Product runners should use `doctor`
  for setup screens, `runbook` for batch execution order, `batch-manifest` for
  compact product execution manifests, and
  `plan --require-ready` before executing a single collector, then execute the
  returned `argv` list rather than reparsing the display command string.
  Runbook auto-links deterministic `<upstream-id-events-jsonl>` lens inputs
  from ready upstream package paths.
  After a collector exits, runners should execute the returned
  `package_validation.argv` before ingesting the package into Lake.
- `tools/run_finclaw_batch.py` consumes a batch manifest or builds one from the
  catalog. It defaults to dry-run reporting; `--execute` is required before it
  runs ready steps and their post-run package validations.
- `tools/validate_investor_wiki_evidence.py` validates
  `finclaw.investor_wiki_evidence.v1` packages before SoulMirror/FinClaw writes
  the final investor Wiki.
- `docs/investor-collector-productization-roadmap.md` tracks the P0/P1/P2
  productization waves and Git discipline.
- `docs/soulmirror-migration-policy.md` records the rule for copying existing
  SoulMirror/Hermes collectors without unnecessary rewrites.

## Current Collectors

### Generic Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `filesystem` | `filesystem-collector` | Metadata-only generic file collector aligned with SoulMirror driver boundary; manifest includes source audit, extension/path/file-name/directory/keyword scope-policy audit, filtered-all/no-metadata gap packages, filesystem boundary proof, skip reasons, per-root results, and macOS/Windows/Linux default-root plan; investor routing is handled by lenses |
| `wechat` | `wechat-export` | WeChat 4.x local query baseline with `--collect --out-dir` CollectorX package output, preflight/no-message gap packages, field/filter/source audit manifest, and generic-to-lens boundary; real-source validation still requires authorized keys/platform setup |
| `feishu` | `feishu` | Legacy OAuth/API tool plus authorized local/ZIP export package baseline for Feishu messages, documents, file refs, folders, meetings, recordings, source audit, ZIP skip reasons, and path-level parse results; real account API validation pending |
| `ticktick` | `ticktick-cli` | SoulMirror-style collector YAML + AgentRunner + skill path; live collection returns a JSON array through `collect_for_soulmirror.py`, while `ticktick_events.py` remains an offline authorized-export conversion helper with source-app/project/tag/keyword scope-policy audit and filtered-all/no-input profile gap events; managed OAuth validation pending |
| `doubao` | `doubao-chat-export` | Migrated skill; provenance review required |
| `email` | `email-collector` | Multi-account IMAP plus authorized local email scan and EML/EMLX/Maildir/MBOX/JSON/CSV/ZIP package output with account/folder audit, local-scan/import audit, skipped file/ZIP-member reasons, email authorization scope-policy audit, filtered-all readiness, field coverage, body/attachment policy, and generic-to-lens boundary; real mailbox/root validation still pending |
| `qq` | `qq-export` | QQ local/NT discovery plus `collect --out-dir` standard package output with events, manifest, summary, field/filter audit, and explicit gap packages; current machine still needs authorized/decrypted QQ NT data for real-message validation |
| `notes` | `notes-collector` | Event-package baseline for Obsidian Markdown/Canvas and Notion plus authorized Youdao/Evernote/Markdown/HTML/JSON/ENEX/ZIP imports; manifest reports P1 note-platform coverage, source-app/path/tag authorization filters, table/Canvas import audit, per-input source audit, skip reasons, missing platforms, and validator-safe filtered-all/no-input gap packages |
| `dingtalk` | `collaboration-exports` | Authorized local/ZIP export baseline for DingTalk messages, chats, contacts, file refs, and meeting refs; manifest includes field coverage, source-platform/record-kind/chat/sender/participant/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, source audit, ZIP skip reasons, and path-level parse results; investment filtering handled by lenses |
| `wecom` | `collaboration-exports` | Authorized local/ZIP export baseline for WeCom messages, chats, contacts, file refs, and meeting refs; manifest includes field coverage, source-platform/record-kind/chat/sender/participant/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, source audit, ZIP skip reasons, and path-level parse results; investment filtering handled by lenses |
| `calendar` | `calendar-collector` | Local ICS/JSON/CSV/TSV/ZIP event-package baseline with Apple/Google/Outlook/Feishu/DingTalk/WeCom/Tencent Meeting platform coverage, source-platform/calendar/attendee/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, source audit, ZIP skip reasons, and path-level parse results; investment filtering handled by `task-calendar-investor` |
| `meeting-artifacts` | `meeting-artifacts` | Authorized local/platform-export/ZIP baseline for meeting minutes, transcripts, HTML/CSV/JSON exports, participants, links, platform normalization, source-platform/participant/keyword scope-policy audit, platform coverage, validator-safe filtered-all/no-input gap packages, missing/unsupported input audit, ZIP skip reasons, and path-level parse audit; account API adapters pending |
| `wechat-favorites` | `wechat-favorites` | Local saved-article/favorites/read/share file/folder/ZIP baseline with action coverage, source-account/action/tag/domain/keyword scope-policy audit, per-input source audit, skip reasons, and path-safety manifest; real WeChat favorites adapter pending |
| `social-activity` | `social-activity` | Local JSON/CSV/Excel/HTML/TXT/ZIP/browser-history activity baseline for Weibo/Bilibili/Xiaohongshu follows, likes, favorites, watch history, comments, shares, browser-history visits, creators, engagement counts, visit/typed counts, browser transition types, social influence topics, weak influence signals, platform/action/source-app/domain/creator/topic/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, platform/action/field coverage, social activity boundary proof, per-input source audit, skipped reasons, and ZIP member audit |

### Vertical Investor Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `ths-portfolio` | `ths-portfolio` | Local metadata + strong trade package with event-kind/symbol/account/source/keyword authorization scope-policy audit, explicit filtered-all gap event, and Wiki boundary proof; ongoing real-device validation |
| `eastmoney-portfolio` | `eastmoney-portfolio` | macOS local + authorized full trade Lake production candidate with event-kind/symbol/account/source/keyword authorization scope-policy audit, filtered-all readiness, and strong trade boundary proof; strong trade tables require unlocked trading account |
| `xueqiu-watchlist` | `xueqiu-watchlist` | Authorized local export/package baseline for Xueqiu watchlists with source audit, symbol/market/group/industry/tag/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, field coverage, watchlist boundary proof, and 7/20 Wiki evidence package; attention-universe evidence only |
| `xueqiu-investor-activity` | `xueqiu-investor-activity` | Normalized local export/package/HAR/browser-history baseline for watchlists, follows, posts, comments, favorites, saved pages, owner portfolios, browser-history visits, source apps, visit/typed counts, transition types, domain-filter audit, source/pagination audit, activity/source-surface/source-app/domain/symbol/author/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, field coverage, and SoulMirror lake sync; real account adapter pending |
| `china-wealth-assets` | `china-wealth-assets` | Normalized local export/package baseline for fund, wealth, cash-management holdings, transactions, asset snapshots, Excel/legacy-XLS/HTML-table/PDF-statement/JSON/CSV/ZIP/HAR inputs, platform/account/subtype/product/currency/side/keyword scope-policy audit, filtered-all gap packages, source/PDF/HAR audit, platform/field/account/asset-surface/currency coverage, asset value summary, asset-boundary proof, and SoulMirror lake sync |
| `financial-news-usage` | `financial-news-usage` | Local usage export, saved-page, ZIP, direct Chromium/Safari browser-history, and ZIP-packaged browser-history baseline for finance-app read, favorite, subscribe, search, and alert actions with platform/action/topic coverage, behavior summary, platform/action/source-app/domain/topic/keyword scope-policy audit, filtered-all gap packages, browser source counts, per-input source audit, skip reasons, and path-safety manifest |
| `hk-us-brokerage` | `hk-us-brokerage` | Local read-only CSV/JSON/Excel/ZIP export baseline for Futu/Tiger/IBKR assets, positions, executions, orders, cashflows, dividends, FX, margin, tax, settlement fields, account-boundary/currency-market/fee-tax-margin summaries, broker/account/subtype/symbol/market/currency/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, unified brokerage-boundary proof, broker/trade-surface/field coverage, per-input source audit, skip reasons, and path-safety manifest |
| `pro-terminal-usage` | `pro-terminal-usage` | Local workflow CSV/JSON/Excel/HTML/TXT/LOG/ZIP export baseline for Wind/Choice/iFinD/Bloomberg workspaces, watchlists, searches, downloads, templates, factors, datasets, fields, function codes, query terms, parameters, export paths, row counts, workspace/template IDs, object counts, terminal/activity/field/topic coverage, workflow-intensity summary, terminal/activity/workspace/project/dataset/field/keyword scope-policy audit, validator-safe filtered-all/no-input gap packages, unified workflow-boundary proof, per-input source audit, skip reasons, and license-safe manifest |
| `ths-watchlist` | `ths-watchlist` | Authorized local-scan plus export/package baseline for Tonghuashun watchlists with local-scan provenance, path-level source audit, ZIP provenance, symbol/market/group/industry/tag/keyword/source scope-policy audit, validator-safe filtered-all/no-input gap packages, field coverage, ths_watchlist_boundary_proof, and 7/20 Wiki evidence package; attention-universe evidence only, corroborate with trades/research |

### Investor Lenses

| Lens | Upstream | Status |
| --- | --- | --- |
| `wechat-investment-dialogue` | `wechat` | Runnable lens baseline with investment classifier, optional chat/sender source policy, source-policy audit, and explicit filtered-all gap status; real WeChat lake validation pending |
| `research-documents` | `filesystem`, `notes` | Runnable lens baseline for research files and valuation docs; explicit XLS/XLSX/PPTX/DOCX/PDF content extraction, extension/path/file-name/parser/surface/keyword scope-policy audit, filtered-all readiness, path-level collection audit, skipped reasons, limit truncation, and screenshot metadata-only/no-OCR policy validation done |
| `email-research` | `email` | Runnable lens baseline for broker research, morning meetings, roadshow invites, IR mail, earnings alerts, research attachment refs, sender-domain/body-preview/attachment boundaries, sender-domain/folder/mailbox/subject/attachment/surface/keyword scope-policy audit, filtered-all readiness, and email-research boundary proof; real mailbox validation pending |
| `meeting-minutes` | `meeting-artifacts`, `feishu`, `dingtalk`, `wecom` | Runnable lens baseline for roadshow/research/IC/expert/earnings minutes, decision points, risk discussions, follow-up actions, upstream platform surface, and participant/attachment/recording refs; source account adapters pending |
| `investment-notes` | `notes` | Runnable lens baseline for investment notes, reviews, rules, checklists, valuation assumptions, source-app surface, and preview/full-content surface; generic notes gap packages stay in data-quality routing and are not promoted as investment facts |
| `task-calendar-investor` | `ticktick`, `calendar` | Runnable lens baseline for research tasks, trade plans, review reminders, earnings calendar, research meetings, risk checks, upstream source surface, scope-policy boundary, and reminder/time surface |
| `wechat-article-favorites` | `wechat-favorites` | Runnable lens baseline for investment public-account articles, saved/read/share/saved-file action surface, broker/fundamental/strategy/industry/valuation/portfolio/risk/macro article surfaces, and source-account type coverage |
| `social-investment-influence` | `social-activity` | Runnable lens baseline for weak investment creator, social influence topic, platform/action/source-app/domain/creator/topic/keyword scope-policy audit, filtered-all gap state, corroboration-candidate signals, and social influence boundary proof |

Status legend:

- `production-candidate`: at least one real user/device path is validated and
  FinClaw may expose it as a guarded user-facing collector.
- `deep-beta`: substantial implementation and tests exist, but broader real
  device coverage is still required.
- `baseline+audit`: runnable local/export/package path exists with tests,
  manifest coverage, provenance, and evidence policy, but real account
  validation is incomplete.
- `baseline`: runnable baseline exists with tests, but audit coverage or real
  validation is incomplete.
- `migrated-review`: copied or adapted local skill that still needs provenance,
  license, and investor-specific boundary review before broad exposure.

## Event Contract

Read `docs/event-contract.md` first. Every collector should output events shaped
like:

```json
{
  "schema": "collectorx.event.v1",
  "id": "stable-event-id",
  "collector": "collector-id",
  "source": "human-readable evidence source",
  "owner_scope": "personal",
  "kind": "message|file|note|email|calendar|task|trade|holding|watchlist|a2a|profile|other",
  "time": "2026-07-07T15:00:00+08:00",
  "collected_at": "2026-07-07T15:05:00+08:00",
  "data": {},
  "raw_ref": {},
  "privacy": {
    "sensitive": true,
    "local_only": true
  }
}
```

## Validation

Run the project validation suite:

```bash
bash test_collectors.sh
```

The suite currently checks:

- no `.DS_Store` files
- Python syntax for all scripts
- CLI `--help` for draft collectors
- FinClaw catalog helper CLI, invocation-plan tests, safe `argv` rendering,
  package-validation argv rendering, readiness doctor/runbook, and
  ready-to-run gate
- package-level validation for standard CollectorX outputs
- FinClaw catalog entrypoints: collector YAML category, skill directory, script
  references, lens source ids, and output targets
- FinClaw catalog coverage: every collector YAML must be present in the
  investor catalog or explicitly excluded with a reason
- FinClaw invocation contracts: every catalog entry has a matching
  authorization mode, product surface, evidence role, user step, preflight, and
  failure state
- FinClaw catalog skill metadata: every catalog-referenced skill has
  `.collectorx.json`, a `VERSION`, matching version values, and a non-empty
  machine-readable description
- parser unit tests for portfolio/watchlist collectors
- investor lens classifier tests for matched and non-matched evidence
- event example shape

This is a quality baseline, not a claim that every collector has been verified
on real user data or every operating system.

## First Investor Loop

Run the first deterministic investor-avatar loop:

```bash
python3 tools/run_first_investor_loop.py \
  --input-csv examples/fixtures/ths-portfolio.sample.csv \
  --out-dir .tmp/first-investor-loop
```

This produces:

```text
.tmp/first-investor-loop/
├── lake/ths-portfolio/events.jsonl
├── manifest.json
├── investor_wiki_evidence.v1.json
├── wiki/vertical/investor/record-review/决策日志.md
├── wiki/vertical/investor/risk-portfolio/组合约束.md
├── wiki/vertical/investor/competence-circle/公司能力圈.md
├── wiki/vertical/investor/decision-framework/仓位决策.md
└── wiki/vertical/investor_maturity.json
```

The loop proves the file/data path from a portfolio collector to an investor
wiki. It is deterministic and conservative: trade records prove actions, not
the user's full reasons or investment philosophy.

## Release Rules

Before public release:

1. Confirm provenance and license for every migrated skill in `NOTICE.md`.
2. Mark platform support precisely: real device, CI only, code path only, or not
   supported.
3. Add real fixture coverage for each draft collector without leaking private
   data.
4. Ensure every collector emits `collectorx.event.v1`.
5. Prove at least one full loop: collector -> event -> lake -> distill app ->
   wiki.

## License

CollectorX-original files are MIT licensed. Migrated skills may have different
upstream licensing requirements; see `NOTICE.md` before redistribution.
