# CollectorX

全渠道数据采集框架 - 基于SoulMirror架构

## 设计理念

采集器 = skill（采集逻辑）+ YAML配置（调度参数）

- **skill**：包含完整的数据采集逻辑（解密、API调用、数据解析）
- **YAML配置**：定义采集频率、模式、存储等参数
- **daemon**：自动调度和执行采集

## 架构

```
collectorx/
├── collectors/           # 采集器配置
│   ├── generic/          # 通用采集器
│   │   ├── wechat.yaml       # 微信聊天
│   │   ├── feishu.yaml       # 飞书消息
│   │   └── ticktick.yaml     # 滴答清单
│   └── vertical/         # 垂直采集器
│       ├── ths-portfolio.yaml    # 同花顺交割单
│       └── ths-watchlist.yaml    # 同花顺自选股
└── skills/               # 采集器skill
    ├── wechat-export/    # 微信采集skill
    ├── feishu/           # 飞书采集skill
    └── ticktick-cli/     # 滴答清单采集skill
```

## 快速开始

```bash
# 1. 安装skill
cp -r skills/* ~/.hermes/skills/

# 2. 复制采集器配置
cp -r collectors/* ~/.soulmirror/collectors/

# 3. 激活采集器
编辑 ~/.soulmirror/collectors/<id>.yaml，设置 armed: true
```

## License

MIT
