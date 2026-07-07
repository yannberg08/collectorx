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

## Current Collectors

### Generic Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `filesystem` | daemon/driver | Config only; depends on host runtime |
| `wechat` | `wechat-export` | Migrated skill; provenance review required |
| `feishu` | `feishu` | Migrated skill; provenance review required |
| `ticktick` | `ticktick-cli` | Migrated skill; provenance review required |
| `doubao` | `doubao-chat-export` | Migrated skill; provenance review required |
| `email` | `email-collector` | Multi-account preflight/event baseline; needs real mailbox validation |
| `qq` | `qq-export` | Real macOS QQ NT store discovery; decrypt-ready adapters for contacts/groups/messages; current machine blocks LLDB passphrase capture |
| `notes` | `notes-collector` | Draft implementation |
| `dingtalk` | none yet | YAML placeholder; skill not implemented |

### Vertical Investor Collectors

| Collector | Skill | Status |
| --- | --- | --- |
| `ths-portfolio` | `ths-portfolio` | Draft CSV parser |
| `eastmoney-portfolio` | `eastmoney-portfolio` | macOS local + trade UI evidence Beta; strong trade tables require unlocked trading account |
| `xueqiu-watchlist` | `xueqiu-watchlist` | Draft CSV parser |
| `ths-watchlist` | none yet | YAML placeholder; skill not implemented |

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
