# FinClaw 采集器 skill 自带声明清单（下载即接入）

下载一个 collectorx skill 后，FinClaw 通过 skill 自带的一份声明清单（一般名为
`.collectorx.json`）读取该采集器的「意图 / 模式声明」，按统一逻辑自动接入并蒸馏优化。

## 文件位置

`skills/<slug>/.collectorx.json`

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `slug` | string | ✓ | skill 的名字（与目录名一致） |
| `version` | string | ✓ | 语义化版本（FinClaw 用它判断是否更新） |
| `status` | string |  | 质量状态（baseline+audit 等） |
| `description` | string |  | 一句话说明 |
| `collector` | object | ✓ | 采集器声明（见下） |
| `intent_prompt` | string |  | 采集意图 prompt（蒸馏阶段用，针对投资者） |

### `collector` 声明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✓ | 采集器唯一 id（可与 slug 不同，如 skill=wechat-export → id=wechat） |
| `display_name` | string | ✓ | 展示名（中文，面向投资者） |
| `kind` | string | ✓ | `builtin` 预置 / `external` 用户自装 / `a2a` |
| `mode` | string | ✓ | `snapshot` 全量 diff / `incremental` 增量游标 |
| `driver` | string | ✓ | `filesystem` 内置机械扫描 / `skill` 技能驱动(LLM) / `a2a` |
| `time_field` | string | ✓ | 时间字段（`mtime` / `time` / `due` 等） |
| `refresh_interval` | string |  | 采集频率（`30m` / `6h` / `24h`） |
| `armed` | bool | ✓ | 用户同意后才跑 |
| `category` | string |  | `generic` / `vertical` / `lenses` |
| `skill` | string |  | 执行 skill（缺省用 `slug`） |
| `skill_hub_slug` | string |  | hub 安装 slug |
| `description` | string |  | 采集器说明 |

## FinClaw 侧逻辑（下载即接入）

- 安装（`POST /api/collector/install`）时：先 `git pull` 拉取最新注册表，复制 skill 到
  `~/.agents/skills/<skill>`，读取 `.collectorx.json`，用 `collector.id` 注册采集器，并把
  `mode` / `time_field` / `armed` / `intent_prompt` 并入运行时目录。
- 运行时扫描（`loadInstalledCollectorCatalogs`）：凡声明了 `collector.id` 且属于
  FinClaw 内置 skill 采集器（如 wechat/qq）或已安装/配置的采集器，自动注册进目录，
  使其出现在前端并能按统一逻辑（`collectSkill`）执行。
- 同 id 时「下载清单」覆盖「内置目录」，保证拉到的是最新优化逻辑（mode/意图）。

## 示例（wechat-export）

```json
{
  "slug": "wechat-export",
  "version": "0.11.4",
  "collector": {
    "id": "wechat",
    "display_name": "微信聊天记录",
    "kind": "external",
    "mode": "incremental",
    "driver": "skill",
    "time_field": "time",
    "refresh_interval": "30m",
    "armed": false,
    "category": "generic",
    "skill": "wechat-export"
  },
  "intent_prompt": "你是 FinClaw 投资分身【微信采集 · 蒸馏筛选阶段】……"
}
```
