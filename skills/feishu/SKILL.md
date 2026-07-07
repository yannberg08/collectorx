---
name: feishu
description: 飞书完整工具：读取文档、创建文档、搜索文档、发送消息、上传文件、管理云空间、录音豆转写。当用户提到"飞书"、"飞书文档"、"飞书纪要"、"会议纪要"、"读取飞书"、"传到飞书"、"发飞书"、"飞书消息"、"录音豆"、"录音转写"、"拉录音"时触发。
version: 0.1.4
---

## 调用约定（AI 必读）

所有脚本一律用 **`python <绝对路径>`** 调用——跨平台都对，不会被 shell 路径/权限问题坑：

```bash
python <SKILL_DIR>/scripts/feishu_api.py search "MES"
python <SKILL_DIR>/scripts/auth.py register <app_id> <app_secret>
python <SKILL_DIR>/scripts/auth.py authorize
```

`<SKILL_DIR>` 通常：
- macOS / Linux: `~/.qclaw/skills/feishu` 或 `~/.claude/skills/feishu`
- Windows: `C:\Users\<用户>\.qclaw\skills\feishu`

❌ **不要**用以下姿势（容易踩坑）：
- `cd <skill_dir> && python ...` — PowerShell 的 `&&` 和 cmd 不一样
- `./scripts/foo.py` — Windows 不识别 shebang
- 老版的 `feishu_api.py auth <code>` 手抄 code 流程也不要再用，改 `auth.py authorize`

## ⚠️ 首次授权 SOP（AI 必读）

**每台机器上的每个用户必须用自己的飞书自建应用——不要共用别人的，否则后台数据会混在同一个应用名下。**

第一次跑这个 skill 前，token 文件 `~/.cufin/skills-config/feishu.json` 不存在，CLI 会报"缺凭证"。**用户只需要扫一次码登录飞书**（在 chrome-auto profile 里）——剩下的 AI 用 Chrome CDP 全部搞定，**包括 OAuth 授权页那个『授权』按钮也是自动点的**（建应用 → 配回调 → 勾权限 → 发版 → navigate 到 OAuth 授权 URL → 自动点击『授权』→ 收 callback → 换 token → 落盘）。

### AI 应该这样跟用户对话

**一条龙命令**（推荐，正常情况就这一条）：

```bash
python <SKILL_DIR>/scripts/auth.py setup
```

⚠️ **AI 调用方注意：setup 是个长流程（60–120 秒），不要因为终端短时间没新输出就重跑！** 重跑会启动第二个 setup 进程跟第一个抢 Chrome / 飞书后台，互相打断导致权限只勾上一半（已踩坑）。具体：

- 等到看到 `[setup] 凭证已落 .../feishu.json` 才算 Chrome 自动化阶段完成
- 后续还有 OAuth 自动点授权 + 拿 token，再 30 秒
- 总超时设到 **3 分钟**（180s）以上；中间没刷屏不代表卡死，是在等飞书页面渲染/React state 同步
- 真要停只用 Ctrl+C 一次，**不要先 Ctrl+C 再起一次新 setup**

执行流程（AI 跑完这一条命令就完事了）：
1. 自动启动 Chrome（独立 profile `~/.cufin/skills-config/chrome-auto`，端口 9222，不影响用户主 Chrome）
2. **首次需要用户在弹出的 Chrome 里手机扫码登录飞书**——告诉用户"请在弹出的 Chrome 窗口里用手机飞书扫码登录"
3. 自动建一个新企业自建应用（默认名 `fs-cli-<hostname末21字>`，截到 32 字防超限）
4. 自动配回调地址 `http://localhost:18921/callback`
5. 自动勾选 scope（默认 10 个：文档/聊天/录音豆/云盘——已覆盖文档读写、聊天列表、录音豆 list+get 全文转写；可用 `--scopes` 自定义）+ 申请开通
6. 自动创建版本 + 发布上线
7. 抓出 app_id / app_secret，落 `~/.cufin/skills-config/feishu.json`
8. 启动本地 18921 server，CDP navigate 到飞书授权页 + **自动点击『授权』按钮**
9. 拿 user_token + refresh_token，落盘完成

**用户全程只需 1 个动作：扫码登录飞书**（且 chrome-auto profile 第二次跑时登录态自动复用，连这步都省了）。

#### 想用已有的飞书应用？

```bash
python <SKILL_DIR>/scripts/auth.py setup --app-id cli_xxx --app-secret <secret>
```

AI 会跳过新建步骤，但仍会自动配回调/勾权限/发版（如果还没配好）。

#### setup 失败的回退方案

如果 setup 卡在某一步（飞书后台 UI 改了、网络问题、CDP 连不上），AI 走分步手动流程：
```bash
python <SKILL_DIR>/scripts/auth.py register <app_id> <app_secret>  # 用户在飞书后台手动建好应用，把 app_id/secret 给 AI
python <SKILL_DIR>/scripts/auth.py authorize                       # 起本地 server + 开浏览器授权
```
`register` 输出会清晰列出"用户需要在飞书后台完成的 3 件事"清单（含可复制的 redirect URI 和 scope 列表）。

