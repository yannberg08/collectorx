# QQ数据格式参考

## 数据目录位置

### macOS
```
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/<QQ号>/Msg/
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/nt_qq_<hash>/nt_db/
```

### Windows
```
C:\Users\<用户>\Documents\Tencent Files\<QQ号>\Msg\
C:\Users\<用户>\Documents\Tencent Files\<QQ号>\nt_qq\nt_db\
```

### Linux
```
~/.local/share/QQ/<QQ号>/Msg/
```

## 新版 QQ NT 数据库

真实 macOS QQ NT 目录常见文件：

- `nt_msg.db`：私聊/群聊主消息库
- `profile_info.db`：联系人/资料库
- `group_info.db`：群资料库
- `recent_contact.db`：最近联系人
- `guild_msg.db`：频道/群组消息
- `files_in_chat.db` / `rich_media.db`：文件与富媒体索引
- `*_msg_fts.db`：消息全文索引

这些文件通常不是普通 SQLite。文件头为 `SQLite header 3`，包含 `QQ_NT DB` 标记；前 1024 字节是 QQ 封装头，去掉后才是 SQLCipher 数据页。常见参数为 page size 4096、kdf_iter 4000，解密仍需要 QQ 运行时传给数据库层的 passphrase。

当前采集器行为：

- `probe`：发现真实 `nt_db`，盘点联系人/群/消息库，不读取正文。
- `key-diagnose`：定位 QQ 进程、CPU 架构、`nt_sqlite3_key_v2` 偏移，并诊断 LLDB 是否能附加；不读取/输出密钥。
- `key-capture`：权限允许后捕获 passphrase 到本机 `0600` 文件；不在终端输出密钥。
- `prepare-nt`：去掉 1024 字节封装头，输出仍加密的 clean SQLCipher 文件。
- `decrypt-nt`：在用户提供 passphrase 文件/环境变量且本机有 SQLCipher 时，导出明文 SQLite。
- `entities`：在明文 SQLite 可读后导出联系人、群和最近联系人清单。
- `collect/export`：只在明文 SQLite 可读后输出正文和 CollectorX 事件。已支持 `group_msg_table` / `c2c_msg_table` 的纯文本提取。

当前本机诊断：

- QQ 主进程已发现。
- `wrapper.node` 中 `nt_sqlite3_key_v2` 偏移已定位。
- macOS 拒绝 LLDB 附加 QQ 进程，因此无法自动捕获 passphrase。
- Homebrew 安装 SQLCipher 曾尝试执行，但下载依赖卡住，已中止；当前本机仍未安装 `sqlcipher`。

安全约束：

- 不打印 passphrase、Cookie、Token、登录凭据或原始会话密钥。
- 默认不把真实聊天正文输出到对话；采集结果写到用户本机指定路径。

## 数据流向Wiki

QQ聊天数据可流向以下Wiki维度：
- 外在/关系/联系人
- 外在/关系/对话记录
- 内在/知识体系/信息源
