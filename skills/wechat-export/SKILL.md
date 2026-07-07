---
name: wechat-export
description: 导出和查询微信聊天记录。当用户说"查微信"、"导出聊天记录"、"破解微信"、"聊天记录"、"查标签"、"按标签查联系人"时使用此 skill。
version: 0.11.0
---

# 微信聊天记录导出工具

## ⚠️ 下游 Agent 必读（v0.5.0+）

**禁止自行写 SQL 查询标签/分组/群成员/联系人！**

请只使用 skill 提供的 CLI 命令（见下文"参数说明"+"标签查询"章节）。
如果遇到命令覆盖不到的场景（例如你需要"按标签批量查消息"/"按地区过滤联系人"等），
**请反馈给 skill 官方（@Kevin），不要自己 workaround。**

偷跑 SQL 的风险：
- 不同微信版本 schema 会变（Mac 3.x / Mac 4.x / Windows 4.x 不一样）
- 加密密钥读取方式平台不同，错误处理很容易漏
- 直接 SQL 绕开 skill 的统一错误降级，导致 "Mac 上查标签返回空 = 看起来正常 = 其实数据根本没有" 的误判

## 快速判断：这是什么环境？

用户说"查微信"时，**先判断平台和版本**，再选择对应方案：

### 判断方法

```
1. 用户在 Mac 上？
   → 方案 A：Mac 微信 4.x（**自 v0.9.1 起仅支持 4.x，3.x 已下线**）
     · Mac 4.x：SQLCipher4（page 4096 / kdf 256000 / HMAC-SHA512），
       数据在 Documents/xwechat_files/<wxid>/db_storage/message/message_N.db
       （Msg_<md5> 表，schema 同 Windows 4.x）
     · 若检测到 3.x（旧数据目录）：脚本会**明确报错，提示把微信升级到 4.x**
       后重新提取密钥；不再走 3.x 解密路径。
   ⚠️ 标签功能：Mac 4.x 与 Windows 4.x 同源，本地有标签（走 Windows 标签逻辑）

2. 用户在 Windows 上？检查以下特征：
   进程名是 Weixin.exe  → 微信 4.x → 方案 B
   数据目录含 xwechat_files → 微信 4.x → 方案 B
   进程名是 WeChat.exe  → 微信 3.x → 不在本 skill 范围
   ⚠️ 不要用注册表版本号判断，可能是旧的残留！

3. 用户在 Linux 上？（原生微信 /opt/wechat/wechat，微信 4.x）→ 方案 C
   数据目录 ~/xwechat_files/<wxid>/db_storage，SQLCipher4（同 Mac/Win 4.x）。
   key 从 /proc/<pid>/mem 扫明文 x'<96hex>'（需 root），无需 lldb/gdb hook。
```

---

## 方案 A：Mac 微信 4.x

**本 skill 只支持微信 4.x，3.x 不支持。** `wechat_query.py` 会探测本机数据目录，
发现 4.x（`db_storage/`）即走 SQLCipher4 解密/查询；若找不到 4.x 数据，会**明确报错
提示升级到 4.x**。

Mac 4.x 与 Windows 4.x 同源：SQLCipher4（page 4096 / kdf 256000 / HMAC-SHA512），
**每个库一把独立 enc_key**（不是共用一把），密钥用 `wechat_extract_mac.py`（lldb hook
`CCKeyDerivationPBKDF`）提取；消息库 `message/message_N.db`（`Msg_<md5>` 表 + `Name2Id`），
联系人库 `contact/contact.db`，本地有标签。

### 数据库位置

**Mac 4.x**：
```
~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/<wxid>/db_storage/
```
- `message/message_N.db` - 聊天消息（加密，`Msg_<md5>` 表 + `Name2Id`）
- `contact/contact.db` - 联系人 + 群成员（加密）
- `session/*.db` - 会话（加密）

> 脚本解密 4.x 时会把需要的库解密到 `data/decrypted_cache/<hash>/` 明文缓存
> （按 mtime 增量，源库没变就复用），再复用 Windows 4.x 的查询逻辑读取。
> 明文缓存只在本机、不入 git。

### 第一步：获取数据库密钥

#### 检查是否已有密钥

首先检查环境变量 `WECHAT_KEY` 是否已设置。如果有，跳到第二步。

#### 获取新密钥（需要关闭 SIP）

用一键提取器 `wechat_extract_mac.py`（下方），无需手动 lldb。跑前先 `csrutil status`
确认 SIP 已 `disabled`；若已启用，重启进恢复模式（开机按住 `Command + R`）跑
`csrutil disable` 后再重启。

##### Mac 4.x（SQLCipher4）—— 用一键提取器