### Token 过期与续期

飞书 token 设计：
- `user_token`：2 小时有效——`feishu_api` 调用前会自动检查，过期自动 refresh
- `refresh_token`：30 天滑动窗口——**每次刷新会换新的 + 重置 30 天**

所以**只要每月用一次这个 skill，refresh_token 永远不会过期**。30 天没用过才需要重新走 `auth.py setup`（或 `authorize`）。

### 故障排查

- **`setup` 启动 Chrome 失败**：会自动探测 Chrome / Edge / Brave / Chromium（Edge 在 Windows 几乎预装），都没装才报错。装一个或设 `CUFIN_CHROME_BIN` 指向已装的 Chromium 系浏览器路径。
- **`setup` 卡在"等用户登录"**：用户没在 5 分钟内扫码。重跑即可（profile 已保留）。
- **`setup` 报"飞书后台 UI 找不到按钮"**：飞书改 UI 了，CDP 选择器失效。走回退方案（`register` + `authorize` 手动）。
- **`authorize` 卡住不结束**：用户没在 5 分钟内点"授权"。重跑即可。
- **`status` 显示"应用未注册"**：还没跑 `setup` 或 `register`。
- **「No 'code' parameter」**：用户在授权页点了"拒绝"或者关了浏览器。让用户重跑并在新打开的页面点"授权"。
- **「应用不存在/已下架」**：自建应用没发布版本上线，重跑 `setup`（自动重新发版）或在飞书后台手动发版。

#### 环境变量

| 名 | 默认 | 用途 |
|----|------|------|
| `CUFIN_CHROME_PROFILE` | `~/.cufin/skills-config/chrome-auto` | 自动化 Chrome 的 profile 目录，多个 skill 共享登录态 |
| `CUFIN_CHROME_PORT` | `9222` | Chrome 调试端口 |
| `CUFIN_CHROME_BIN` | 自动探测 | Chrome 可执行路径 |

## 1) 常用子命令

### 文档读取
- `feishu_api.py doc <doc_token>` — 读取飞书文档全文
- `feishu_api.py search <keyword>` — 全局搜索文档
- `feishu_api.py chats` — 列出聊天列表
- `feishu_api.py links --chat <名称>` — 通过 Chrome CDP 提取聊天里的文档链接（需 Chrome 调试模式 9222）

### 文档创建
- `feishu_api.py create-doc <标题> [--file <md_file>] [--folder <token>]` — 用 Markdown 创建飞书文档

### 消息 / 文件
- `feishu_api.py send <chat_id> <content> [--type text|post|interactive|file]`
- `feishu_api.py upload <file_path> [--type opus|mp4|pdf|doc|xls|ppt|stream]`

### 云盘
- `feishu_api.py folders [--token <folder_token>]` — 列云空间文件夹

### 录音豆（会议转写）
- `feishu_api.py recordings list [--limit N]` — 列出最近录音豆产物
- `feishu_api.py recordings get <doc_token>` — 获取某条录音的转写全文
- `feishu_api.py recordings latest` — 拉取最新一条录音的转写

录音豆识别用严格标题模式（『文字记录：xxx 2026年4月24日』『智能纪要：...』『soundcore Work_MM-DD HH:MM』），不会混入人工写的会议纪要。

## 2) 状态文件

`~/.cufin/skills-config/feishu.json` 一个文件搞定：
```json
{
  "oauth_app": {"app_id": "cli_xxx", "app_secret": "xxx"},
  "user_token": "u-xxx",
  "refresh_token": "ur-xxx",
  "expires_at": 1777xxxxxx
}
```

`auth.py register` 写 `oauth_app`；`auth.py authorize` 写 token；`feishu_api.py` 调用时自动 refresh。互不破坏。

老路径 `~/.feishu_tokens.json` 第一次跑会自动迁移到新路径。

## 3) 资源

