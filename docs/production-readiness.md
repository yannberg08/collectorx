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
| 本地研报/财报/PDF/Excel/Markdown/截图 | `filesystem-collector` metadata-only + `research-documents` lens classifier/content reader | `baseline`; macOS metadata and explicit content extraction validation passed; default-root code paths for macOS/Windows/Linux are fixture-tested | Broader private PDF/XLSX/DOCX samples, extraction-scope UX, false-positive review, real Windows/Linux device validation |
| 雪球投资活动 | `xueqiu-watchlist` + `xueqiu-investor-activity` | `baseline`; watchlist source now emits standard lake packages; activity collector covers nested Snowball-like payloads, raw sanitization, and SoulMirror sync; neither is a real account adapter | Real Xueqiu login/export discovery, activity pagination, watchlist/favorites/posts/comments/follows validation, rate/terms boundary |
| 支付宝/天天基金/蛋卷/且慢/银行理财 | `china-wealth-assets` | `baseline`; normalized local export/package path covers Excel/JSON/CSV, platform inference, numeric asset fields, platform coverage manifest, raw sanitization, and SoulMirror sync; no real account export found yet | Per-platform export/UI adapters, real account validation, complete account-boundary proof |
| 邮件研报 | `email` generic collector + `email-research` lens classifier | `baseline`; local EML/MBOX/JSON/CSV import package now works with attachment refs and no full body by default; real mailbox validation still blocked by missing registered mailbox | Register mailbox, real mailbox validation, expanded broker/IR sender classifiers, attachment refs backtest, no full-body Wiki leakage |

## P1 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 飞书/钉钉/腾讯会议/企业微信会议纪要 | `meeting-artifacts` local/platform-export/ZIP collector + `collaboration-exports` for `dingtalk`/`wecom` + `feishu` exists; `meeting-minutes` lens classifier | `baseline`; macOS local meeting-file validation passed; HTML/CSV/JSON/ZIP platform-export fixture validation passed; meeting manifest reports platform coverage; DingTalk/WeCom collaboration-export fixtures passed; platform account APIs pending | Build/port real Feishu/DingTalk/WeCom/Tencent Meeting account adapters, validate real authorized exports, participant identity normalization, false-positive review |
| Obsidian/Notion/有道云/印象笔记 | `notes-collector` event package + authorized export/ZIP import + `investment-notes` lens classifier | `baseline`; macOS Obsidian-style real validation passed; Youdao/Evernote/Markdown/HTML/JSON/ENEX/ZIP fixtures pass; manifest reports observed/missing P1 note platforms | Validate real Notion/Youdao/Evernote account exports or APIs, user allowlists, false-positive review, Windows/Linux vault path validation |
| 日历/任务/滴答清单 | `ticktick-cli` API tool + `ticktick_events.py`; `calendar-collector`; `task-calendar-investor` lens classifier | `baseline`; TickTick/Dida JSON/ZIP export and generic calendar ICS/JSON/CSV/TSV/ZIP paths exist; manifests report task/calendar platform coverage; real TickTick/API calendar validation blocked by missing account tokens/exports | Complete TickTick OAuth validation, validate real calendar exports/accounts, recurring tasks/timezones, backtest investment task classifier |
| 公众号/微信收藏文章 | `wechat-favorites` local file/folder/ZIP collector + `wechat-article-favorites` lens classifier | `baseline`; macOS saved-article validation passed; JSON/HTML/ZIP fixtures cover favorite/read/share/saved-file actions and action coverage manifest; real WeChat favorites adapter pending | Discover/validate real WeChat favorites and public-account stores, account/tag allowlists, action metadata, Windows/Linux path validation |
| 华尔街见闻/财联社/格隆汇使用痕迹 | `financial-news-usage` local usage/browser-history/ZIP collector | `baseline`; JSON/CSV/HTML/TXT/ZIP fixture validation passed; Chromium browser-history validation passed; manifest reports platform/action coverage; real app/account adapters pending | Discover/validate CLS/WallstreetCN/Gelonghui app caches, account APIs, real subscription/alert stores, Safari/Windows/Linux browser-history paths; do not crawl public news as personal evidence |

## P2 Status

| Need | Current implementation | Status | Gap |
| --- | --- | --- | --- |
| 富途/老虎/盈透/港美股券商 | `hk-us-brokerage` local read-only CSV/JSON/Excel/ZIP export collector | `baseline`; fixture validation passed; multi-section JSON, Excel, ZIP, broker coverage, trade-surface coverage, and field coverage validation passed; no real local export found yet | Validate real Futu/Tiger/IBKR exports or read-only screens, broker-specific column maps, multi-currency assets, margin, tax, dividends, FX, and Windows/macOS/Linux paths |
| Choice/Wind/同花顺 iFinD 使用痕迹 | `pro-terminal-usage` local CSV/JSON/Excel/HTML/TXT/LOG/ZIP workflow collector | `baseline`; fixture validation passed; multi-section JSON, Excel, ZIP, terminal coverage, activity coverage, and workflow-field coverage validation passed; real licensed terminal exports pending | Validate real Wind/Choice/iFinD/Bloomberg authorized workflow exports, user workspace paths, watchlists, searches, downloads, templates, datasets, fields, function codes, and license-safe boundaries |
| B站/微博/小红书投资内容痕迹 | `social-activity` local JSON/CSV/Excel activity collector + `social-investment-influence` lens classifier | `baseline`; fixture validation passed; multi-section JSON and Excel validation passed; strict local saved-record validation is partial; real account/export adapters pending | Validate real Weibo/Bilibili/Xiaohongshu exports, watch/favorite/like/follow/comment surfaces, platform allowlists, creator allowlists, engagement fields, and weak-evidence backtest |

## Deep-Designed Existing Collectors

| Collector | Current status |
| --- | --- |
| `eastmoney-portfolio` | `production-candidate` on current macOS machine for unlocked account read-only asset/holding/execution/order/fund-flow capture; Windows/Linux are code-level simulations or fallback paths |
| `ths-portfolio` | `deep-beta`; strong local package and GUI snapshot design exists, but needs broader real-device validation to claim production |
| `ths-watchlist` | `baseline`; authorized local export collector for same-channel watchlist/attention-universe evidence; not a strong trade, holding, order, or fund-flow collector |
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