微信 4.x（实测 4.1.11）**不再把 key 以明文串留在内存**（库头 salt 在内存出现 0 次，
旧的 `x'<96hex>'` 内存扫描彻底失效），也**不用** SQLCipher 标准的 `sqlite3_key`。
正解是 hook 系统的密钥派生函数 `CCKeyDerivationPBKDF`，在微信打开每个库、派生
SQLCipher HMAC 子密钥（`rounds==2`）那一刻，其 `password` 参数就是**该库的 enc_key**。
这套已封装成一键脚本，无需手动 lldb。

> **⚠️ 跑之前必须满足三个前提，缺一个都提不出 key：**
> 1. **SIP 已关闭**（`csrutil status` 显示 `disabled`）——lldb 要附加到微信这种
>    hardened-runtime 进程，SIP 开着会被系统直接拒绝。关 SIP 需重启进恢复模式跑
>    `csrutil disable`。
> 2. **必须 `sudo`（root）**——脚本开头就检查，非 root 直接报 `[ERROR] 需要 root` 退出。
> 3. **微信已登录**——脚本会优雅重启一次微信来捕获启动时的密钥派生；账号若没保持
>    登录，重启后会弹扫码登录，就 hook 不到派生了。

```bash
# 前提：SIP 已关 + root + 微信已登录；脚本会短暂优雅重启一次微信以捕获启动派生
# ⚠️ 提取器要用 sudo，用户通常不在 skill 目录下跑——必须用【完整绝对路径】，别用相对路径
sudo python3 <本 skill 目录>/scripts/wechat_extract_mac.py
```

> **⚠️ 给用户的破解命令一律用完整绝对路径**。SKILL.md 顶部会带「Base directory for
> this skill: …」，把 `<本 skill 目录>` 替换成那个真实绝对路径再发给用户；相对路径
> （`scripts/wechat_extract_mac.py`）在用户的 home 目录下会 `no such file` 失败。
> 日常查询的 `wechat_query.py` 同理，发给用户时也给绝对路径。

它会：① 找到 `db_storage` ② lldb `--waitfor` 挂上 hook 并重启微信 ③ 截获所有
`rounds==2` 的 32 字节 enc_key ④ 用「每个库第 1 页 HMAC-SHA512 校验」把 key 对回
具体的库 ⑤ 存 `data/all_keys.json`（`{相对路径: enc_key_hex}`，chmod 600）。
之后 `wechat_query.py` 自动读取，**日常查询不再需要 sudo**。

> **原理速记**：SQLCipher4 每打开一个库做两次 PBKDF2 —— 主密钥派生
> （rounds=256000）+ HMAC 子密钥派生（rounds=2，password=该库 enc_key）。
> 我们只取后者。key 是 **每库一把独立的**（36 个库 36 把），不是共用一把。
> 参考：`L1en2407/wechat-decrypt`、`cocohahaha/wechat-decrypt-macos`、
> 高金博客《用 AI+Frida 打通微信 4.1.8 macOS 数据库密钥提取》。

7. **完成后恢复 SIP**（推荐）：重启进恢复模式，执行 `csrutil enable`。

### 第二步：查询聊天记录

使用 `scripts/wechat_query.py` 脚本查询聊天记录。v0.4.0 起同时支持**微信通话记录**
（语音 / 视频通话），用于判断"是否已经通电话沟通过"。
v0.5.0 起新增**标签查询**（Mac 4.x 与 Windows 4.x 同源，两平台都可本地查标签，详见"标签查询"章节）。

```bash
# 查看最新 N 条消息（含通话记录）
python3 scripts/wechat_query.py --recent 10

# 搜索包含关键词的消息
python3 scripts/wechat_query.py --search "关键词"

# 查看特定联系人/群的消息（v0.5.0+ 结果会附 tags 字段）
python3 scripts/wechat_query.py --contact "联系人名称" --limit 50

# 导出主人相关的紧凑清洗 txt：一条消息一行，XML/系统卡片压成摘要；无可读标题的未知卡片会跳过，默认过滤潜水群
python3 scripts/wechat_query.py --export ~/Desktop/wechat_export.txt

# 如需给人看所有会话（包括潜水群），显式开启全量导出
python3 scripts/wechat_query.py --export ~/Desktop/wechat_all.txt --export-all

# 如需排查数据库原始内容，才使用旧版裸导出（隐含全量）
python3 scripts/wechat_query.py --export ~/Desktop/wechat_raw.txt --raw-export

# 给 Agent 建账 / 自动模式 / 下游分析使用；默认紧凑 JSON，避免行数和空白膨胀
python3 scripts/wechat_query.py --collect --days 3 --active-group-days 3 --out /tmp/wechat-3d.json

# 人工排查 collect 内容时才加 --pretty
python3 scripts/wechat_query.py --collect --days 3 --pretty --out /tmp/wechat-3d.pretty.json

# 列出所有联系人和群（默认前 100 条按字母序，前面多是符号开头的杂项）
python3 scripts/wechat_query.py --list-contacts

# 找特定关键词的联系人/群（推荐 — 4 万联系人裸列毫无意义，必须配 --filter）
python3 scripts/wechat_query.py --list-contacts --filter "黑客松"
```

