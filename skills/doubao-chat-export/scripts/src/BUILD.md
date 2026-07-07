# doubao-export — 构建与使用

跨平台、零运行时依赖的单 Go 二进制，用于导出本人豆包（doubao.com）桌面版聊天记录。
无浏览器、无 a_bogus/msToken 签名；唯一凭据是从本机豆包桌面版解密出的登录 cookie。

## 依赖

- **构建期**：Go 1.23+（本机用 1.24）、纯 Go 的 `modernc.org/sqlite`（读 Chromium cookie DB，
  可无 CGO 交叉编译）、`golang.org/x/crypto`（PBKDF2）、`golang.org/x/sys`（Windows DPAPI）。
  全部编进二进制。
- **运行期**：无。不依赖 Node / Go / sqlite3 CLI。
  - macOS 运行时仅调用系统自带的 `security`（钥匙串）命令。
  - Linux 运行时会尝试系统自带的 `secret-tool`（缺失则回退 `peanuts` 口令）。

## 构建命令

本机原生构建：

```bash
go build -o doubao-export .
```

四平台交叉编译（全部 `CGO_ENABLED=0`，产物放 `dist/`）：

```bash
CGO_ENABLED=0 GOOS=darwin  GOARCH=arm64 go build -o dist/doubao-export-darwin-arm64 .
CGO_ENABLED=0 GOOS=darwin  GOARCH=amd64 go build -o dist/doubao-export-darwin-amd64 .
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o dist/doubao-export-windows-amd64.exe .
CGO_ENABLED=0 GOOS=linux   GOARCH=amd64 go build -o dist/doubao-export-linux-amd64 .
```

`go vet ./...` 通过；四平台均交叉编译成功。二进制体积约 14–15 MB（静态包含 SQLite 驱动）。

## 平台二进制

| 平台 | 文件名 |
|---|---|
| macOS Apple Silicon | `doubao-export-darwin-arm64` |
| macOS Intel | `doubao-export-darwin-amd64` |
| Windows x64 | `doubao-export-windows-amd64.exe` |
| Linux x64 | `doubao-export-linux-amd64` |

## 用法

JSON 输出到 stdout；日志/进度到 stderr。

```bash
# 列出全部会话
./doubao-export-darwin-arm64 list

# 导出单个会话的全部消息（按 index_in_conv 升序、message_id 去重）
./doubao-export-darwin-arm64 pull 38431500614263810

# 列表 + 逐会话导出到目录（默认 ./doubao-export-out），串行 + ~400ms 间隔防风控
./doubao-export-darwin-arm64 export ./out
```

`export` 产物：`conversations.json`（会话列表）+ 每会话一个 `<conversation_id>.json`
（含会话元信息 + `messages` 数组）。

## 工作原理（简述）

1. 定位本机豆包 Chromium 资料目录。
2. 拷贝 `Cookies` SQLite 到临时文件（活动 DB 被锁），用纯 Go 驱动读 `host_key like '%doubao%'` 的行。
3. 按平台解密 cookie 值（见下）。
4. 从本机 netlog（`sdk_storage/log/saman_*.log`）抓一份可用的 device query 参数；无则回退最小集。
5. 调豆包后端：`POST /samantha/thread/list` 翻页取会话；`POST /im/chain/single`（AGW 网关
   JSON↔protobuf，header 必带 `Content-Type: application/json; encoding=utf-8` + `Agw-Js-Conv: str`）
   按 `direction` 翻页取消息。

## Cookie 解密（按平台分叉，build-tag 分文件）

- **darwin**（`cookies_darwin.go`）：数据目录 `~/Library/Application Support/Doubao`；
  cookie DB `Default/Cookies`。密钥来自钥匙串 `Doubao Safe Storage`
  → PBKDF2-HMAC-SHA1(pw, "saltysalt", 1003, 16)；值去 `v10`/`v11` 前缀，AES-128-CBC
  （IV=16×0x20），去 PKCS7；若明文前 32 字节含控制字符则丢弃（新版 SHA256 域前缀）。
  **已在本机真豆包 + 登录态实测通过。**
- **windows**（`cookies_windows.go`）：数据目录候选 `%LOCALAPPDATA%\Doubao\User Data`、
  `%LOCALAPPDATA%\Doubao`、`%APPDATA%\Doubao`；cookie DB `Default\Network\Cookies`
  或 `Default\Cookies`。密钥读 `Local State` 的 `os_crypt.encrypted_key`（base64 解码、去开头
  `DPAPI` 5 字节），用 DPAPI `CryptUnprotectData` 解出 32 字节 key；值去 `v10` 前缀，
  AES-256-GCM（nonce=12 字节，尾 16 字节 tag）。另含 pre-v10 旧值的 DPAPI 直解回退。
- **linux**（`cookies_linux.go`）：数据目录 `~/.config/Doubao`；AES-128-CBC，key 优先经
  `secret-tool` 取 secret-service 口令，失败回退 `peanuts`+PBKDF2(iters=1)。两个候选 key 都试。

## 风险点 / 未真机验证

- **Windows（`cookies_windows.go`）：未在真实 Windows 机器上验证。** 仅通过代码审阅 + 交叉编译保证可编。
  可能需要按真机调整的点：
  - 数据目录与 cookie DB 的实际相对路径（不同豆包版本可能用 `User Data\Default\Network\Cookies`，
    代码已按常见候选顺序尝试，但豆包具体落点未确认）。
  - `os_crypt.encrypted_key` 是否始终带 `DPAPI` 前缀、AES-256-GCM 的 nonce/tag 切分。
  - 新版是否也会给明文加 32 字节域前缀（代码已做控制字符探测，但启发式可能误判，需真机校准）。
  - DPAPI 必须在写入该 cookie 的同一 Windows 用户会话下运行才能解密。
- **Linux（`cookies_linux.go`）：未真机验证，best-effort。** secret-service 取口令用的是
  `secret-tool lookup application Doubao`，实际属性名/口令存储方式未确认；多数情况会落到 `peanuts` 回退。
  豆包是否提供官方 Linux 桌面版亦未确认。
- query 参数回退集（netlog 为空时）可能被网关拒绝；打开一次豆包桌面版可填充 netlog 后修复。
- 鉴权仅靠 cookie，cookie 过期需在豆包桌面版重新登录。
```
