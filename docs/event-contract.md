# CollectorX Event Contract v1

CollectorX 的采集器不直接写 Wiki。采集器只负责把用户授权的数据变成稳定、可追溯、可过滤的事件。事件进入 lake 后，由 distill app 决定如何萃取、归档到通用 Wiki 或垂直 Wiki。

## 边界

CollectorX 采集的是用户自己的数据，默认服务于“更懂这个用户”的分身。

应该进入 CollectorX 的数据：

- 用户自己的聊天、邮件、日程、任务、笔记、本地文件
- 用户自己的交易记录、持仓、自选、投研笔记、复盘
- 用户与他人的投资讨论、调研纪要、协作记录

不应该作为分身采集器直接进入的外部公共数据：

- 行情、公告、财报、新闻、研报、宏观、行业数据库

这些外部数据可以由 FinClaw 的研究工具或应用调用，但不要混入用户个人 Wiki 的原始证据池。

## 标准事件

Schema 文件：`schemas/collectorx-event.schema.json`

最小事件：

```json
{
  "schema": "collectorx.event.v1",
  "id": "ths-portfolio:2024-01-15:600519:buy:1800.00:100",
  "collector": "ths-portfolio",
  "source": "同花顺交割单 CSV",
  "owner_scope": "personal",
  "kind": "trade",
  "time": "2024-01-15T09:30:00+08:00",
  "collected_at": "2026-07-07T15:00:00+08:00",
  "data": {},
  "raw_ref": {},
  "privacy": {
    "sensitive": true,
    "local_only": true,
    "contains": ["trade", "money"]
  }
}
```

## 字段说明

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema` | 是 | 固定为 `collectorx.event.v1` |
| `id` | 是 | 稳定事件 ID，不应每次采集变化 |
| `collector` | 是 | 采集器 ID，如 `wechat`、`ths-portfolio` |
| `source` | 是 | 给人和 Agent 看的证据来源 |
| `owner_scope` | 是 | `personal` / `workspace` / `public` / `unknown` |
| `kind` | 是 | `message`、`trade`、`holding`、`watchlist` 等 |
| `time` | 是 | 源事件时间；源头无时间时可为 `null` |
| `collected_at` | 是 | 本次采集时间 |
| `data` | 是 | 标准化内容，不同 kind 有不同结构 |
| `raw_ref` | 是 | 原始证据指针，不强迫下游 prompt 暴露原文 |
| `privacy` | 是 | 本地、敏感、包含内容类别 |
| `wiki_targets` | 否 | 给蒸馏 app 的建议路由，不是强制写入 |

## kind 约定

### `message`

用于微信、QQ、飞书、钉钉、A2A 等对话。

`data` 建议字段：

- `chat`
- `sender`
- `sender_is_owner`
- `text`
- `message_type`

### `trade`

用于交割单、成交记录。

`data` 建议字段：

- `account`
- `symbol`
- `name`
- `side`
- `price`
- `quantity`
- `amount`
- `fee`
- `tax`

### `holding`

用于持仓快照。

`data` 建议字段：

- `account`
- `symbol`
- `name`
- `quantity`
- `market_value`
- `cost`
- `unrealized_pnl`

### `watchlist`

用于自选股、关注列表。

`data` 建议字段：

- `symbol`
- `name`
- `industry`
- `note`
- `group`

### `note`

用于 Obsidian、Notion、有道云等笔记。

`data` 建议字段：

- `title`
- `path`
- `content`
- `tags`

## 隐私原则

1. 默认 `local_only: true`。
2. 明文凭证不能出现在 `data`、日志、测试 fixture、README。
3. 大段聊天原文和邮件正文应尽量只保留 raw pointer，由 distill app 按需读取。
4. `wiki_targets` 只是建议，最终由 app 的 distill/organize prompt 决定。
5. 公共市场数据不要伪装成用户个人数据。

## 与 SoulMirror / FinClaw 的关系

CollectorX 只做“采集与标准化事件”。在 SoulMirror 式闭环里，它的位置是：

```text
collector skill
  -> CollectorX Event
  -> lake
  -> distill app
  -> general wiki / investor wiki
  -> FinClaw Agent and applications
```

这保证采集器可以开源、复用，而 FinClaw 的投资分身逻辑仍然保留在 app、schema、评分和产品层。