#### 参数说明

| 参数 | 说明 |
|------|------|
| `--recent N` | 显示最新 N 条消息 |
| `--search "关键词"` | 搜索包含关键词的消息 |
| `--contact "名称"` | 筛选特定联系人或群的消息（v0.5.0+ 输出带 tags 字段）|
| `--limit N` | 限制返回结果数量 |
| `--export 路径` | 导出主人相关的紧凑清洗 txt：一条消息一行，XML/系统卡片/视频/表情压成短摘要；无可读标题的未知卡片会跳过，默认过滤潜水群，默认每条最多 500 字 |
| `--export-all` | 配合 `--export` 使用，显式导出所有会话（包括主人未参与的群刷屏）|
| `--raw-export` | 配合 `--export` 使用，保留旧版原始多行格式和未清洗 XML，仅用于排查数据库原文；隐含全量导出 |
| `--export-max-chars N` | 配合 `--export` 紧凑模式，限制单条消息长度；默认 500，设 0 不截断 |
| `--list-contacts` | 列出所有联系人和群（默认前 100，按字母序）|
| `--filter "关键词"` | 配合 `--list-contacts`，按名字模糊匹配过滤（不区分大小写）|
| `--days N` | 只查询最近 N 天的消息 |
| `--new-contacts N` | 查看近 N 天新增的联系人（通过首条消息时间判断；Mac + Windows 通用） |
| **`--list-tags`** | **v0.5.0+** 列出所有联系人标签（Mac 4.x + Windows 4.x，两平台同源，实测可用） |
| **`--tag "NAME"`** | **v0.5.0+** 查询带该标签的联系人；可配合 `--search`/`--days` 查消息 |
| **`--contact-tags "NAME"`** | **v0.5.0+** 查看某个联系人身上挂的所有标签 |
| **`--collect`** | **采集模式** 查询 + 过滤 + 格式化输出 CUFin JSON，一条命令搞定；默认紧凑 JSON |
| **`--after "YYYY-MM-DD HH:MM:SS"`** | 配合 `--collect`，只采该时刻起的消息 |
| **`--out FILE`** | 配合 `--collect`，写到文件（默认打到 stdout） |
| **`--pretty`** | 配合 `--collect`，人工排查时输出缩进 JSON；默认不要加，避免行数和 token 膨胀 |
| **`--exclude "n1,n2"`** | **v0.7.0+** 配合 `--collect`/`--export`，黑名单（任何 chat 名匹配则跳过） |
| **`--include-groups "g1,g2"`** | **v0.7.0+** 配合 `--collect`/`--export`，群聊白名单（默认不采群） |
| **`--active-group-days N`** | **v0.7.0+** 配合 `--collect`/`--export`，自动把"最近 N 天我有发言的群"加进白名单（`--collect` 默认 30；`--export --days N` 默认跟随 N；设为 0 关闭） |

> 密钥从环境变量 `WECHAT_KEY` 读取，无需通过参数传入。

#### 采集模式过滤策略（v0.7.0+）

`--collect` 模式按以下规则筛选要采的消息：

```
私聊：默认全收，--exclude 列表里的剔除
群聊：默认【不收】，除非满足以下任一：
       - 在 --include-groups 显式白名单
       - 最近 --active-group-days 天我在群里发过言（默认 30 天）
```

意图：私人对话信息密度高、自动全收；群聊噪音多、只保留我真正参与的。

Agent 建账、自动模式、下游摘要和长期记忆蒸馏默认使用 `--collect`,不要用 `--export`。`--collect` 默认写紧凑 JSON,每条记录包含 `id`、`source` 和 `data{chat,sender,time,text}`,减少无意义换行和空白；只有人工排查文件结构时才加 `--pretty`。`--export` 是给人看的留档格式；默认同样按主人相关性过滤并清洗 XML。只有明确要看全部会话时才加 `--export-all`；只有数据库排查才使用 `--raw-export`。

调用示例：

```bash
# 只采近 7 天的私聊 + 我活跃过的群（默认 30 天阈值）
python3 wechat_query.py --collect --days 7 --out /tmp/out.json

# 只采纯私聊（关闭群自动白名单）
python3 wechat_query.py --collect --days 7 --active-group-days 0 --out ...

# 私聊（剔除广告号） + 指定 2 个群
python3 wechat_query.py --collect --days 7 \
  --exclude "环球小姐,知产企服朱老师" \
  --include-groups "LCC的Agent分会筹备群,萃分身项目沟通群" \
  --out ...
```

#### 通话记录输出格式（v0.4.0+）

微信 VoIP 通话（语音 / 视频）的 `messageType=50` 行会被解析成结构化的 `(call)` 条目：

```
[2026-04-16 17:52:46] (call)
  dm: 航驱IT—董涛
  type: 语音通话
  duration: 1小时13分4秒
  status: 已接通
  initiator: sent   # 我发起
```

关键字段：