- [feishu_api.py](scripts/feishu_api.py)：主 CLI 入口，所有业务命令
- [auth.py](scripts/auth.py)：首次授权辅助脚本，OAuth 一条龙

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.5 | 2026-05-24 | **状态目录定为 `~/.cufin/skills-config/`**（萃分身英文代号 cufin）。token / chrome-auto profile 全部在此。env var 主名 `CUFIN_CHROME_PROFILE` / `CUFIN_CHROME_PORT` / `CUFIN_CHROME_BIN`。改动文件：SKILL.md / auth.py / chrome_setup.py / feishu_api.py 共 4 处路径常量 + env var 处理 + 注释/文档更新 |
| 0.1.4 | 2026-05-01 | **修『AI 调用方等不及重跑导致权限只勾上一半』root cause**：setup 是个长流程（60–120 秒），QClaw / Codex / 其他 AI runner 默认子进程超时太短（30–60s）等不到 `凭证已落 .../feishu.json` 就以为失败重跑，第二个 setup 进程跟第一个抢 Chrome / 飞书后台 SPA，互相打断 _enable_scopes 的 click 流程，结果 8 个 scope 只勾上一部分（甚至 0 个），OAuth 拿到 token 但调 API 全 Unauthorized。SKILL.md 顶部加显眼提示："不要因为终端短时间没新输出就重跑，总超时设到 3 分钟以上"。同时加防御：每次 click 后 sleep 250ms 让 React state 同步、勾完后 sleep 2s 再点确认开通（dump_state 诊断 log 也保留作生产调试用） |
| 0.1.3 | 2026-05-01 | Windows 浏览器探测加 3 层 fallback，覆盖绿色版/便携版 Chrome：① `winreg` 查 App Paths（标准安装注册）；② 固定标准路径列表；③ **递归扫 `%LOCALAPPDATA%\Google\Chrome\` 等根目录**——校长机器实测 Chrome 109 装在 `\Bin\chrome.exe`（不是标准的 `\Application\`）且没注册到 App Paths/Uninstall/PATH，旧探测全 miss。探测顺序按浏览器分组（Chrome 全部探测方式 → Edge 全部 → Brave 全部）而不是按方式分组，让 Chrome 优先级压过 Edge（Win 上 Edge 预装率高，否则会先命中 Edge）。同步修 0.1.2 残留的 `_grab_credentials` bug——用精确 `.auth-info__secret` + `.secret-code__code` selector 抓 secret，不再正则匹配 textContent（避免误抓到 Verification Token 等其他 32 字符串导致 OAuth 报『app secret invalid』10014） |
| 0.1.2 | 2026-04-30 | **`auth.py setup` 一条龙自动化**：用 Chrome CDP 在飞书开放平台自动建企业自建应用、配回调地址 `http://localhost:18921/callback`、勾选 10 个 scope（文档/聊天/录音豆/云盘——只含无数据权限范围要求的 scope，保证能自动发版；妙记转写/AI 产物 scope 需用户在飞书后台手动配数据权限范围）、创建版本+发布上线，再自动跑 OAuth 拿 token。用户全程只需扫码登录 + 点一下授权（共 2 个动作），不用手动找页面、不用搜权限名。配套 `auth.py delete <app_id>` 用 CDP 删测试应用。setup 失败时回退到 `register` + `authorize` 分步手动流程；`register` 输出现在带应用详情页 URL + 必做清单（redirect URI/scope 列表可复制）。**实测全链路 50s**（CREATE 阶段，含建应用/配回调/勾 10 scope/发版/抓 secret）：踩过 3 个坑——① 默认应用名 `feishu-cli-{hostname}` 会撞飞书 32 字限制（mac 长机器名 +`.local` 一拼就 42 字），改用 `fs-cli-{hostname末21字}` 并 `[:32]` 截断；② 飞书 React checkbox 不接受 JS 批量 `cb.click()`——第一个 click 后框架会把后续 `.checked` 全标 true 但实际状态没变，必须真实 mouse event 逐个点；③ 抽屉里 11 个 checkbox 第 1 个是"批量勾选"——点它 1 次就把 10 个 scope 全勾完，原代码盲点 11 次浪费 20s+ |
| 0.1.1 | 2026-04-30 | 修浏览器自动打开在 Windows/客户端环境失败的问题（同 ticktick-cli 0.1.6）：原本 `os.startfile(url)` 在 QClaw/Claude Code 的 subprocess 沙箱里偶发 silent 失败（找不到默认浏览器关联或没 GUI session），用户看到『终端没反应』。三层兜底：① 优先用 stdlib `webbrowser.open()`（内部针对 Windows 试 cmd start 比裸 os.startfile 兼容性好）；② 再显式 `cmd /c start "" <url>`（`""` 是窗口标题占位，不加会把 URL 当标题）；③ 都失败时把 URL 用分隔线包起来打印得**很**显眼，用户能 1 秒看到然后手动复制 |
| 0.1.0 | 2026-04-30 | 首次发布到 hub。基于 `~/.claude/skills/feishu/`（4-24 创建的"飞书完整版"）重构。**核心修复**：refresh_token 端点 bug——旧版 refresh 时打到 `/authen/v1/oidc/access_token`（这是"用 code 换 token"的端点，需要 code 参数）永远失败，user_token 一过期就要重新 OAuth；改为正确的 `/authen/v1/oidc/refresh_access_token`，30 天滑窗。同时按 ticktick-cli 0.1.5 标准化：① 拆出 `auth.py`（register + authorize 一条龙）；② 剥离硬编码的 `cli_a945e69f503a1cb0` / app_secret，每用户必须用自己的应用；③ 状态文件搬到 hub 共享路径（合并 oauth_app + token），老 `~/.feishu_tokens.json` 自动迁移；④ stdout/stderr utf-8 reconfigure，Windows 中文/cp936 不再乱码；⑤ requests 缺时自动 pip install；⑥ SKILL.md 调用约定改成 `python <SKILL_DIR>/scripts/foo.py` |
