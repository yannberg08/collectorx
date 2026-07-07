# CollectorX

全渠道数据采集框架 - 基于SoulMirror架构

## 设计理念

采集器是YAML配置文件，daemon自动调度和执行，数据存储在lake目录。

## 采集器分类

```
collectors/
├── generic/           # 通用采集器（完善通用Wiki - 9维）
│   ├── filesystem.yaml    # 本地文件
│   ├── wechat.yaml        # 微信聊天
│   ├── feishu.yaml        # 飞书消息
│   └── dingtalk.yaml      # 钉钉消息
└── vertical/          # 垂直采集器（完善垂直分身Wiki）
    ├── ths-portfolio.yaml     # 同花顺交割单
    ├── ths-watchlist.yaml     # 同花顺自选股
    ├── eastmoney-portfolio.yaml  # 东方财富交割单
    └── xueqiu-watchlist.yaml     # 雪球关注列表
```

## 快速开始

```bash
# 复制采集器配置到 ~/.collectorx/collectors/
cp -r collectors/* ~/.collectorx/collectors/

# 激活采集器
编辑 ~/.collectorx/collectors/<id>.yaml，设置 armed: true

# 查看采集器状态
collectorx status
```

## License

MIT
