# schema_snapshot.md —— 数据契约（人读版）

> 与 db/001_init.sql 同步维护；表结构变更的会话结束时必须更新本文件。
> 快照版本：007（2026-08-01，新增私有历史新闻回填队列）

## 层次关系

```
companies ──(code)── announcements ──1:1── extractions ──1:N── quota_items
                          │
                     event_members ──N:1── hedge_events（派生表，全量重建）

companies ──(code)── periodic_reports ──1:1── periodic_derivatives
                              └──────────1:N── periodic_metric_items
                              └──────────1:N── periodic_hedge_accounting_items

companies ──(code)── risk_source_documents
companies ──(code)── derivative_risk_cases
risk_source_documents ──N:M── derivative_risk_cases（risk_case_documents）
             └─────────────── risk_case_evidence ───────┘

companies ──(code，可空)── risk_media_leads（未核实、非正式案例）
risk_media_backfill_windows ──(进度队列)── risk_media_leads（按 URL 幂等汇入）
```

## M6a 衍生品风险案例独立数据域

### risk_source_documents（官方来源文档）

按 `source_doc_id` 主键及 `(source_org, official_doc_id)` 唯一约束去重。记录来源机构、
来源类型、公司、标题、日期、强制 HTTPS 原文链接、文档格式、哈希/本地路径、正文字符数、
命中的衍生品与风险词、原始元数据和处理状态。状态机为 discovered → candidate →
relevant / irrelevant → extracted；失败可标记 failed。官方公司代码不在当前公司主表时
允许置空，不丢弃来源文档。

### derivative_risk_cases（正式风险案例）

一案一行，必须关联公司，风险类型限定为 PRD 5.8 的八类。保存事件日期、工具、品种、
摘要、金额口径、监管措施、结果、案例状态、模型与置信度。规则候选不得直接写入本表；
必须经过正文相关性、模型结构化和官方证据回验。

### risk_case_documents / risk_case_evidence

`risk_case_documents` 以复合主键连接案例与问询、回复、措施、处罚、整改及其他支持文档。
`risk_case_evidence` 保存字段级原文引文、页码/段落、抽取值、官方 URL、引文与数值回验
状态及置信度。正式案例验收要求至少一条官方来源证据。

### risk_media_leads（私有新闻风险线索）

按规范化 URL 的 SHA-256 主键幂等去重，保存 Tavily 标题、HTTPS 链接、短摘要、发布时间、
查询组、衍生品/风险命中词、公司匹配与供应商分数。`official_corroborated=false` 且
`need_review=true` 为默认值；本表不外键连接正式案例，不保存新闻全文。RLS 已启用，
仅显式授权 service_role，anon/authenticated 无策略和表权限，当前前端不可读取。

### risk_media_backfill_windows（私有历史回填进度）

按查询组和精确日期范围建立确定性窗口，保存年度、粒度、状态、尝试次数、原始结果数、线索数、
credit 消耗和异常。年度窗口命中每窗口结果上限时拆为四个季度；失败最多重试 3 次，运行超过
3 小时可恢复。表启用 RLS 且只授权 service_role，不与正式风险案例建立外键，也不向前端公开。
窗口由仅 service_role 可执行的原子领取函数加锁；媒体线索由受控合并函数写入，只合并机器发现字段，
不得覆盖人工维护的 `status`、`need_review` 或 `official_corroborated`。

## periodic_reports（定期报告元数据与处理状态）

`report_id` 使用巨潮 announcementId；`report_type` 为 annual/semiannual，`report_period`
使用 `2025FY` / `2025H1`。状态机为 discovered → located → extracted；无法解析时进入
needs_ocr / failed / skipped。候选页为 PDF 1-based 页码，连同定位词、定位器版本、总页数和
全文字符数保存，用于复现页面筛选。

## periodic_derivatives（每份报告的披露判断）

一份报告一行。`disclosure_status` 是一等公民：有数值 / 提及无数值 / 未提及 / 需复核。
保存 scope、工具、品种、目的、套期会计类型、证据、模型和提示词版本；`review_status`
默认 pending，机器抽取不能自动等同于人工接受。v1.5 增加
`hedge_accounting_status`（已应用 / 未应用 / 混合应用 / 未明确披露 / 需复核）、
`hedge_accounting_types`、未应用原因及页码/引文/引文回验。旧 `hedge_accounting` 数组保留兼容。

## periodic_metric_items（逐项原文数值事实）

一份报告可有多条事实。每条保存 metric_type、scope/underlying、原始 value、currency、unit、
时间口径（period / period_end / period_peak）、来源章节、原文摘录和页码。`value_origin`
数据库约束固定为 reported，估算值无法写入主事实表。`value_verified` 只证明数字可从摘录
复算；`quote_verified` 证明摘录可在候选正文定位。可信统计必须两者同时为 true。

`fact_level` 明确事实归属：`report` 要求 scope/underlying 均为空，`scope` 要求仅 scope，
`underlying` 要求 scope 和 underlying 同时存在。新增综合损益、处置投资收益、公允价值
变动损益和公允价值净额的明确指标类型；旧 `period_pnl` 只为历史兼容，不再由 v2.0 提示词
生成。保证金事实额外保存 `account_name`、`is_restricted`、`counterparty`，避免重复计数和
错误比较。

## periodic_hedge_accounting_items（套期会计业务级事实）

一份报告可按业务范围、工具或品种保存多条套期会计事实。记录应用状态、会计方法、未应用
原因、来源章节、页码、引文、引文回验、置信度和复核标记。报告级摘要仍保存在
`periodic_derivatives`，本表不进入公司维表。

