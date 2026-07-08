---
name: ticktick-cli
description: 使用 Python CLI 与 Dida365 Open API 交互以管理滴答清单任务/项目，适用于需要通过脚本或命令行调用滴答清单接口的场景（如项目/任务的查询、创建、更新、完成、删除）。
---

## 调用约定（AI 必读）

所有脚本一律用 **`python <绝对路径>`** 调用——跨平台都对，不会被 shell 路径/权限问题坑：

```bash
python <SKILL_DIR>/scripts/ticktick_cli.py --json project list
python <SKILL_DIR>/scripts/auth.py register <id> <sec>
python <SKILL_DIR>/scripts/auth.py authorize
python <SKILL_DIR>/scripts/ticktick_events.py collect --input <tasks.json-or-zip> --out-dir <out-dir>
```

`ticktick_events.py collect` 是 CollectorX/FinClaw 的只读事件导入路径：它
解析用户授权的 TickTick/Dida JSON/JSONL/ZIP 导出，输出 `lake/ticktick/events.jsonl`
和 `manifest.json`。manifest 会报告平台覆盖、任务字段覆盖、开始/截止/完成/
过期/循环/提醒统计、ZIP 来源审计、ZIP 跳过成员数量/原因、逐文件解析结果和
`task-calendar-investor` lens 边界。
generic task events 不能直接写投资 Wiki。

`<SKILL_DIR>` 通常：
- macOS / Linux: `~/.qclaw/skills/ticktick-cli` 或 `~/.claude/skills/ticktick-cli`
- Windows: `C:\Users\<用户>\.qclaw\skills\ticktick-cli`

❌ **不要**用以下姿势（容易踩坑）：
- `cd <skill_dir> && python ...` — PowerShell 的 `&&` 和 cmd 不一样，QClaw 的 exec 工具会拒绝复杂命令
- `./scripts/foo.py` — Windows 不识别 shebang，Mac 上要 `chmod +x` + 装 uv
- `uv run python ...` — 不是所有用户都装了 uv

## ⚠️ 首次授权 SOP（AI 必读）

**每台机器上的每个用户必须用自己的 dida365 OAuth 应用——不要共用别人的，否则后台数据会混在同一个应用名下。**

第一次跑这个 skill 前，token 文件 `~/.covo/ticktick.json` 不存在，CLI 会报"缺 token"。这时 AI 按下面流程**主动引导用户走完授权**——用户全程操作只 3 步：扫码登录 + 创建应用报凭证 + 浏览器点授权。

### AI 应该这样跟用户对话

**第 1 步**：先打开 dida365 开发者中心：
```bash
open https://developer.dida365.com/manage   # macOS
# Linux: xdg-open ...
# Windows: start ...
```
然后给用户清晰指示（**完整复述**给用户）：

> 我帮你打开了滴答开发者中心。你需要：
> 1. **扫码登录**你的滴答账号（必须是你**自己**的账号）
> 2. 点页面上的 **"创建应用"**，应用名随便填（比如 `ticktick-cli-我的名字`）
> 3. **redirect_uri 必须填**：`http://localhost:18921/callback` ⚠️ 一字不差
> 4. 创建完成后，把 **Client ID** 和 **Client Secret** 一起告诉我（直接说就行）

**第 2 步**：用户报了 client_id 和 secret 后，AI 调：
```bash
python3 scripts/auth.py register <client_id> <client_secret>
```

**第 3 步**：AI 调一条龙命令完成授权：
```bash
python3 scripts/auth.py authorize
```

`authorize` 命令会：
- 起本地 18921 server 监听 callback
- 自动打开浏览器到授权页
- 等用户在浏览器里点"授权"
- callback 自动落到本地 server → 自动换 token → 落到 `~/.covo/ticktick.json`
- 整个过程**用户只在浏览器里点一下"授权"按钮**，不需要复制粘贴任何 URL

