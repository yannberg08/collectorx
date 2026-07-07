# 雪球关注列表授权导出格式参考

## 标准 CSV

```csv
代码,名称,行业,备注,关注时间
600519,贵州茅台,白酒,核心关注,2026-07-08T09:00:00+08:00
000858,五粮液,白酒,观察
```

## 简单代码列表

```txt
SH600519 贵州茅台
SZ000858 五粮液
HK00700 腾讯控股
```

## 字段说明

| 字段名 | 别名 | 类型 | 说明 |
| --- | --- | --- | --- |
| 代码 | code, symbol, stock_symbol | string | 股票代码，支持 SH/SZ/BJ/HK 前缀 |
| 名称 | name, stock_name | string | 股票名称 |
| 分组 | group, folder | string | 用户自选分组 |
| 行业 | industry, sector | string | 所属行业 |
| 标签 | tags, labels | list/string | 用户标签 |
| 备注 | note, memo, reason | string | 用户备注或关注理由 |
| 关注时间 | followed_at, added_at, created_at | datetime/string | 用户关注或加入时间 |

## 数据流向 Wiki

关注列表数据可流向以下 Wiki 维度：

- `investor.opportunity_watchlist.watchlist`
- `investor.capability_circle.attention_universe`

它不应单独流向持仓、成交、委托或资金流水维度。
