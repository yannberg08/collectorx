---
name: ths-portfolio
description: 导出同花顺交割单。当用户说"导出交割单"、"同花顺记录"、"交易记录"时使用此skill。
version: 0.1.0
---

# 同花顺交割单导出工具

## 功能

- 解析同花顺导出的CSV交割单
- 提取交易记录（买入/卖出/成交金额等）
- 支持多种CSV格式
- 输出标准化JSON格式

## 使用方法

```bash
# 解析交割单CSV
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv

# 导出为JSON
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv --export ~/Desktop/portfolio.json

# 查看统计
python <SKILL_DIR>/scripts/ths_query.py --file ~/Downloads/交割单.csv --stats
```

## CSV格式支持

### 格式1：标准同花顺格式
```
成交日期,成交时间,证券代码,证券名称,买卖方向,成交价格,成交数量,成交金额,手续费,印花税,过户费
2024-01-15 09:30:00,600519,贵州茅台,买入,1800.00,100,180000.00,54.00,0.00,1.80
```

### 格式2：简化格式
```
日期,代码,名称,方向,价格,数量,金额
2024-01-15,600519,贵州茅台,买入,1800.00,100,180000.00
```

## 输出格式

```json
[
  {
    "date": "2024-01-15",
    "time": "09:30:00",
    "code": "600519",
    "name": "贵州茅台",
    "direction": "买入",
    "price": 1800.00,
    "quantity": 100,
    "amount": 180000.00,
    "fee": 54.00,
    "tax": 0.00
  }
]
```

## 限制

- 需要用户从同花顺APP手动导出CSV
- 不同券商导出的格式可能不同
- 不支持实时数据，只支持历史记录