**第 4 步**：提示用户把 token 加进 shell 环境变量（`authorize` 命令会打印好 export 命令）：
```bash
# 临时生效
eval "$(python3 -c 'import json; t=json.load(open("/Users/.../.covo/ticktick.json")); print(f"export TICKTICK_TOKEN={t[\"access_token\"]}")')"

# 永久：把 export TICKTICK_TOKEN=... 一行加到 ~/.zshrc 或 ~/.bashrc
```

### Token 过期了

dida365 token 大约半年过期。重新跑 `auth.py authorize` 即可（已注册的应用凭证还在，不需要重新 register）。

### 故障排查

- **`authorize` 卡住不结束**：用户没在 5 分钟内点"授权"，超时退出。重跑即可。
- **"No 'code' parameter"**：用户在授权页点了"拒绝"或者关了浏览器。让用户重跑并在新打开的页面点"授权"。
- **`status` 显示"应用未注册"**：还没跑 `auth.py register`，回到第 2 步。
- **手抄 callback URL 的备选路径**（`open` 失败时）：用户从浏览器复制整个跳转 URL（`http://localhost:18921/callback?code=xxx`），喂给 `auth.py callback "<URL>"`。

## ⚠️ 重要：更新任务必须写说明

当用户说"更新滴答"时，**不只是改状态**，必须同时写入说明（`--content`），记录做了什么、结果如何。

**完成任务的正确流程**：
1. 先用 `task update` 写入 content 说明（做了什么、结果、备注）
2. 再用 `task complete` 标记完成

**示例**（`<task_id>` 和 `<project_id>` 都从 `task list` 输出里取）：
```bash
# 先更新说明
python <SKILL_DIR>/scripts/ticktick_cli.py --json task update \
  --task-id <task_id> --project-id <task_的_projectId 字段> \
  --content "2026-04-06 已完成。新网续费boyuan-sh.com 1年，¥90，到期2027-04-28。发票待开。"
# 再完成
python <SKILL_DIR>/scripts/ticktick_cli.py --json task complete \
  --task-id <task_id> --project-id <task_的_projectId 字段>
```

**禁止**：直接 `task complete` 不写说明。

## ⚠️ 重要：收件箱（Inbox）

滴答清单的**收件箱**是用户最常用的任务存放位置，但它**不会出现在 `project list` 的返回结果中**。

- **收件箱 ID 是用户特定的**——形如 `inbox<user_id>`，每个滴答账号 user_id 不同。**不要在任何地方硬编码具体 inbox ID**
- `task list` 不指定 `--project-id` 时默认查当前 token 用户的收件箱（推荐用法）
- `task create` 不指定 `--project-id` 时默认创建到当前用户的收件箱
- 操作收件箱里的任务时，`--project-id` 从 `task list` 输出的 `projectId` 字段读，**不要猜**

**查找任务的正确流程**：
1. **先查收件箱**：`task list`（不传 `--project-id`，大部分日常任务在这里）
2. 如果收件箱没找到，再 `project list` + `project data` 逐个项目查

1) 常用子命令（覆盖日常场景）
- `project`
  - `list`（注意：不包含收件箱）
  - `get --project-id`
  - `data --project-id`
  - `create --name [--color --sort-order --view-mode --kind]`
  - `update --project-id [--name --color --sort-order --view-mode --kind]`
  - `delete --project-id`（危险，删除前需谨慎确认）
- `task`
  - `list [--project-id]`（默认收件箱）
  - `get --project-id --task-id`
  - `create --project-id --title [--content --desc --all-day --start-date --due-date --time-zone --reminder --repeat --priority --sort-order --item]`
  - `update --task-id --project-id [--title --content --desc --all-day --start-date --due-date --time-zone --reminder --repeat --priority --sort-order --item]`
  - `complete --project-id --task-id`
  - `delete --project-id --task-id`（危险，删除前需谨慎确认）
  - `create-receipt` **cufenshen action outbox 专用 · 不给人类用**
    - 参数：`--title --project-id --due-date? --content? --priority? --app --job-id --outbox-id --event-id --sink-id --idempotency-key`
    - 内部走 search-before-create（防重复创建）
    - stdout 永远是合法 ActionReceipt v1 JSON（含 schema/status/external_ref/error）
    - exit code 永远 0（包括 failed 路径 · daemon 看 receipt.status 不看 exit）
    - 详见 `cufenshen/dev-conventions.md §14` ticktick-cli sink skill 协议升级