| 字段 | 含义 |
|------|------|
| `type` | `语音通话` 或 `视频通话` |
| `duration` | 接通时显示通话时长（`Xh Ym Zs`）；未接通时显示原因（如 `我已取消` / `对方已取消` / `无人接听` / `已拒绝`） |
| `status` | 机读状态的中文展示（`已接通`/`已取消`/`未接听`/...） |
| `initiator` | `sent` = 我方发起，`recv` = 对方发起 |

用途：Agent 整理待办时可以判断"我是否已经和某人通过电话"。例如：

```bash
# 查询陆高杰最近 2 天的消息（文本 + 通话）
python3 scripts/wechat_query.py --contact "陆高杰" --days 2 --limit 50

# 搜索"视频通话"/"语音通话"关键词，快速找到最近通话
python3 scripts/wechat_query.py --search "语音通话" --days 7
```

> ⚠️ 微信只记录在微信 App 里发起的 VoIP 通话；手机通话（打电话号码）不会出现在这里。

### Mac 依赖安装

```bash
pip3 install sqlcipher3
```

---

## 方案 B：Windows 微信 4.x

### 关键特征（判断依据）

- 进程名：`Weixin.exe`（不是 `WeChat.exe`）
- 数据目录：`C:\Users\<用户名>\xwechat_files\<wxid>\db_storage\`
- ⚠️ **不要用注册表版本号判断！** 可能是旧版残留

### 前置条件

```bash
pip install pycryptodome zstandard
```

微信必须已**登录状态**（进程在跑且登录了账号）——只启动进程不登录不行。

### 第一步：提取密钥（仅首次需要，已提取会自动跳过）

```bash
python scripts/wechat_extract_windows.py
```

脚本会自动：检测微信版本 → 查找数据目录 → 检查 `data/all_keys.json` 是否已有密钥。

- **已有密钥**：直接跳过，提示用 `wechat_query.py` 查询
- **没有密钥**：扫描进程内存提取，保存到 `data/all_keys.json`

> 密钥同一大版本（4.x系列）内不会变，提取一次即可复用。**提取时微信必须处于已登录状态**（只启动不登录，内存里没有密钥）。

### 第二步：查询聊天记录（直接读实时数据库）

```bash
# 查看最新10条消息（自动检测数据目录和密钥）
python scripts/wechat_query.py --recent 10
```

> Windows上无需手动指定 `--db-dir`，脚本会自动：
> 1. 读取 `AppData\Roaming\Tencent\xwechat\config\*.ini` 获取自定义数据路径
> 2. 扫描 `xwechat_files` 下的所有 wxid 目录（支持多账号）
> 3. 自动检测 `data/all_keys.json` 密钥文件
> 4. 直接读取实时加密数据库并在内存中解密

也可以手动指定路径：
```bash
python scripts/wechat_query.py --db-dir "C:\Users\<用户名>\xwechat_files\<wxid>\db_storage" --recent 10
```

```bash
# 搜索消息
python scripts/wechat_query.py --db-dir <db_storage路径> --search "关键词"

# 查看特定联系人/群的消息
python scripts/wechat_query.py --db-dir <db_storage路径> --contact "联系人名称" --limit 50

# 列出所有联系人和群
python scripts/wechat_query.py --db-dir <db_storage路径> --list-contacts

# 只查询最近N天
python scripts/wechat_query.py --db-dir <db_storage路径> --days 7 --recent 20

# 导出消息到文件
python scripts/wechat_query.py --db-dir <db_storage路径> --export output.txt
```

### 注意事项

1. **微信必须已登录**：密钥提取需要微信进程在跑**且已登录账号**（只启动不登录没用）
2. **密钥可复用**：同一大版本（4.x系列）内密钥通用，保存 `all_keys.json` 即可
3. **查询无需微信在线**：只要密钥已提取，查询可以离线进行

---

## 方案 C：Linux 微信 4.x（v0.11.0+）

Linux 原生微信（`/opt/wechat/wechat`，实测 4.1.1.7）与 Mac/Windows 4.x **同源**：
SQLCipher4（page 4096 / kdf 256000 / HMAC-SHA512），每库一把独立 32 字节 enc_key，
消息库 `db_storage/message/message_0.db`（`Msg_<md5>` 表）、联系人库 `contact/contact.db`。

**与 Mac 的关键差异**：Linux 微信 4.x 内存里**仍保留明文 key**，WCDB 缓存形态是
`x'<64hex enc_key><32hex salt>'`（与 Windows 一致），所以直接 regex 扫 `/proc/<pid>/mem`
就能拿到，**不需要 lldb/gdb hook**（比 Mac 简单）。

### 数据库位置
```
~/xwechat_files/<wxid>/db_storage/
```
（实测微信启动参数 `--wechat-files-path=$HOME/xwechat_files`；兼容 `~/.xwechat/xwechat_files`。）

### 第一步：提取密钥（需 root）
读 `/proc/<pid>/mem` 需要 root / `CAP_SYS_PTRACE`，且**微信必须已登录并在运行**。
```bash
# 前提：微信已登录在跑；用 sudo（脚本开头检查 root）
sudo python3 <本 skill 目录>/scripts/wechat_extract_linux.py --keys-only
```
它会：① 自动找 db_storage（或 `--db-dir` 指定）② `collect_db_files` 收各库 salt
③ 扫微信主进程（`exe==/opt/wechat/wechat`）内存的 `x'<96hex>'`、按 salt 反查对回库
④ 用第 1 页 HMAC-SHA512 校验 ⑤ 存 `data/all_keys.json`（`{相对路径: {enc_key, salt}}`，
与 Windows 同构）。

> **⚠️ sudo 属主坑**：sudo 跑完 `data/`、`logs/` 会是 root 属主，普通用户随后跑查询会
> `Permission denied`。跑完补一句 `sudo chown -R $USER: <本 skill 目录>`。
> 另注：sudo 下 `~` 变 `/root`，自动找目录会失效——建议显式 `--db-dir`。

### 第二步：查询（无需 root）
查询侧的 `WindowsV4Query` 路径**平台无关**（纯 Python AES 逐页解密），Linux 上带
`--db-dir` 直接复用，与方案 B 完全同套命令：
```bash
python3 <本 skill 目录>/scripts/wechat_query.py \
  --db-dir ~/xwechat_files/<wxid>/db_storage --recent 10
