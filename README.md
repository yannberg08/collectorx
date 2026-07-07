# CollectorX

全渠道数据采集框架 - 通用/垂直分类的插件化采集器

## 设计理念

采集器 = skill（采集逻辑）+ YAML配置（调度参数）

## 架构

```
collectorx/
├── collectors/           # 采集器配置
│   ├── generic/          # 通用采集器
│   │   ├── wechat.yaml
│   │   ├── feishu.yaml
│   │   ├── ticktick.yaml
│   │   └── doubao.yaml
│   └── vertical/         # 垂直采集器
│       ├── ths-portfolio.yaml
│       └── ths-watchlist.yaml
└── skills/               # 采集器skill（完整代码）
    ├── wechat-export/    # 微信采集
    ├── feishu/           # 飞书采集
    ├── ticktick-cli/     # 滴答清单采集
    └── doubao-chat-export/  # 豆包采集
```

## SoulMirror采集器清单

| Skill | 功能 | 类型 |
|-------|------|------|
| wechat-export | 微信聊天导出 | 通用 |
| feishu | 飞书消息/文档 | 通用 |
| ticktick-cli | 滴答清单任务 | 通用 |
| doubao-chat-export | 豆包聊天导出 | 通用 |

## 新增采集器（待开发）

### 通用采集器
- QQ聊天记录
- 邮箱（Gmail/Outlook/QQ邮箱）
- 笔记（Notion/Obsidian/有道云笔记）
- 日历（Google Calendar/Apple Calendar）

### 投资类采集器
- 同花顺交割单/自选股
- 东方财富交割单/自选股
- 雪球关注列表
- 券商APP交割单

## License

MIT
