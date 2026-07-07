# Collector Production Readiness

This document is the honest product status for CollectorX. A collector being
listed in `collectors/` does not mean it is production-ready. The goal is to
avoid building placeholders that look complete.

## Readiness Levels

| Level | Meaning | Required proof |
| --- | --- | --- |
| `production-candidate` | Can be used by FinClaw with real user authorization on at least one verified platform | Real-device run, stable event output, readiness manifest, tests, no secret leakage |
| `deep-beta` | Deep design exists and the code path is substantial, but broader real-device coverage is still needed | Parser/unit tests, local package output, platform notes, at least one realistic validation |
| `baseline` | Can parse authorized exports or produce valid CollectorX events, but not yet a full production collector | CLI, fixture, tests, event output |
| `lens-registered` | Investment lens exists and has routing rules, but does not yet have a mature classifier/backtest | Upstream dependency declared, boundaries documented |
| `placeholder` | YAML/config entry only; not a runnable collector | Scope and exclusions documented |

## Latest Productization Wave

`investor-source-collectors` now has a runnable lens baseline:

- Generic-channel lens sources default to investment evidence filtering.
- Events include classification metadata: confidence, reasons, matched terms,
  and matched security symbols.
- Upstream `collectorx.event.v1` JSON/JSONL inputs are supported.
- No-match inputs produce `no_investment_evidence_matched` gap events.
- Gap events are excluded from investor Wiki coverage.

This moves the shared lens engine to `baseline`, but it does not yet prove that
every upstream source collector is production-ready.

## P0 Status

| Need | Current implementation | Status | Gap to reach Tonghuashun/EastMoney standard |
| --- | --- | --- | --- |
| 微信投资对话 | `wechat` generic collector + `wechat-investment-dialogue` lens classifier | `baseline`; real-source validation blocked on current Mac by missing WeChat 4.x keys/SIP enabled | Prepare authorized WeChat keys, real WeChat lake validation, contact/group allowlists, entity/time matching, backtest against trade events |
| 本地研报/财报/PDF/Excel/Markdown/截图 | `filesystem-collector` metadata-only + `research-documents` lens classifier | `baseline`; macOS metadata real validation passed | Optional content extraction under explicit authorization, PDF/Excel fixtures, Windows/Linux path validation, false-positive review |
| 雪球投资活动 | `xueqiu-investor-activity` | `baseline` | Real Xueqiu login/export discovery, activity pagination, favorites/posts/comments/follows validation, rate/terms boundary |
| 支付宝/天天基金/蛋卷/且慢/银行理财 | `china-wealth-assets` | `baseline` | Per-platform export/UI adapters, product field mapping, real account validation, cross-platform import fixtures |
| 邮件研报 | `email` generic collector + `email-research` lens classifier | `baseline` | Real mailbox validation, expanded broker/IR sender classifiers, attachment refs, no full-body Wiki leakage |

## P1 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 飞书/钉钉/腾讯会议/企业微信会议纪要 | `feishu` exists; `dingtalk`, `wecom`, `meeting-artifacts` YAML; `meeting-minutes` lens classifier | `placeholder` / `baseline` | Build/port real dingtalk/wecom/tencent meeting collectors, unify minutes schema, validate meeting fixtures |
| Obsidian/Notion/有道云/印象笔记 | `notes-collector` + `investment-notes` lens classifier | `baseline` | Expand beyond draft Notion/Obsidian, add Youdao/Evernote adapters, validate investment-note classifier |
| 日历/任务/滴答清单 | `ticktick-cli`; `calendar` YAML; `task-calendar-investor` lens classifier | `baseline` / `placeholder` | Validate TickTick real account, build calendar collector, backtest investment task classifier |
| 公众号/微信收藏文章 | `wechat-favorites` YAML + `wechat-article-favorites` lens classifier | `placeholder` / `baseline` | Build WeChat favorites/public-account artifact collector, validate saved article refs |
| 华尔街见闻/财联社/格隆汇使用痕迹 | `financial-news-usage` YAML | `placeholder` | Build user activity adapters; do not crawl public news as personal evidence |

## P2 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 富途/老虎/盈透/港美股券商 | `hk-us-brokerage` YAML | `placeholder` | Build per-broker read-only adapters for assets, positions, executions, orders, cashflows |
| Choice/Wind/同花顺 iFinD 使用痕迹 | `pro-terminal-usage` YAML | `placeholder` | Build licensed-workflow collectors; do not mirror vendor databases |
| B站/微博/小红书投资内容痕迹 | `social-activity` YAML + `social-investment-influence` lens classifier | `placeholder` / `baseline` | Build user activity collectors and validate investment influence classifier |

## Deep-Designed Existing Collectors

| Collector | Current status |
| --- | --- |
| `eastmoney-portfolio` | `production-candidate` on current macOS machine for unlocked account read-only asset/holding/execution/order/fund-flow capture; Windows/Linux are code-level simulations or fallback paths |
| `ths-portfolio` | `deep-beta`; strong local package and GUI snapshot design exists, but needs broader real-device validation to claim production |
| `qq` | `deep-beta`; QQ NT discovery/decrypt-ready flow exists, current machine still has LLDB/passphrase capture limitation |

## Product Rule

For a collector to be marked `production-candidate`, it needs the same product
discipline as the Tonghuashun/EastMoney work:

1. Channel responsibility: what it collects and what it must never collect.
2. Authorization story: how the user grants access without exposing secrets.
3. Cross-platform plan: macOS, Windows, Linux status stated separately.
4. Event contract: emits `collectorx.event.v1` with stable IDs.
5. Evidence package: where applicable, emits `finclaw.investor_wiki_evidence.v1`.
6. Tests: parser/unit tests and at least one fixture without private data.
7. Real validation: run against a real account/device/export and record readiness.
8. Backtest: verify events can land in investor Wiki dimensions without hallucinating reasons.