# 采集/搜索/联系人/标签等所有参数同方案 A/B（见「参数说明」「标签查询」）
```
依赖：解密用 `Crypto.Cipher.AES`（`pycrypto 2.6.1` 或 `pycryptodome` 皆可）。

---

## 标签查询（v0.5.0+）

**目的**：让下游 Agent 能按联系人标签（微信"标签"功能设置的分组，例如"客户"/"供应商"/"同事"等）查询联系人或消息，而不用自己写 SQL。

### 命令速览

```bash
# 1. 列出所有标签（名字 + 人数）
python scripts/wechat_query.py --list-tags

# 2. 查询某个标签下的全部联系人
python scripts/wechat_query.py --tag "客户"

# 3. 查询某个标签下联系人的最近消息
python scripts/wechat_query.py --tag "客户" --days 7 --limit 20
python scripts/wechat_query.py --tag "客户" --search "报价"

# 4. 查看某个联系人身上挂的所有标签
python scripts/wechat_query.py --contact-tags "陆高杰"

# 5. --contact 查消息时，结果会自动附带 tags 字段
python scripts/wechat_query.py --contact "陆高杰" --limit 10
# 输出头部：Contact tags: ['客户', '航驱']
```

### 输出示例（Mac 4.x / Windows 4.x 一致）

**`--list-tags`**:
```
==================================================
Tags (4)
==================================================
  [     1] 供应商  (12 contacts)
  [     2] 同事    (8 contacts)
  [     3] 客户    (35 contacts)
  [     4] 家人    (3 contacts)
```

**`--tag "客户"`**（列出联系人）：
```
==================================================
Contacts with tag: 客户  (35)
==================================================
  张三  (wxid: wxid_abc123def456...)  tags: [客户, 航驱]
  李四  (wxid: wxid_ghi789jkl012...)  tags: [客户]
  ...
```

**`--tag "客户" --days 7`**（查消息）：
```
============================================================
Messages from 35 contacts with tag '客户' (20 messages)
============================================================

[2026-04-22 21:00:31] (recv)
  dm: 张三
  content: 大师 方便电话不
...
```

**`--contact-tags "张三"`**:
```
==================================================
Tags of contact: 张三
==================================================
  - 客户
  - 航驱
```

### ⚠️ 已知局限

1. **只支持微信 4.x（3.x 不支持）**
   - Mac 4.x 与 Windows 4.x 同源，本地都有标签数据，`--list-tags` / `--tag` / `--contact-tags` 均可用（实测 Mac 4.1.11 返回 95 个标签）。
   - 若 4.x 上跑标签命令返回空，多半是微信里本就没设标签；确认设了仍查不到，反馈 @Kevin。

2. **Windows 4.x schema 自适配**
   - skill 同时支持 camelCase（`ContactLabel(LabelID, LabelName)` + `Contact.LabelIDList`）和 snake_case（`contact_label(label_id, label_name)` + `contact.label_id_list`）两种 schema
   - 如果刘学林那边实际 schema 与以上两种都不匹配，请把 `--list-tags` 的输出发给 @Kevin，我们会加新适配

3. **标签查询不使用 SQL 查询消息**
   - `--tag X` 只用标签数据找出成员列表，然后对每个成员走 `query_messages`
   - 所以 `--search`/`--days`/`--limit` 等都能组合用

### 对下游 Agent 的明确指令（再次强调）

```
❌ 禁止：
   - 下游 Agent 自己写 SQL 查询标签/分组/群成员
   - 下游 Agent 自己读 contact.db 找 LabelIDList 做 split

