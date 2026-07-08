# 采集器架构深度学习总结

> 当前开发基准:以 `docs/event-contract.md` 和
> `schemas/collectorx-event.schema.json` 为输出契约。本文保留对
> SoulMirror 采集器形态的学习总结,但不代表所有草稿采集器已经生产可用。
> 新采集器必须先输出 `collectorx.event.v1`,再由 lake/distill/wiki 处理。

## SoulMirror采集器架构

### 核心模式

```
skill = SKILL.md + scripts/ + references/ + tests/
```

### 4个采集器对比

| 采集器 | 代码量 | 核心技术 | 数据源 |
|--------|--------|----------|--------|
| wechat-export | 2358行 | SQLCipher4解密 + lldb hook | 本地数据库 |
| feishu | 900+行 | OAuth + Chrome CDP + CollectorX package import | 飞书API/授权导出 |
| ticktick-cli | 745行 | OAuth + REST API | 滴答API |
| doubao-chat-export | 115行 | 预编译二进制 + cookie解密 | 豆包API |

### 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                    采集器架构层次                              │
├─────────────────────────────────────────────────────────────┤
│  1. 认证层                                                   │
│     ├── OAuth流程（飞书/滴答）                                │
│     ├── Cookie解密（豆包）                                    │
│     └── 密钥提取（微信）                                      │
│                                                             │
│  2. 数据发现层                                               │
│     ├── 本地文件扫描（微信）                                  │
│     ├── API调用（飞书/滴答）                                  │
│     └── 二进制执行（豆包）                                    │
│                                                             │
│  3. 数据解析层                                               │
│     ├── SQLCipher4解密（微信）                                │
│     ├── JSON解析（飞书/滴答/豆包）                            │
│     └── XML/Protobuf解析（微信）                              │
│                                                             │
│  4. 数据格式化层                                             │
│     ├── 消息格式化                                           │
│     ├── 过滤策略                                             │
│     └── 输出格式（JSON/TXT）                                  │
│                                                             │
│  5. CLI接口层                                                │
│     ├── 参数解析                                             │
│     ├── 命令路由                                             │
│     └── 输出渲染                                             │
└─────────────────────────────────────────────────────────────┘
```

## 开发新采集器的模板

### 通用采集器模板

```python
# scripts/xxx_api.py - 主CLI入口

import argparse
import json
import os
from pathlib import Path

# 1. 配置管理
STATE_DIR = Path.home() / ".collectorx"
TOKEN_FILE = STATE_DIR / "xxx.json"

def _load_state() -> dict:
    if not TOKEN_FILE.exists():
        return {}
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))

def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

# 2. 认证流程
def auth_register(client_id: str, client_secret: str):
    """注册OAuth应用凭证"""
    state = _load_state()
    state["oauth_app"] = {
        "client_id": client_id,
        "client_secret": client_secret
    }
    _save_state(state)

def auth_authorize():
    """一条龙授权：起server + 开浏览器 + 等callback + 换token"""
    # 启动本地server
    # 打开浏览器
    # 等待callback
    # 交换token
    # 保存到本地
    pass

# 3. 数据采集
def collect_messages():
    """采集消息"""
    # 调用API
    # 解析数据
    # 格式化输出
    pass

# 4. CLI入口
def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    
    # auth命令
    auth_parser = subparsers.add_parser("auth")
    auth_parser.add_argument("action", choices=["register", "authorize", "status"])
    
    # collect命令
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--format", choices=["json", "txt"])
    
    args = parser.parse_args()
    
    if args.command == "auth":
        if args.action == "register":
            auth_register(args.client_id, args.client_secret)
        elif args.action == "authorize":
            auth_authorize()

if __name__ == "__main__":
    main()
```

### YAML配置模板

```yaml
apiVersion: collectorx/v1
kind: Collector
id: xxx
display_name: XXX采集器
refresh_interval: 24h
mode: snapshot
armed: false

# 采集器使用的skill
skill: xxx

# 采集逻辑由skill定义
```

## 下一步：开发新的通用采集器

需要开发的采集器：
1. QQ聊天记录 - 已完成真实 macOS QQ NT 库发现、加密状态探测、key 诊断、解密后联系人/群/消息 schema 适配；当前机器需先解决 LLDB 调试权限才能自动捕获 passphrase
2. 邮箱采集 - IMAP/SMTP协议
3. 笔记采集 - Notion/Obsidian API
4. 日历采集 - CalDAV协议

投资类采集器：
1. 同花顺交割单 - CSV解析
2. 东方财富交割单 - CSV解析
3. 雪球关注列表 - API或CSV
4. 券商APP交割单 - 各券商格式不同
