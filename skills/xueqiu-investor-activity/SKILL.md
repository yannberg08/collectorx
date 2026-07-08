---
name: xueqiu-investor-activity
description: 雪球投资者活动垂直采集器。采集用户授权的雪球自选、关注用户、关注组合、个人发帖、评论、收藏和用户自己的组合调仓等个人投资活动，输出 CollectorX 事件和 FinClaw 投资分身证据包。用于能力圈、关注池、信息源、人脉网络和投资观点表达；不采全站舆情，不把雪球组合当券商强交易事实。
---

# 雪球投资者活动采集器

雪球是投资垂直通道。它对投资分身有价值，但价值不是“强交易事实”，而是关注池、信息网络、观点表达和组合模拟行为。

## 采什么

- 自选股、关注股票、关注行业。
- 关注用户、关注组合、关注话题。
- 用户自己的发帖、评论、收藏。
- 用户自己的雪球组合和调仓记录。

## 不采什么

- 不采全站舆情。
- 不采他人完整时间线。
- 不采券商成交、委托、资金流水。
- 不读取 cookie、token、密码或设备指纹。

## 使用

```bash
python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/xueqiu-export.json \
  --out-dir ~/Desktop/xueqiu-investor-collect \
  --sync-soulmirror

python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/雪球自选.csv \
  --event-export ~/Desktop/xueqiu-events.jsonl

python <SKILL_DIR>/scripts/xueqiu_activity.py collect \
  --input ~/Downloads/xueqiu-network.har \
  --out-dir ~/Desktop/xueqiu-investor-collect
```

支持 JSON/JSONL/CSV/TSV/XLSX/XLSM/HTML/TXT/Markdown/HAR/ZIP。解析器会归一化常见雪球/Snowball
结构，如 `statuses`、`list`、`data.items`、`stocks`、`cubes` 和
`rebalancing_histories`，并剔除 cookie、token、password 等凭据类字段。

HAR 是用户已登录雪球后、明确授权选择的浏览器网络导出文件。采集器只读取
`xueqiu.com` 域名的响应体，记录接口路径、状态、行号和审计计数；请求头、
Cookie、Authorization 和 URL 查询串不会写入事件、manifest 或 Wiki evidence。

ZIP 包会保留 `archive.zip::member` 来源并跳过路径穿越成员。manifest 会明确
标注 `xueqiu_is_broker_trade_source: false`，雪球只作为关注网络、观点表达和
模拟组合证据，不能替代券商强交易事实。manifest 还会记录输入文件数、扩展名覆盖、
ZIP 成员/跳过成员、HAR 网络包覆盖、跳过原因、解析记录数、分页标记字段、
字段覆盖和来源面覆盖。

没有授权输入时，采集器只输出缺口状态，不伪造数据。
