# CollectorX 采集器架构规范

## 标准采集器结构

每个采集器必须包含以下文件：

```
skill-name/
├── SKILL.md              # 使用文档（给Agent看）
├── VERSION               # 版本号
├── .collectorx.json      # 元数据
├── scripts/
│   ├── xxx_query.py      # 主CLI入口
│   └── xxx/              # 核心库（多模块）
│       ├── __init__.py
│       ├── parser.py     # 数据解析
│       ├── stats.py      # 统计分析
│       └── ...
├── tests/                # 测试
│   └── test_xxx.py
└── references/           # 参考文档
    └── xxx-format.md
```

## 各文件说明

### SKILL.md
- 给Agent看的使用文档
- 包含：功能说明、使用方法、参数说明、限制

### VERSION
- 版本号（如 0.1.0）

### .collectorx.json
- 元数据（slug、version、description）

### scripts/xxx_query.py
- 主CLI入口
- 参数解析
- 调用核心库

### scripts/xxx/
- 核心库模块
- parser.py：数据解析
- stats.py：统计分析
- 其他辅助模块

### tests/
- 单元测试
- 测试解析、统计等功能

### references/
- 参考文档
- CSV格式说明
- API文档等

## 对比

| 采集器 | 文件数 | 状态 |
|--------|--------|------|
| wechat-export | 15 | ✅ 完整 |
| feishu | 5 | ✅ 完整 |
| ticktick-cli | 12 | ✅ 完整 |
| doubao-chat-export | 19 | ✅ 完整 |
| ths-portfolio | 9 | ✅ 已补齐 |
| eastmoney-portfolio | 2 | ❌ 需补齐 |
| xueqiu-watchlist | 2 | ❌ 需补齐 |
| email-collector | 2 | ❌ 需补齐 |
| qq-export | 2 | ❌ 需补齐 |
| notes-collector | 2 | ❌ 需补齐 |
