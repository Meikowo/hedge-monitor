# M6a 新闻风险线索 POC 设计

## 目标与边界

在现有官方风险案例管线之外增加 Tavily 新闻搜索，只生成“待核实媒体线索”。媒体线索
不得写入 `risk_source_documents`、`derivative_risk_cases`、`risk_case_documents` 或
`risk_case_evidence`，不得自动形成监管或法律结论，也暂不向公开前端展示。

## 数据与安全

- 新建私有表 `risk_media_leads`，以规范化 URL 的 SHA-256 构造稳定主键。
- 表启用 RLS，仅显式授权 `service_role`，不向 `anon` 或 `authenticated` 建立策略或授权。
- 只保存标题、来源 URL、发布时间、短摘要、查询组、匹配词和公司匹配结果，不保存新闻全文。
- `official_corroborated` 默认 `false`；只有后续找到官方文件并完成证据核验，才能由独立流程处理。

## 采集与额度

- Tavily 固定使用 `topic=news`、`search_depth=basic`、`include_answer=false`、
  `include_raw_content=false`。
- 每次最多 12 组查询、每组最多 10 条结果；每天北京时间 08:15、20:15 各运行一次，
  月度理论上限为 744 次基础搜索，不超过免费计划 1,000 credits。
- Tavily Key 只从 `TAVILY_API_KEY` 环境变量读取；缺失时立即失败，不回显密钥。
- 手动运行默认 dry-run；定时运行在数据库迁移完成后自动幂等写入。

## 相关性与幂等

- 结果文本必须同时命中衍生品业务词和风险词，才进入输出快照或数据库。
- 使用 URL 规范化去除 fragment 和常见跟踪参数；同 URL 被多个查询命中时合并查询组。
- 写库前尝试按股票代码或公司全称匹配 `companies`；未匹配结果保留为 `unmatched`，
  供后续抽检，不擅自关联公司。
- 重复运行按 `lead_key` upsert，不产生重复线索。

## 验收

1. 单元测试覆盖请求安全参数、额度上限、相关性、URL 幂等、公司匹配和私有 RLS 契约。
2. 手动 workflow 用 1 个查询、3 条结果完成真实 dry-run，证明 Secret 可用。
3. 数据库迁移后验证 `anon/authenticated` 无权限、`service_role` 可写，并运行安全顾问。
4. 首次写入仍只产生媒体线索，不产生正式风险案例。