2) 输出格式
- 所有调用统一在脚本后、子命令前加 `--json`（示例：`python <SKILL_DIR>/scripts/ticktick_cli.py --json task get --project-id ...`）

3) CollectorX 事件包
- `ticktick_cli.py` 是 API 操作工具；`ticktick_events.py` 是 CollectorX 事件转换入口。
- 用户授权的 `task list`/`project data` JSON 可以用下面命令转成标准事件：

```bash
python <SKILL_DIR>/scripts/ticktick_events.py collect \
  --input ~/Desktop/ticktick-tasks.json \
  --out-dir ~/Desktop/ticktick-collect
```

- 输出：`lake/ticktick/events.jsonl`、`manifest.json`、`SUMMARY.md`。
- 支持用户授权 JSON/JSONL/NDJSON 文件、目录或 ZIP 导出包。
- `manifest.platform_coverage` 会记录 `ticktick`/`dida365` 来源覆盖、缺失来源、事件数和 `real_account_validation`。
- 事件 raw 会过滤 password/cookie/token/session 等凭证字段。
- generic `ticktick` 事件只路由到 `internal.productivity.tasks`，不直接写投资 Wiki。
- 投资分身应把 `lake/ticktick/events.jsonl` 交给 `task-calendar-investor` lens，筛选交易计划、复盘提醒、研究任务。

4) 冷门参数/字段怎么查
- 运行 `python <SKILL_DIR>/scripts/ticktick_cli.py <command> --help` 查看该命令的参数
- 查看 `references/dida365-openapi.md` 了解完整参数、字段与响应结构

## Dida365 概念模型

- Project：项目，任务的容器，支持不同视图模式（list/kanban/timeline）。
  - 常用字段：
    - `name`（名称）
    - `color`（颜色）
    - `viewMode`（视图模式）
    - `kind`（类型）
    - `groupId`（分组）
    - `closed`（是否关闭）
    - `permission`（权限）
    - `sortOrder`（排序）
- Task：任务，隶属于某个 Project，可包含提醒、优先级、重复规则等。
  - 常用字段：
    - `title`（标题）
    - `content`（内容）
    - `desc`（描述/清单说明）
    - `tags`（标签）
    - `priority`（优先级）
    - `status`（状态）
    - `startDate`（开始时间）
    - `dueDate`（截止时间）
    - `timeZone`（时区）
    - `reminders`（提醒）
    - `repeatFlag`（重复规则）
    - `items`（子任务列表）
- ChecklistItem：任务下的子任务（清单项），用于拆分步骤。
  - 常用字段：
    - `title`（标题）
    - `status`（状态）
    - `startDate`（开始时间）
    - `completedTime`（完成时间）
    - `timeZone`（时区）
    - `sortOrder`（排序）
- Column：项目看板列，用于 kanban 视图的列信息。
  - 常用字段：
    - `name`（列名）
    - `sortOrder`（排序）
- ProjectData：项目详情聚合，包含项目本身、未完成任务与列信息。

## 资源

