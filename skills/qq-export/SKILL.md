---
name: qq-export
description: 导出QQ聊天记录。当用户说"查QQ"、"导出QQ聊天记录"、"QQ备份"时使用此skill。
version: 0.1.0
---

# QQ聊天记录导出工具

## 支持版本

- QQ 9.x（新版NT架构）
- 数据库格式：SQLite（未加密或SQLCipher）

## 数据目录

### macOS
```
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/???????/Msg/
```

### Windows
```
C:\Users\<用户>\Documents\Tencent Files\<QQ号>\Msg\
```

## 使用方法

```bash
# 查看最新消息
python <SKILL_DIR>/scripts/qq_query.py --recent 10

# 搜索消息
python <SKILL_DIR>/scripts/qq_query.py --search "关键词"

# 导出聊天记录
python <SKILL_DIR>/scripts/qq_query.py --export ~/Desktop/qq_export.json
```

## 限制

- QQ新版NT架构数据格式变化较大，需要适配
- 部分版本数据库可能加密
- 仅支持读取，不支持写入

## 数据流向Wiki

QQ聊天数据可流向以下Wiki维度：
- **外在/关系/联系人**：QQ好友
- **外在/关系/对话记录**：聊天内容
- **内在/知识体系/信息源**：群聊信息

### 支持的应用
- **关系管理**：追踪QQ好友关系
- **对话分析**：分析聊天内容
- **信息聚合**：聚合群聊信息
