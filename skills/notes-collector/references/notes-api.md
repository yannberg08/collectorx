# 笔记应用API参考

## Notion API

- 认证方式：API Token
- 推荐方式：用 `--token-env` 从环境变量读取 Token，不把 Token 写入命令历史或采集包。
- 文档：https://developers.notion.com/reference
- 主要端点：/v1/search, /v1/pages, /v1/databases

## Obsidian

- 认证方式：本地文件访问
- 数据格式：Markdown文件
- Vault目录：用户指定

## 授权导出导入

- 支持目录或单文件：Markdown、TXT、HTML、JSON、JSONL、NDJSON、CSV、TSV、ENEX。
- CSV/TSV 表格按行转成 note，适配 Notion database、投资规则表、复盘表和研究清单导出。
- 支持 ZIP 授权导出包，常见于 Notion、印象笔记迁移包和手动打包的笔记库。
- ZIP 内部只读取支持的笔记文件，并跳过绝对路径或包含 `..` 的成员，避免路径跳出。
- `manifest.json` 的 `platform_coverage` 会记录预期 P1 平台、实际观察平台、缺失平台和事件数。

## 数据流向Wiki

笔记数据可流向以下Wiki维度：
- 内在/知识体系/笔记
- 内在/知识体系/学习记录
- 外在/履历/项目文档
