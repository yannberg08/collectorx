---
name: xueqiu-watchlist
description: 导出雪球关注列表。当用户说"导出关注"、"雪球股票"、"自选股"时使用此skill。
version: 0.1.0
---

# 雪球关注列表导出工具

## 功能

- 解析雪球导出的关注列表CSV
- 提取关注的股票代码和名称
- 支持多种CSV格式
- 输出标准化JSON格式

## 使用方法

```bash
# 解析关注列表CSV
python <SKILL_DIR>/scripts/xueqiu_query.py --file ~/Downloads/关注列表.csv

# 导出为JSON
python <SKILL_DIR>/scripts/xueqiu_query.py --file ~/Downloads/关注列表.csv --export ~/Desktop/watchlist.json

# 查看列表
python <SKILL_DIR>/scripts/xueqiu_query.py --file ~/Downloads/关注列表.csv --list
```

## CSV格式支持

### 格式1：标准格式
```
代码,名称,行业,备注
600519,贵州茅台,白酒,核心持仓
000858,五粮液,白酒,观察
```

### 格式2：简化格式
```
600519
000858
```

## 输出格式

```json
[
  {
    "code": "600519",
    "name": "贵州茅台",
    "industry": "白酒",
    "note": "核心持仓"
  }
]
```

## 限制

- 需要用户从雪球APP手动导出CSV
- 不支持实时数据
