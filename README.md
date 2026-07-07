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

- `docs/production-readiness.md` records what is genuinely runnable versus what
  is still a placeholder or lens.
- `docs/finclaw-integration-guide.md` describes how FinClaw should discover,
  authorize, call, and gate collectors.
- `docs/investor-collector-productization-roadmap.md` tracks the P0/P1/P2
  productization waves and Git discipline.
- `docs/soulmirror-migration-policy.md` records the rule for copying existing
  SoulMirror/Hermes collectors without unnecessary rewrites.

## Current Collectors

### Generic Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `filesystem` | `filesystem-collector` | Metadata-only generic file collector aligned with SoulMirror driver boundary; investor routing is handled by lenses |
| `wechat` | `wechat-export` | Migrated skill; provenance review required |
| `feishu` | `feishu` | Migrated skill; provenance review required |
| `ticktick` | `ticktick-cli` + `ticktick_events.py` | API tool plus event-conversion baseline; real OAuth validation pending |
| `doubao` | `doubao-chat-export` | Migrated skill; provenance review required |
| `email` | `email-collector` | Multi-account preflight/event baseline; needs real mailbox validation |
| `qq` | `qq-export` | Real macOS QQ NT store discovery; decrypt-ready adapters for contacts/groups/messages; current machine blocks LLDB passphrase capture |
| `notes` | `notes-collector` | Event-package baseline for Obsidian/Notion plus authorized Youdao/Evernote/Markdown/HTML/JSON/ENEX imports; macOS Obsidian-style validation done |
| `dingtalk` | none yet | YAML placeholder; skill not implemented |
| `wecom` | none yet | YAML placeholder; enterprise WeChat generic channel |
| `calendar` | `calendar-collector` | Local ICS/JSON/CSV/TSV event-package baseline for generic calendar events; investment filtering handled by `task-calendar-investor` |
| `meeting-artifacts` | `meeting-artifacts` | Local file event-package baseline for meeting minutes/transcripts; platform API adapters pending |
| `wechat-favorites` | `wechat-favorites` | Local saved-article/favorites event-package baseline; real WeChat favorites adapter pending |
| `social-activity` | `social-activity` | Local activity export/saved-record baseline for Weibo/Bilibili/Xiaohongshu follows, likes, favorites, watch history, comments, and shares |

### Vertical Investor Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `ths-portfolio` | `ths-portfolio` | Local metadata + trade package; ongoing real-device validation |
| `eastmoney-portfolio` | `eastmoney-portfolio` | macOS local + authorized full trade Lake Beta; strong trade tables require unlocked trading account |
| `xueqiu-watchlist` | `xueqiu-watchlist` | Draft CSV parser |
| `xueqiu-investor-activity` | `xueqiu-investor-activity` | Normalized local export/package baseline for watchlists, follows, posts, comments, favorites, owner portfolios, and SoulMirror lake sync; real account adapter pending |
| `china-wealth-assets` | `china-wealth-assets` | Normalized local export/package baseline for fund, wealth, cash-management holdings, transactions, asset snapshots, Excel/JSON/CSV inputs, and SoulMirror lake sync |
| `financial-news-usage` | `financial-news-usage` | Local usage export/saved-page baseline for finance-app read, favorite, subscribe, search, and alert actions |
| `hk-us-brokerage` | `hk-us-brokerage` | Local read-only export baseline for Futu/Tiger/IBKR assets, positions, executions, orders, cashflows, dividends, and FX |
| `pro-terminal-usage` | `pro-terminal-usage` | Local workflow export baseline for Wind/Choice/iFinD/Bloomberg workspaces, watchlists, searches, downloads, templates, and factors |
| `ths-watchlist` | none yet | YAML placeholder; skill not implemented |

### Investor Lenses

| Lens | Upstream | Status |
| --- | --- | --- |
| `wechat-investment-dialogue` | `wechat` | Runnable lens baseline with investment classifier; real WeChat lake validation pending |
| `research-documents` | `filesystem`, `notes` | Runnable lens baseline for research files and valuation docs; explicit XLSX/DOCX/PDF content extraction validation done |
| `email-research` | `email` | Runnable lens baseline for broker research, roadshow, and IR mail; real mailbox validation pending |
| `meeting-minutes` | `meeting-artifacts`, `feishu`, `dingtalk`, `wecom` | Runnable lens baseline for roadshow/research/IC minutes; source adapters pending |
| `investment-notes` | `notes` | Runnable lens baseline for investment notes, reviews, rules, checklists; note adapters pending |
| `task-calendar-investor` | `ticktick`, `calendar` | Runnable lens baseline for research tasks, trade plans, review reminders; calendar validation pending |
| `wechat-article-favorites` | `wechat-favorites` | Runnable lens baseline for investment public-account articles; saved-article validation done |
| `social-investment-influence` | `social-activity` | Runnable lens baseline for weak investment creator and social influence signals |

Status legend:

- Migrated skill: copied or adapted from an existing local skill package. Confirm
  upstream license before public release.
- Draft implementation: usable for local validation, not yet proven against broad
  real-world exports.
- YAML placeholder: scheduling/config stub only; no real collection skill yet.

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