✅ 正确：
   - 用 --list-tags 查看有哪些标签
   - 用 --tag "<名称>" 查标签下的联系人或消息
   - 用 --contact-tags "<姓名>" 查某人的标签
   - 用 --contact "<姓名>" 附带看 tags 字段

🆘 命令覆盖不到？
   反馈给 skill 官方（@Kevin），不要自己 workaround。
```

---

## 加密原理（仅供参考）

| 平台 | 版本 | 加密方式 | 密钥 |
|------|------|---------|------|
| **Mac** | 4.x | SQLCipher4，**每库一把独立密钥** | 每个 .db 有自己的 32 字节 enc_key（同 Windows 4.x） |
| **Windows** | 4.x | per-DB AES-256-CBC，每库独立密钥 | 每个 .db 有自己的 32 字节密钥 |
| **Linux** | 4.x | SQLCipher4（同上），每库独立密钥 | 内存留明文 `x'<96hex>'`，`/proc/mem` 扫（同 Windows，无需 hook） |

> Mac 4.x 与 Windows 4.x 同源，**每个库一把独立 key**（不是共用一把）。加密都是
> SQLCipher4 家族；差别只在 Mac 用 sqlcipher3 库读、Windows 用手动 AES 逐页解。

Mac 4.x / Windows 4.x SQLCipher4 参数：
```python
PRAGMA cipher_page_size = 4096
PRAGMA kdf_iter = 256000
PRAGMA cipher_hmac_algorithm = HMAC_SHA512
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512
```

---

## 通用注意事项

1. **安全性**：Mac 获取密钥需关闭 SIP，获取后建议重新开启
2. **隐私**：聊天记录包含隐私信息，请妥善保管导出的文件
3. **密钥保存**：密钥不会改变（除非重新安装微信），可以保存下来下次使用

## 文件清单

| 文件 | 用途 |
|------|------|
| `scripts/wechat_query.py` | Mac + Windows 微信聊天记录查询工具（支持两个平台，含标签查询） |
| `scripts/wechat_extract_windows.py` | Windows 微信密钥提取 + 解密工具（4.x per-DB AES，内存扫描 key） |
| `scripts/wechat_extract_mac.py` | Mac 4.x 密钥提取（lldb hook `CCKeyDerivationPBKDF`，产出 `data/all_keys.json`） |
| `scripts/wechat_extract_linux.py` | Linux 4.x 密钥提取（扫 `/proc/<pid>/mem` 的 `x'<96hex>'` + salt 反查，产出 `data/all_keys.json`） |

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.11.0 | 2026-07-05 | **新增 Linux 微信 4.x 支持（方案 C）**。① 新增 `scripts/wechat_extract_linux.py`：从运行中 Linux 原生微信（`/opt/wechat/wechat`，实测 4.1.1.7）的 `/proc/<pid>/mem` 扫明文 key `x'<96hex>'`、按 salt 反查对回库、第 1 页 HMAC-SHA512 校验，产出与 Windows 同构的 `data/all_keys.json`。Linux 微信内存**仍留明文 key**（不像 Mac 4.1.11 已不留），故 regex 即可、**无需 lldb/gdb hook**。② 解密算法 `decrypt_page`/`decrypt_database` 从 `wechat_extract_windows.py` 抽进 `wexport/keycrypto.py`（三平台共用，AES 延迟 import，不解密的调用方无需装 Crypto）。③ `wexport/detect.py` 加 `_auto_find_linux_db_dir`（`~/xwechat_files/<wxid>/db_storage`，兼容 `~/.xwechat/xwechat_files`）。④ 查询侧零改动：`WindowsV4Query` 平台无关，Linux 带 `--db-dir` 直接复用。真机（CentOS 宿主上的 Ubuntu 20.04 VM，微信 4.1.1.7）端到端验证：提取 16/16 库 key → 解密 8 库 → 加载 10816 联系人 → 查出实时消息；`pycrypto 2.6.1` 即可解密。`py_compile` + 本地 import/argparse 通过。 |
| 0.10.1 | 2026-07-05 | **Mac 提取器：跳过 `.factory` 备份库 + 综合诊断输出**。① `collect_db_files` 遍历时跳过 WCDB 的 `.factory` 备份/修复目录（活库的历史快照副本，微信启动不打开、不派生 key，扫进来会让密钥匹配数虚少一个，如实测的 36/37）——过滤后提取与查询两侧都干净（36/36）。② `wechat_extract_mac.py` 校验后**逐个打印未匹配到 key 的库**（路径 + 大小 + 未中原因：不足一页 / 明文库 / 本轮未派生），不再让人对着"36/37"干猜；`info['page1']` 取值改 `.get` 防越界。③ **新增综合诊断文件 `/tmp/wx_kd_diag.txt`**（成功/失败都写）：系统（macOS 版本+build / Darwin / 机型 / 芯片 / SIP / `CCKeyDerivationPBKDF` 是否可解析）、微信 App（`CFBundleShortVersionString`+`CFBundleVersion` / 是否 App Store 来源 / bundle 与二进制构建时间）、抓取（候选数 / 断点命中次数与 rounds·pwl 分布 / HMAC 校验数）——用于两台机器失败时快速对比定位（微信构建号差异 / 函数是否被调用 / 系统层是否有变）。lldb hook 同时记录每次命中的 rounds/pwl 到 `wx_kd_hits.txt`。真机自测：诊断输出正确、`.factory` 过滤 36/36、`py_compile` 通过。 |
| 0.10.0 | 2026-07-03 | **破解层去重：抽公用进 `wexport/` 并接线 + 密钥文件统一命名**。① 两个提取器（`wechat_extract_mac.py` / `wechat_extract_windows.py`）此前各存一份逐字重复的 SQLCipher4 逻辑（`derive_mac_key` / `verify_key_page1` / `collect_db_files` + 目录发现），现全部抽进**新模块 `wexport/keycrypto.py`**（常量 + 派生/校验/收库 + 密钥文件命名解析）；目录发现改共用已有的 `wexport/detect.py`（`_find_mac4_db_storage` / `_auto_find_windows_db_dir`）。`wexport/` 之前是建好没接线的孤立包，现三个脚本（两提取器 + `wechat_query.py`）都真正 import 它。`collect_db_files` 统一成一份 `(db_files, salt_to_dbs)`，同时给 Windows(salt) 和 Mac(page1) 用；Windows `decrypt_database` 的内联 HMAC 校验也换成共享 `verify_key_page1`。② **密钥文件统一命名**：`mac_all_keys.json` / `windows_all_keys.json` → 都叫 **`data/all_keys.json`**（一台机器只跑一个平台不冲突，格式各自，reader 按平台分派各读各的）；新增 `resolve_keys_file()` 优先读统一名、兜底旧平台名，老装机零迁移仍可用。③ 新增 `tests/test_keycrypto.py`（5 例：派生确定性 / page1 HMAC 校验收放 / collect 收 salt+page1 / 命名解析优先级）。真机复测：Mac 用 36 把已存 key 复验 36/36 对回各库；Windows(.22 微信 4.x) 查询 + 提取器 exist-check 走统一名/兜底名均通；单测全过。 |
| 0.9.2 | 2026-07-03 | **文档校准 + 提取器 chown 收尾**。① `wechat_extract_mac.py` sudo 跑完递归 `chown data/` 回真实用户（`SUDO_UID/GID`），免得留 root 属主文件、普通用户之后改不动。② SKILL.md / `--help` 全量对齐「只支持 4.x，3.x 不支持」：提取器前置条件（SIP 已关 / root / 微信已登录）提到醒目位置；删除过时的 3.x 手动 lldb 取密钥流程与 3.x 加密参数表；修正标签查询口径——Mac 4.x 与 Windows 4.x 同源、两平台都能本地查标签（实测 Mac 4.1.11 返回 96 个标签），去掉「仅 Windows / Mac 待验证」旧说法。真机复测：`--recent`/`--search`/`--contact`/`--list-contacts`/`--tag`/`--contact-tags`/`--new-contacts`/`--collect`/`--export` 九类查询全通，单测 9/9 + multi_shard 全过。 |
| 0.9.1 | 2026-07-03 | **微信 3.x / SQLCipher3 下线（仅保留 4.x）+ 崩溃修复**。① 用户已把各机器统一升到微信 4.x，遂**删除 `MacV3Query` 类（约 260 行）及其 `WeChatExporter` / `MacWeChatQuery` 别名**；Mac 调度检测到 3.x（或无 4.x 数据）时改为**明确报错提示升级到 4.x**，不再实例化 V3；清掉 4 处 `isinstance(exporter, MacV3Query)` 分支（`--contact-tags` / `--new-contacts` / `--contact` 两处），头部 docstring 去 3.x。`wechat_query.py` 2671→2361 行。② **修复 sqlcipher3 native double-free 崩溃**（`malloc: freed twice → abort`）：该崩溃发生在解释器退出、Python 对象析构阶段（查询结果此时已全部输出），是 C 扩展既有 bug、与拆分/重构无关（实测新旧版崩溃率一致）。`main` 结尾改为 `flush stdout/stderr → os._exit(_rc)`，跳过析构阶段从根上规避用户可见崩溃。实测真机查询卢鑫/刘学林：数据正确、无 abort、无 traceback。单测 9/9 通过（`test_backward_compat_aliases` 改为断言 V3 别名已移除）。 |
| 0.9.0 | 2026-07-03 | **Mac 4.x 真机端到端打通 + 读库层重构**。真机（微信 4.1.11）验证发现两处关键事实：① Mac 4.x 是 **每库一把独立 key**（非"单一全局密钥"），旧 `MacV4WeChatQuery` 用单 key 全解 → 升级后一条查不出；② 新版微信内存里**扫不到明文 key**（库头 salt 出现 0 次），旧内存扫描 / `setCipherKey` hook 失效。**新增 `wechat_extract_mac.py`**：lldb hook `CCKeyDerivationPBKDF` 截 `rounds==2` 派生调用拿每库 enc_key，HMAC 校验对回各库，产出 `data/mac_all_keys.json`（一键、chmod 600）。**查询侧重构**为 generation-based 类层次：抽出共享基类 `V4QueryBase`（4.x 读库，Mac4/Win4 共用），`WindowsV4Query` / `MacV4Query` 各继承并只补"拿 key+解密"；`MacV3Query` 独立；旧类名 `WindowsWeChatQuery/MacV4WeChatQuery/MacWeChatQuery` 保留为别名。修复 `isinstance` 分支（Mac4 不再是 Windows 子类，`--new-contacts` 改判 `V4QueryBase`）。新增 `tests/test_mac4_keys.py`（9 例：HMAC 校验/key→库匹配/类层次/别名/keys 解析），多分片回归全过。实测：解密 24 库、加载 44054 联系人、查到刘学林聊天到当日；提取器重跑 36/36 与首次完全一致。 |
| 0.8.0 | 2026-07-03 | 新增 **Mac 微信 4.x** 支持（此前 SKILL.md 谎称 3.x/4.x 通用，实际 `MacWeChatQuery` 全按 3.x 硬编码，4.x 零支持）。脚本自动探测 3.x/4.x 并分派：4.x 走新增的 `MacV4WeChatQuery`（发现 `Documents/xwechat_files/<wxid>/db_storage/`；SQLCipher4 page4096/kdf256000/HMAC-SHA512 解密到明文缓存；复用 Windows 4.x 的 `Msg_`/`Name2Id`/`contact` 查询逻辑）。3.x 路径零改动（已回归：`--list-contacts` 正常解密加载 43380 联系人）。SKILL.md 修正三处虚假"通用"声明，补 4.x 取密钥 hook（`WCTDatabase setCipherKey` / 内存扫描 `x'<64hex><32hex salt>'`）。⚠️ 4.x 真机端到端联调待一台 Mac 4.x 环境验证。 |
| 0.7.6 | 2026-06-28 | `--collect` 原生输出 `source` 字段,与 SoulMirror 采集器标准事件契约对齐,避免下游 Agent 二次读取 raw 结果、猜测私聊/群聊并把消息样例打印进日志。 |
| 0.7.5 | 2026-06-28 | 默认 `--export` 继续保持紧凑清洗，并跳过无可读标题的未知 XML 卡片；`Messages` 头部改为真实写出的行数，避免空壳卡片撑大导出。 |
| 0.7.3 | 2026-06-28 | `--collect` 默认改为紧凑 JSON，减少行数和空白 token；新增 `--pretty` 供人工排查时输出缩进 JSON。 |
| 0.7.1 | 2026-06-28 | `--export` 默认改为紧凑清洗格式：一条消息一行，XML/卡片/视频/表情压成短摘要，默认单条 500 字；新增 `--raw-export` 保留旧版原始多行导出，新增 `--export-max-chars` 控制单条长度。 |
| 0.7.0 | 2026-05-23 | `--collect` 模式新增三个过滤参数：`--exclude`（黑名单）、`--include-groups`（群白名单）、`--active-group-days`（默认 30 天，自动把"我最近 N 天发过言的群"加入白名单）。默认行为变化：群聊不再全收，必须命中显式白名单或活跃群；私聊仍默认全收。改用 `exporter.group_names` 判定群（之前按消息前缀判，外发消息会被误判成私聊）。 |
| 0.6.4 | 2026-05-20 | 修复 Windows 4.x 查询只扫 `message_0.db` 的缺陷：`query_messages` 现在遍历全部 `message_*.db` 分片，按 `Msg_` 表所在分片路由查询，支持同一会话表跨多分片；发件人映射改为按分片各自的 `Name2Id` 解析（rowid 是分片内局部值，不能跨分片合并）。影响 `--contact` / `--recent` / `--search` |
| 0.6.1 | 2026-04-27 | `--new-contacts` 加 Windows 支持；跨多 message_*.db 取全局 MIN（之前 Mac 实现只看单 db 局部 MIN，分散在多 db 的老朋友会被误报）；早退优化：联系人在任一 db 中命中 < threshold 即跳过后续 db |
| 0.5.0 | 2026-04-23 | 新增标签查询：`--list-tags` / `--tag` / `--contact-tags`；`--contact` 输出附 tags 字段；明确 Mac 3.x 不支持本地标签的限制 |
| 0.4.0 | 2026-04-23 | 解析微信 VoIP 通话记录（messageType=50） |
| 0.3.0 | 2026-04-22 | 三策略查询优化（direct contact / smart recent / full scan） |
