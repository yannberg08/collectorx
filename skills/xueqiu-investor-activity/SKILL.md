---
name: xueqiu-investor-activity
description: 雪球投资者活动垂直采集器。采集用户授权的雪球自选、关注用户、关注组合、个人发帖、评论、收藏、用户自己的组合调仓，以及用户授权复制的 Chromium/Safari 浏览器历史中的雪球访问痕迹，输出 CollectorX 事件和 FinClaw 投资分身证据包。用于能力圈、关注池、信息源、人脉网络和投资观点表达；不采全站舆情，不把雪球组合或浏览历史当券商强交易事实。
---

# 雪球投资者活动采集器

雪球是投资垂直通道。它对投资分身有价值，但价值不是“强交易事实”，而是关注池、信息网络、观点表达和组合模拟行为。

## 采什么

- 自选股、关注股票、关注行业。
- 关注用户、关注组合、关注话题。
- 用户自己的发帖、评论、收藏。
- 用户自己的雪球组合和调仓记录。
- 用户授权复制的 Chromium/Safari 浏览器历史中，仅 `xueqiu.com` 域名相关的访问记录。
- 浏览器历史访问元数据：页面 URL、标题、访问时间、来源浏览器、visit_count、typed_count、transition_type。
- 活动覆盖证明：自选、关注用户、关注组合、组合活动、评论、收藏、发帖、保存页是否齐全。
- 分页完整性摘要：是否看到分页标记、HAR 分页端点、是否被 limit 截断。

## 不采什么

- 不采全站舆情。
- 不采他人完整时间线。
- 不采券商成交、委托、资金流水。
- 不读取 cookie、token、密码或设备指纹。
- 不把浏览器历史推断为完整雪球账号活动；浏览器历史只作为阅读/关注痕迹。

## 使用

```bash
python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/xueqiu-export.json \
  --out-dir ~/Desktop/xueqiu-investor-collect \
  --sync-soulmirror

python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/雪球自选.csv \
  --event-export ~/Desktop/xueqiu-events.jsonl

python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/xueqiu-network.har \
  --out-dir ~/Desktop/xueqiu-investor-collect

python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Desktop/authorized-browser-history-copy/History \
  --out-dir ~/Desktop/xueqiu-investor-collect

# 可选：按用户授权范围收窄雪球活动
python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/xueqiu-export.json \
  --out-dir ~/Desktop/xueqiu-investor-collect \
  --allow-activity post \
  --allow-symbol SH600519 \
  --deny-keyword 私人
```

支持 JSON/JSONL/CSV/TSV/XLSX/XLSM/HTML/TXT/Markdown/HAR/ZIP，以及用户授权复制出来的
Chromium `History` / Safari `History.db` / `.sqlite` / `.sqlite3` / `.db` 浏览器历史文件。
解析器会归一化常见雪球/Snowball
结构，如 `statuses`、`list`、`data.items`、`stocks`、`cubes` 和
`rebalancing_histories`，并剔除 cookie、token、password 等凭据类字段。

HAR 是用户已登录雪球后、明确授权选择的浏览器网络导出文件。采集器只读取
`xueqiu.com` 域名的响应体，记录接口路径、状态、行号和审计计数；请求头、
Cookie、Authorization 和 URL 查询串不会写入事件、manifest 或 Wiki evidence。

浏览器历史文件必须是用户主动复制给采集器的只读副本。采集器只读取 `xueqiu.com`
及其子域名的访问记录，过滤其他域名；写入 `source_app`、`visit_count`、
`typed_count`、`transition_type` 和 `browser_history_boundary` 审计字段。浏览器历史
只能证明用户访问过哪些雪球页面，不能证明用户完整的关注、收藏、发帖或交易行为。

ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员。manifest 会明确
标注 `xueqiu_is_broker_trade_source: false`，雪球只作为关注网络、观点表达和
模拟组合证据，不能替代券商强交易事实。manifest 还会记录输入文件数、扩展名覆盖、
ZIP 成员/跳过成员、HAR 网络包覆盖、浏览器历史覆盖、跳过原因、解析记录数、分页标记字段、
字段覆盖、来源面覆盖、活动覆盖证明和分页完整性摘要。
`collect` 支持 activity、source_surface、source_app、domain、symbol、author、
keyword 的 allow/deny 授权范围过滤。`manifest.collection_audit.xueqiu_activity_scope_policy`
会记录配置、候选事件数、保留数、过滤数、原因计数和 filtered-all 状态；
`manifest.activity_boundary_proof.authorization_scope_boundary` 给 FinClaw 检查本轮
雪球活动授权边界。该策略只限定用户授权范围，不判断投资相关性。

`manifest.activity_boundary_proof` 会区分：

- `broad_partial_activity_boundary`：本次授权输入覆盖全部预期活动面。
- `medium_partial_activity_boundary`：覆盖多个核心活动面，但仍有缺口。
- `narrow_partial_activity_boundary`：只覆盖少数活动面。
- `no_authorized_activity_evidence`：没有可用授权活动输入。

`pagination_completeness.complete_timeline_claimed` 始终为 `false`。没有真实账号分页验证前，
采集器不会宣称已经完整采集雪球时间线。

没有授权输入时，采集器只输出缺口状态，不伪造数据。
