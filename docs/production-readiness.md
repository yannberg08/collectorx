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
| 本地研报/财报/PDF/Excel/Markdown/截图 | `filesystem-collector` metadata-only + `research-documents` lens classifier/content reader | `baseline`; macOS metadata and explicit content extraction validation passed | Windows/Linux path validation, broader private PDF/XLSX/DOCX samples, extraction-scope UX, false-positive review |
| 雪球投资活动 | `xueqiu-investor-activity` | `baseline`; normalized local export/package path covers nested Snowball-like payloads, raw sanitization, and SoulMirror sync; not a real account adapter | Real Xueqiu login/export discovery, activity pagination, favorites/posts/comments/follows validation, rate/terms boundary |
| 支付宝/天天基金/蛋卷/且慢/银行理财 | `china-wealth-assets` | `baseline`; normalized local export/package path covers Excel/JSON/CSV, platform inference, numeric asset fields, raw sanitization, and SoulMirror sync; no real account export found yet | Per-platform export/UI adapters, real account validation, cross-platform import fixtures, complete account-boundary proof |
| 邮件研报 | `email` generic collector + `email-research` lens classifier | `baseline`; real mailbox validation blocked by missing registered mailbox | Register mailbox, real mailbox validation, expanded broker/IR sender classifiers, attachment refs, no full-body Wiki leakage |

## P1 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 飞书/钉钉/腾讯会议/企业微信会议纪要 | `meeting-artifacts` local/platform-export collector + `feishu` exists; `dingtalk`, `wecom` YAML; `meeting-minutes` lens classifier | `baseline`; macOS local meeting-file validation passed; HTML/CSV/JSON platform-export fixture validation passed; platform account APIs pending | Build/port real Feishu/DingTalk/WeCom/Tencent Meeting account adapters, validate real authorized exports, participant identity normalization, false-positive review |
| Obsidian/Notion/有道云/印象笔记 | `notes-collector` event package + authorized export import + `investment-notes` lens classifier | `baseline`; macOS Obsidian-style real validation passed; Youdao/Evernote/Markdown/HTML/JSON/ENEX import fixtures pass | Validate real Notion/Youdao/Evernote account exports or APIs, user allowlists, false-positive review, Windows/Linux vault path validation |
| 日历/任务/滴答清单 | `ticktick-cli` API tool + `ticktick_events.py`; `calendar-collector`; `task-calendar-investor` lens classifier | `baseline`; TickTick export and generic calendar export paths exist; real TickTick/API calendar validation blocked by missing account tokens/exports | Complete TickTick OAuth validation, validate real calendar exports/accounts, recurring tasks/timezones, backtest investment task classifier |
| 公众号/微信收藏文章 | `wechat-favorites` local file collector + `wechat-article-favorites` lens classifier | `baseline`; macOS saved-article validation passed; real WeChat favorites adapter pending | Discover/validate real WeChat favorites and public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation |
| 华尔街见闻/财联社/格隆汇使用痕迹 | `financial-news-usage` local usage collector | `baseline`; fixture validation passed; real app/account adapters pending | Discover/validate CLS/WallstreetCN/Gelonghui authorized exports, browser histories, account APIs, and alert/subscription stores; do not crawl public news as personal evidence |

## P2 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 富途/老虎/盈透/港美股券商 | `hk-us-brokerage` local read-only export collector | `baseline`; fixture validation passed; no real local export found yet | Validate real Futu/Tiger/IBKR exports or read-only screens, per-broker column maps, multi-currency assets, dividends, FX, and Windows/macOS/Linux paths |
| Choice/Wind/同花顺 iFinD 使用痕迹 | `pro-terminal-usage` local workflow collector | `baseline`; fixture validation passed; real licensed terminal exports pending | Validate real Wind/Choice/iFinD/Bloomberg authorized workflow exports, user workspace paths, watchlists, searches, downloads, templates, and license-safe boundaries |
| B站/微博/小红书投资内容痕迹 | `social-activity` local activity collector + `social-investment-influence` lens classifier | `baseline`; fixture validation passed; strict local saved-record validation is partial; real account/export adapters pending | Validate real Weibo/Bilibili/Xiaohongshu exports, watch/favorite/like/follow/comment surfaces, platform allowlists, creator allowlists, and weak-evidence policy |

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
