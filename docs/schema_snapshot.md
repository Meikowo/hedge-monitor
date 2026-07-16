# schema_snapshot.md —— 数据契约（人读版）

> 与 db/001_init.sql 同步维护；表结构变更的会话结束时必须更新本文件。
> 快照版本：001（2026-07-13 初版）

## 层次关系

```
companies ──(code)── announcements ──1:1── extractions ──1:N── quota_items
                          │
                     event_members ──N:1── hedge_events（派生表，全量重建）
```

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

6 张表全部启用 RLS；anon/authenticated 仅 select；写入只经 service_role（绕过 RLS）。

## 重新生成快照的 SQL（供核对线上库与本文件一致性）

```sql
select table_name, column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' order by table_name, ordinal_position;
select tablename, rowsecurity from pg_tables where schemaname = 'public';
select * from pg_policies where schemaname = 'public';
```
