---
name: qq-export
description: 仿照微信采集器采集QQ聊天记录，输出主人相关聊天JSON和CollectorX消息事件。当用户说"查QQ"、"导出QQ聊天记录"、"QQ备份"、"QQ投资讨论"时使用此skill。
version: 0.5.0
---

# QQ聊天记录采集工具

## 定位

QQ 采集器用于采集用户授权的个人通信证据，服务于通用分身和投资分身。它不是公共数据爬虫，也不负责外部行情/资讯。

项目层面，QQ 与微信、邮箱、飞书同属“通用个人通信采集器”。它的价值不是替代市场数据，而是补全：

- 关系图谱：好友、最近联系人、群聊和协作关系。
- 对话证据：一对一聊天、群聊、频道/群组消息。
- 信息源：用户长期关注的QQ群、朋友讨论、项目沟通。
- 投资分身证据：投资讨论、调研协作、买卖前后的沟通触发因素。

产品口径与微信采集器保持一致：采集会话、消息、发送者、时间、文本/消息类型、私聊/群聊关系和原始证据指针。能力上应该支持“全量归档”：联系人、私聊、群聊、消息、文件/媒体索引都可授权采集；默认产品模式则用“主人相关过滤”：私聊默认采集，群聊只采显式白名单或主人近期发言过的群。

## 支持版本

- QQ 9.x（新版NT架构）
- 旧版/fixture：普通 SQLite 消息表
- 新版 QQ NT：`nt_db` 下的 SQLCipher 封装库（1024 字节 QQ 头 + SQLCipher，需运行时 passphrase）

## 数据目录

### macOS
```
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/???????/Msg/
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/nt_qq_<hash>/nt_db/
```

### Windows
```
C:\Users\<用户>\Documents\Tencent Files\<QQ号>\Msg\
C:\Users\<用户>\Documents\Tencent Files\<QQ号>\nt_qq\nt_db\
```

## 使用方法

```bash
# 查看最新消息
python <SKILL_DIR>/scripts/qq_query.py recent --limit 10

# 探测真实QQ数据目录与能力，不读取消息正文
python <SKILL_DIR>/scripts/qq_query.py probe

# 诊断是否具备获取 QQ NT passphrase 的系统条件，不读取/输出密钥
python <SKILL_DIR>/scripts/qq_query.py key-diagnose

# 权限允许后捕获 passphrase 到本机文件，不在终端输出密钥
python <SKILL_DIR>/scripts/qq_query.py key-capture \
  --out ~/.collectorx/qq/nt_passphrase

# 新版QQ NT：剥离1024字节封装头，输出仍是加密SQLCipher库
python <SKILL_DIR>/scripts/qq_query.py prepare-nt \
  --roles messages,contacts,groups \
  --out-dir /tmp/qq-nt-clean

# 新版QQ NT：拿到运行时passphrase并安装SQLCipher后解密为明文SQLite
python <SKILL_DIR>/scripts/qq_query.py decrypt-nt \
  --passphrase-file ~/.collectorx/qq/nt_passphrase \
  --roles messages,contacts,groups \
  --out-dir /tmp/qq-nt-plaintext

# 解密后导出联系人、群和最近联系人清单
python <SKILL_DIR>/scripts/qq_query.py --db-dir /tmp/qq-nt-plaintext entities \
  --out /tmp/qq-entities.json

# 搜索消息
python <SKILL_DIR>/scripts/qq_query.py search "关键词"

# 导出聊天记录
python <SKILL_DIR>/scripts/qq_query.py export ~/Desktop/qq_export.json

# 同时导出 CollectorX Event JSONL
python <SKILL_DIR>/scripts/qq_query.py export ~/Desktop/qq_export.json \
  --event-export ~/Desktop/qq-events.jsonl

# 微信同构采集模式：私聊 + 主人近期活跃群，输出紧凑 JSON
python <SKILL_DIR>/scripts/qq_query.py collect --days 7 --out /tmp/qq-7d.json

# 只采纯私聊，关闭群自动白名单
python <SKILL_DIR>/scripts/qq_query.py collect --days 7 --active-group-days 0 --out /tmp/qq-private.json

# 私聊 + 指定群聊白名单，同时输出 CollectorX 事件
python <SKILL_DIR>/scripts/qq_query.py collect --days 7 \
  --include-groups "投资讨论群,项目沟通群" \
  --event-export /tmp/qq-events.jsonl \
  --out /tmp/qq-collect.json
```

## 限制

- QQ新版NT架构数据格式变化较大，需要适配
- 新版 QQ NT 本机库通常需要运行时 passphrase 和 SQLCipher 解密
- 仅支持读取，不支持写入
- 当前已能在 macOS 真实 QQ NT 目录发现联系人库、群库、消息库，并识别加密状态
- 已支持解密后的 `nt_msg.db` 中 `group_msg_table` / `c2c_msg_table` 文本消息读取
- 已支持解密后的联系人、群、最近联系人清单动态导出
- 当前机器 `key-diagnose` 结果：QQ 进程和 key 函数偏移已定位，但 macOS 拒绝 LLDB 附加；需用户处理调试权限/SIP 后才能自动捕获 passphrase
- `key-capture` 只写本机文件，默认路径 `~/.collectorx/qq/nt_passphrase`，权限为 `0600`
- 不输出 QQ 登录凭据、Cookie、Token、passphrase 或原始会话密钥

## 微信同构采集模式

`collect` 子命令对齐微信采集器 `--collect` 的过滤口径：

- 私聊：默认采集，可用 `--exclude` 剔除。
- 群聊：默认不采，除非在 `--include-groups` 白名单，或主人在最近 `--active-group-days` 天内发过实质消息。
- 全量归档：解密后可以通过 `export`/后续适配采集所有联系人、所有私聊、所有群聊和消息；下游再做隐私与噪声过滤。
- 噪声：过滤空文本、XML/卡片、撤回通知。
- 输出：紧凑 JSON，结构为 `id/source/data{chat,sender,time,text}`。
- `--participated-only`：私聊也只保留主人发过言的会话。

## CollectorX事件输出

`--event-export` 会输出 `collectorx.event.v1` JSONL。每一行是一条 `message` 事件，包含：

- `collector`: `qq`
- `owner_scope`: `personal`
- `kind`: `message`
- `data.chat/sender/sender_is_owner/text/message_type`
- `raw_ref.chat_id/message_id/file`
- `privacy.local_only: true`

## 数据流向Wiki

QQ聊天数据可流向以下Wiki维度：
- **外在/关系/联系人**：QQ好友
- **外在/关系/对话记录**：聊天内容
- **内在/知识体系/信息源**：群聊信息
- **投资/关系与协作网络**：投资群、朋友讨论、调研协作

### 支持的应用
- **关系管理**：追踪QQ好友关系
- **对话分析**：分析聊天内容
- **信息聚合**：聚合群聊信息