公告额度核验等级由 `scripts/periodic_verification.py` 决定：期间最高同口径=A、仅期末快照=B、
存在相关但不同口径事实=C、无可用事实=D。期间买卖额、公允价值和损益不直接与授权额度比较。

## companies（公司维表，来源 iFind 季度导出）

| 列 | 类型 | 说明 |
|---|---|---|
| code | text PK | 6位证券代码 |
| market | text | SZ / SH / BJ |
| name / full_name | text | 简称 / 全称 |
| ent_type | text | 枚举：央企 / 地方国企 / 民企 / 外资 / 集体 / 其他 |
| ent_nature_raw | text | iFind 原值（中央企业/私营/中外合资…） |
| actual_controller | text | 实际控制人 |
| scale | text | L 大型 / M 中型 / S 小型 / XS 微型 |
| ind_l1 / l2 / l3 | text | 同花顺行业三级 |
| province / city | text | 属地 |
| profile | text | 公司简介 |
| source / updated_at | | 来源文件名 / 触发器维护 |

## announcements（公告层）

| 列 | 类型 | 说明 |
|---|---|---|
| ann_id | text PK | 巨潮 announcementId（全局去重键） |
| code / name / title | text | |
| publish_time | timestamptz | 带 +08:00 |
| ann_date | date | 北京日期，按日聚合用 |
| adjunct_url / pdf_url | text | pdf_url = static.cninfo.com.cn 直链 |
| source | text | `title:关键词` 或 `fulltext-audit` |
| matched_keywords | text[] | 全部命中词 |
| status | text | **状态机**：pending → extracted / irrelevant / skipped / failed |
| note | text | 失败或无关原因 |

采集脚本 upsert 载荷**不含 status/note**：重跑不会把已抽取公告打回 pending。

## extractions（抽取层，1:1 公告）

| 列 | 说明 |
|---|---|
| ann_id PK/FK | 级联删除 |
| model / prompt_version | 抽取可追溯（提示词改动必须递增版本） |
| is_hedge_related | false ⇒ 公告状态 irrelevant |
| ann_role | 枚举：计划-董事会 / 计划-股东大会 / 可行性分析 / 管理制度 / 进展 / 平仓或终止 / 风险提示 / 其他 |
| scope[] | 商品 / 外汇 / 利率 / 其他 |
| instruments[] / underlyings[] / venues_detail[] | 工具 / 品种 / 点名交易所 |
| venue | 境内 / 境外 / 境内外 / 未披露 |
| approval_level | 董事会 / 股东大会 / 董事会及股东大会 / 未披露 |
| plan_label / meeting / period_text / period_months | 计划年度标签 / 会议届次 / 期限 |
| is_revolving / use_own_funds | 循环额度 / 自有资金 |
| summary / confidence / evidence(jsonb) / raw(jsonb) | 摘要 / 自评置信 / 证据 / 完整输出 |
| text_chars / pdf_pages / extracted_at | 抽取审计 |

## quota_items（额度明细——口径结构化的落点）

| 列 | 说明 |
|---|---|
| ann_id FK | 一公告可多条（商品外汇分列、境内外分列等） |
| scope | 商品 / 外汇 / 利率 / 其他 / 综合 |
| **basis** | **口径枚举**：保证金占用 / 业务总额 / 名义本金 / 合约价值 / 其他 / 未披露 |
| amount | 原币"元"数值；百分比类口径为 null |
| currency | CNY / USD / EUR / HKD / JPY / 其他 |
| raw_text / page | 原文摘录 ≤120字 / 页码（证据引文卡数据源） |
| amount_verified | 程序回验：amount 能否由 raw_text 数字复算（PRD 5.7 防幻觉兜底） |
| quote_verified | 程序回验：raw_text 确在送抽正文中 |

**设计纪律**：任何额度汇总/排行必须按 basis 分口径；amount_verified=false 的行
只进复核，不进统计。

## hedge_events（事件层，派生表）+ event_members

| 列 | 说明 |
|---|---|
| event_key PK | `code|锚定年|scope` 确定性键（重建后稳定） |
| anchor_year / scope[] / plan_label | 分组维度 |
| stage | 股东大会通过 / 董事会通过 / 仅制度可行性 / 进展(未见计划公告) |
| first/latest_ann_date / ann_count / ann_roles[] | 时间线概况 |
| instruments[] / underlyings[] / venue / period_text / is_revolving / use_own_funds | 事件属性 |
| quota jsonb | 取自最高审批阶段计划公告的 quota_items 快照 |
| quota_source_ann_id | 额度证据链：来自哪份公告 |

event_members：ann_id PK → event_key。整层由 `build_events.py` 全量重建，
改分组规则重跑即可，不伤底层。

## 视图（前端读取契约）

- **v_ann_flow**：公告 × 抽取 × 事件键 × 公司（行业/性质/属地）——公告流列表页数据源
- **v_events**：事件 × 公司——概览统计与公司详情时间线数据源

## RLS

定期报告与官方风险案例表均启用 RLS；anon/authenticated 仅 select；写入只经
service_role（绕过 RLS）。新闻风险线索表更加严格：不授予前端角色任何权限，只允许
service_role。所有新表显式授权所需角色，以兼容 Supabase 2026 年开始推行的“新表默认
不暴露 Data API”行为。两个前端视图均为 security_invoker；M6a 当前尚未建立前端视图。

## 重新生成快照的 SQL（供核对线上库与本文件一致性）

```sql
select table_name, column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' order by table_name, ordinal_position;
select tablename, rowsecurity from pg_tables where schemaname = 'public';
select * from pg_policies where schemaname = 'public';
```