- [ticktick_cli.py](scripts/ticktick_cli.py)：主 CLI 入口，负责读取配置并发起 API 调用。
- [auth.py](scripts/auth.py)：首次授权辅助脚本，走 OAuth 拿 token 并落地到 `~/.covo/ticktick.json`。
- [dida365-openapi.md](references/dida365-openapi.md)：官方 Open API 文档快照，便于离线检索参数与字段。

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.7 | 2026-07-08 | CollectorX 事件转换增强：支持授权 ZIP 导出包，manifest 增加 `platform_coverage`，事件 raw 过滤凭证字段，并补充 ZIP 安全测试 |
| 0.1.6 | 2026-04-30 | 修浏览器自动打开在 Windows/客户端环境失败的问题：原本 `os.startfile(url)` 在 QClaw/Claude Code 的 subprocess 沙箱里偶发 silent 失败（找不到默认浏览器关联或没 GUI session），用户看到『终端没反应』。三层兜底：① 优先用 stdlib `webbrowser.open()`（内部针对 Windows 试 cmd start 比裸 os.startfile 兼容性好）；② 再显式 `cmd /c start "" <url>`（`""` 是窗口标题占位，不加会把 URL 当标题）；③ 都失败时把 URL 用分隔线包起来打印得**很**显眼，用户能 1 秒看到然后手动复制 |
| 0.1.5 | 2026-04-30 | 简化状态文件——0.1.4 拆成两个文件（`ticktick-app.json` + `ticktick.json`）是过度设计，合并到一个 `~/.covo/ticktick.json`，里面含 `oauth_app` + `access_token` 两个字段。`auth.py register` 写 oauth_app；`authorize` 写 access_token；互不破坏。状态文件从 2 个减到 1 个 |
| 0.1.4 | 2026-04-30 | 同模式"dcjanus 个人开发假设"清理（共 6 处）：① ticktick_cli.py 加 `~/.covo/ticktick.json` 文件 fallback——授权后 CLI 自动读 token，不再要用户分平台 setx/export；② auth.py 删掉 setx/export 平台分支输出，token 落盘后只提示一句"可以直接用了"；③ ticktick_cli.py "缺 token" 错误信息从老命令 `auth.py url` 改为新一条龙 `auth.py register + authorize`；④ SKILL.md 调用约定改成 `python <SKILL_DIR>/scripts/foo.py`，不再误导 AI 用 `./scripts/foo.py`（Windows 不识别 shebang）；⑤ 删除内嵌真 token 的 my_tasks.sh（dcjanus 留的便利脚本，0.1.0~0.1.3 暴露了校长 04-03 的滴答 token）；⑥ SKILL.md 删除硬编码的 inbox project-id `inbox1013277052`（这是某个特定用户的收件箱 ID，每个滴答账号 user_id 不同），改成"不传 --project-id 时 CLI 默认查当前 token 用户的收件箱" |
| 0.1.3 | 2026-04-30 | `--json` 输出修 fork 上游 dcjanus 的设计 bug：从 `rich.console.print_json` 改成 stdlib `print(json.dumps(...))`——rich 在 Windows cp936 下会写 ANSI 转义码 + 偶发 traceback 污染机读 JSON，让下游 AI 误以为崩了，开始绕过、写临时脚本、写文件中转，单次配置浪费 30 个工具调用；另外 ticktick_cli.py 顶部加 stdout/stderr utf-8 reconfigure（跟 auth.py 一致），中文 task title 不再乱码 |
| 0.1.2 | 2026-04-30 | Windows 友好性修复：① auth.py 写 token / app 文件强制 LF 行尾 + token 字段 strip，避免 Windows 写入 `\r` 让 Authorization header 多换行被服务端 401；② ticktick_cli.py 读 `TICKTICK_TOKEN` 环境变量时也 strip 防御；③ register/authorize 阶段自动 `pip install typer httpx pydantic rich`，不再让用户跑 `task list` 时才发现缺依赖；④ stdout/stderr 切 utf-8、去掉 emoji，避免 Windows cp936 终端 UnicodeEncodeError |
| 0.1.1 | 2026-04-30 | 数据隔离修复 + 一键授权：剥离打包的 client_id/secret（每个用户必须用自己的 OAuth 应用，避免后台数据混在一个应用下）；新增 `auth.py authorize` 一条龙命令——起本地 18921 server + 自动开浏览器 + 抓 callback + 换 token + 落盘，用户不再需要手抄回调 URL |
| 0.1.0 | 2026-04-29 | 首次发布到 covo-hub。OAuth 走 localhost:18921 伪 callback + 人肉粘 code，token 落 `~/.covo/ticktick.json` |
