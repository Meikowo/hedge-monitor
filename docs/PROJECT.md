# PROJECT.md —— 套保监控（hedge-monitor）项目上下文主文件 v2.5

> 用途：每次与 Claude 开新会话时上传本文件（或放入 Claude Project 知识库）。
> 由你维护；每次会话结束让 Claude 输出更新段落，你替换后 commit。
> 需求的唯一基准是 docs/PRD.md（v1.5），本文件记录"现状与决策"，不复述需求。
> 最后更新：2026-07-29（M4 正式前端 v0.1 完成，40 份报告进入实时界面）

## 1. 一句话定位

自用专业研究工具：A 股上市公司套保披露的日更监控、结构化抽取、「计划 vs 实际」
对比分析，以及衍生品相关监管问询、处罚和重大风险案例监测。服务期货研究所研究员的
风险管理研究与展业线索需求。单用户，无对外服务。

## 2. 架构与技术栈（R0 定稿）

- **采集**：GitHub Actions（Python）→ 巨潮 hisAnnouncement（标题层）+
  fulltextSearch（正文审计层）。✅ Actions 直连巨潮已长期验证可达。
- **抽取**：MiniMax-M3，OpenAI 兼容接口 `https://api.minimaxi.com/v1`。
  公告管线使用 adaptive thinking；M4 定期报告改为显式禁用 thinking + 四段短 JSON，
  防止长输出截断，并支持按短批次重跑。Actions 与本地探活均已验证可达。
- **存储**：Supabase Postgres，PostgREST REST 直写（service_role），
  迁移文件在 db/ 且为唯一事实源（"照仓库即可重建库"）。
- **公司维表**：iFind 手动导出（季度刷新）为权威来源，含企业性质+同花顺三级行业，
  一并解决了旧 #7 ent_type 补全。akshare/东财路线已废弃（Actions 不可达，两次实测证伪）。
- **前端**：GitHub Pages 静态站（M3 重做），数据通路定为 **anon key 直连
  Supabase + RLS 只读**（策略已随 001_init.sql 就位）；读取契约=视图
  v_ann_flow / v_events。设计语言按 PRD 7.6「研报纸感的数据终端」。
- **调度**：daily（北京03:00）负责公告采集；extract 每6小时自动抽取最多600条
  pending；audit（每月1日）自动补漏；backfill / import-companies / probe 手动触发。
- **新增规划（v1.3）**：风险案例使用独立官方来源适配器、独立数据表与独立 Actions
  concurrency group；自动发现、关键词召回、相关性判定、结构化抽取、证据回验和幂等
  upsert。首版不依赖手工录入，人工只做质量抽检。

## 3. 数据模型（三层，契约详见 docs/schema_snapshot.md）

```
companies(维表)   announcements(公告层)
                        │ 1:1
                  extractions(抽取层) ── quota_items(额度明细，分口径)
                        │ 派生聚合（build_events 全量重建）
                  hedge_events(事件层) ── event_members(挂靠关系)
```

三个老问题的落地方式：
1. **查全率**：三层召回全自动——L1 标题词表（config/keywords.yml，13词）逐词查+去重；
   L2 月度全文审计自动补捞漏检入库；L3 LLM is_hedge_related 兜底过滤噪音。加词=改配置。
2. **事件去重**：hedge_events 一行=一次套保决策；进展/股东大会决议等挂靠而非新增；
   全部统计口径应基于事件层或明确声明基于公告层。
3. **额度口径**：quota_items 结构化五元组（scope/basis/amount/currency/raw），
   basis 闭集枚举（保证金占用/业务总额/名义本金/合约价值/其他/未披露）+ CHECK 约束；
   每条额度带原文摘录、页码与**程序回验**双标志（amount_verified/quote_verified，
   PRD 5.7 第二层防线已在公告管线提前落地）。

## 4. 关键决策记录（ADR，一事一行，详情见对应 worklog）

- 2026-07-08：companies 构建移出 Actions（东财/akshare 机房 IP 被拉黑）；确立
  「国内商业接口可达性必须逐源实测」原则。
- 2026-07-13：**R0 从头重建**——放弃旧库存量（约4000+公告/124抽取），理由：新词表
  召回本就要求重抓、新数据模型要求重抽、旧抽取无页码证据与口径明细。旧代码存档
  legacy-demo 分支。
- 2026-07-13：companies 权威来源定稿为 iFind 季度导出；build_companies v4 路线废弃。
- 2026-07-13：抽取层与事件层分离；事件层为**派生表**（确定性键+全量重建），
  分组规则可随时演进而不伤底层数据。
- 2026-07-13：抽取范围含制度/可行性/进展（is_hedge_related=true + ann_role 区分），
  仅"计划-董事会/股东大会"贡献事件额度；irrelevant 由 LLM 判定自动打标。
- 2026-07-13：秘钥红线维持（值不进仓库/对话/前端），MiniMax key 统一变量名 LLM_API_KEY。

## 5. 秘钥清单（只记名字与位置）

- GitHub repo Secrets：SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、LLM_API_KEY
- 本地 .env（已 gitignore）：同上三个
- 前端（M3 起）只允许 anon key + RLS 只读

## 6. 进度清单（2026-07-30 版）

| # | 事项 | 状态 |
|---|------|------|
| R0.1 | 三层数据模型 + 迁移 + 视图 + RLS（db/） | ✅ 新 Supabase 已执行并验收 |
| R0.2 | 采集/审计/抽取/事件/导入五条管线 + 6 workflows | ✅ 已合并 main |
| R0.3 | 用户侧部署 8 步（README 首次部署节） | ✅ 已完成核心部署 |
| R0.4 | MiniMax@Actions 探活结论 | ✅ Actions 探活成功 |
| R1 | 回填 2026 + 清积压 + 首轮 verify.sql 全量回贴 | ✅ 2026 公告积压与失败项已清零，事件层重建完成 |
| R2 | 逐年回填 2025→2021，每年配抽取清零（挂机） | 🔄 2025 已全部处理；2024 已开始且仅余 152 条 pending、0 failed |
| R3 | 抽取质量金标准评测：50 份人工标注 vs 抽取结果，字段级准确率 | ⏸ 建议 R1 后 |
| M3 | 前端正式版（PRD 7.x + 设计语言 7.6，先视觉方向稿再落码） | ✅ v1 已部署：高密度事件研究 + 证据详情 + 数据看板 + CSV 导出 |
| M4a/b | 定期报告（年报+半年报）采集与解析 | 🔄 40份2025FY已抽取，265条数值全部双回验；正式前端v0.1已完成；继续扩展120家优先池 |
| M5 | 计划 vs 实际三维核对（PRD 5.6） | 🔄 前端已展示公告候选关联；金额/口径自动匹配仍待M4样本稳定后实现 |
| M6a | 自动化衍生品风险案例 POC（PRD 5.8） | 🔄 第一纵向切片已上线：独立四表、SSE 官方适配器、规则闸门、dry-run/幂等写入与手动 POC workflow；待接 SZSE/CSRC 与 LLM 证据抽取 |
| M6b | 风险案例历史扩展、增量监测与前端（PRD 7.7） | ⏸ 依赖 M6a 数据契约稳定 |

## 7. 风险与已知局限

1. **模型共享额度**：MiniMax@Actions 已长期运行验证可达；公告、M4 与未来 M6 共享套餐额度，
   新管线必须分别设置批次上限、记录调用量并避免同时占满配额。
2. **事件分组 v1 是启发式**：同年同类追加额度会并入同一事件（多数场景合理）；
   跨年多期计划以标签年锚定。待真实数据验证后在 build_events v2 细化——派生表
   设计保证重算零成本。
3. **重建成本**：历史 5 年重抽约 1.5–2.5 万次 LLM 调用（多数公告 irrelevant 判定
   很便宜），MiniMax 年费套餐内预计可covered；逐年推进可随时观察用量。
4. **巨潮风控**：所有巨潮 workflow 共用 concurrency group 串行化；退避已内置；
   整轮失败等 1 小时幂等重跑。
5. **Supabase 免费档**：daily 每日写库天然保活；留意 Actions 断档。
6. **公开性**：anon 可读全库（自用接受 obscurity）；如需加口令在 M3 讨论。
7. **iFind 表时效**：季度刷新，退市/更名/性质变更在刷新间隔内滞后（可接受）。
8. **年报复杂表格证据**：当前正式前端只读取 `value_verified=true` 且
   `quote_verified=true` 的事实；跨页表头、单位继承和换行标题已支持，但新表型仍须
   先通过 POC 审计再扩张。
9. **风险来源异构与页面变动**：交易所、证监会及派出机构页面结构不同，适配器必须逐源
   测试、保存原始 URL/哈希，并允许单一来源故障时独立重试。
10. **衍生品相关性误判**：一般经营问询或处罚不得因公司曾做套保而进入风险案例库；
    必须由原文中的衍生品业务证据通过相关性闸门。SSE 小样已排除“证券期货市场诚信
    档案”、航运“舱位互换”、应收款“远期结算”、远期退换货、股票期权激励及
    “过渡期权益”等非衍生品语境。
11. **并行资源冲突**：M4 与 M6 可并行写各自数据域，但共享迁移编号、公司维表、
    Supabase 配额和 MiniMax 套餐；前端核心文件在数据契约稳定后串行接入。

## 8. 下次会话前的待补信息（视会话主题选带）

- 常备三件套：本文件 + docs/schema_snapshot.md + 最新一份 worklog
- R1 收口会话：verify.sql 全段输出 + 各 workflow 运行时长/异常截图
- 质量评测会话（R3）：2–3 份典型公告 PDF（商品/外汇/进展各一）+ 你手工认定的
  正确抽取值（金标准雏形）
- 前端会话（M3）：2–3 个你喜欢的参考站或风格描述 + 桌面/手机使用比例

## 21. M4a annual-report POC checkpoint (2026-07-20)

- Added migrations `002_periodic_reports.sql` and `003_periodic_hardening.sql`: report metadata,
  disclosure-level extraction, reported metric facts, RLS, explicit Data API grants, security-invoker
  views, and a fixed function search path. Supabase Security Advisor now reports zero findings.
- Deterministic sample: 30 A-share companies, split evenly across commodity, FX, and mixed hedging,
  with industry and ownership diversity. B-share handling is intentionally deferred after code/orgId
  mismatch was observed for 200553.
- Metadata discovery was changed from a capped full-market scan (10 minutes, only 4/30) to CNINFO
  code+orgId targeted queries (about one minute, 30/30).
- Two real PDFs were localized without LLM: JinkoSolar 289→15 pages and Beyondsoft 206→15 pages.
- One JinkoSolar report was extracted end to end in about 101 seconds: 18 reported metric facts;
  3 passed both literal-number and exact-quote checks, 15 table-derived quotes remain pending review.
- No annual-report schedule is enabled. Next gate: improve table evidence alignment, manually review the
  first two reports, then decide whether to expand from 2 to 30. See `docs/M4A_POC.md`.

## 22. M3 province and multi-year dashboard checkpoint (2026-07-21)

- Added the existing `province` dimension to event and announcement tables, detail drawers, full-result
  search, and UTF-8 CSV exports. No database migration was required because both read-only views already
  expose the company province field.
- Added a province coverage chart (Top 16 by distinct company count, with event count alongside it).
- Added one dashboard-wide year selector. It filters enterprise nature, scope, industry, province,
  approval, and field-quality charts while the year trend intentionally retains the complete time series.
- Live data verification: 2025 has 1,464 events / 1,321 companies and 1,443 rows with province; 2026 has
  1,812 events / 1,635 companies and 1,808 rows with province.
## 9. R1 checkpoint (2026-07-17)

- 2026 announcements backfill verified in the new Supabase project: 3,526 rows, covering 2026-01-01 through 2026-07-15.
- All 3,526 rows are currently `pending`; `extractions` is still empty by design.
- Next action: run `Extract Batch (LLM)` with `limit=300` for the first batch, inspect the result, then continue in batches.
## 10. R1 extraction checkpoint (2026-07-17)

- First LLM batch completed successfully: 360 extracted announcements, all with text length and PDF page evidence.
- Current queue: 360 `extracted`, 3,166 `pending`, no `failed` rows.
- Event derivation is active: 178 `hedge_events` and 360 `event_members` were rebuilt automatically.
- Continue `Extract Batch (LLM)` with `limit=300`; after pending reaches zero, run the full verification SQL and close R1.
## 11. R1 quota incident checkpoint (2026-07-17)

- Current data: 708 extracted, 2,678 pending, 139 failed, 1 skipped; 362 derived hedge events.
- The 139 failures share MiniMax HTTP 402 `insufficient_balance_error (1008)`. Pause extraction until the token plan key's available quota is confirmed.
- Recovery order: re-run probe, retry 30 failed rows, then resume 300-row batches after the small retry is stable.
## 12. M3 frontend preview checkpoint (2026-07-18)

- A real-data responsive preview is now merged under `web/`: overview metrics, event stream, announcement stream, filters, evidence drawer, quota table, and PDF links.
- The preview reads `v_ann_flow` and `v_events` with a publishable/anon key only; no service-role credential is shipped to the browser.
- GitHub Pages workflow is present in `.github/workflows/pages.yml`. Repository Pages still needs its Source set to `GitHub Actions` before the first public deployment.

## 13. M3 encoding and density fix (2026-07-18)

- Restored the frontend files as valid UTF-8 after identifying the initial GitHub connector upload transcoding issue.
- Tightened the white research-terminal layout with denser event rows, smaller masthead/metric cards, finer borders, and stronger table hierarchy while preserving mobile stacking.
- Verified the public read-only Supabase views remain available and merged the fix through PR #9.

## 14. M3 shadcn light data terminal direction (2026-07-18)

- Replaced the narrative hero and product-purpose copy with a direct real-data view titled “套保事件”.
- Adopted a shadcn/ui-inspired light system: white background, neutral colors, fine borders, small radii, compact controls, and strong information hierarchy.
- Preserved event/announcement switching, real metrics, filters, evidence drawer, and mobile layout.
- The implementation was synchronized and merged to `main` through PR #11; Pages redeployment is the remaining publication check.

## 15. R1 event rebuild primary-key fix (2026-07-18)

- `build_events.py` previously used the same `|p` suffix for every unmatched progress event under the same company/year/scope, allowing duplicate `event_key` values inside one rebuild batch.
- Unmatched progress keys now append the stable source `ann_id`; a pre-write duplicate-key guard was also added.
- The reported `PostgREST 409 / 23505` occurred after LLM extraction completed, during derived event rebuilding; no new LLM extraction is required for the already completed batch.
- Added a manual `Build Events` workflow so derived-event rebuilds can be retried without invoking the LLM extraction step again.

## 16. R1 recovery checkpoint after PR #11 (2026-07-18)

- Current queue: 1,067 extracted, 2,378 pending, 85 failed, 1 irrelevant, and 1 skipped announcement.
- The source layers remain intact: 1,068 extraction rows and 1,516 quota items.
- `hedge_events` and `event_members` are both empty because the failed full rebuild cleared the derived layer before the duplicate-key insert failed.
- Immediate recovery: run the new `Build Events` workflow on `main`, verify the derived counts, then resume 300-row extraction batches with `retry_failed=false`.

## 17. R1 event rebuild verified (2026-07-18)

- The standalone `Build Events` workflow completed successfully after the deterministic key fix.
- Verified state: 543 events, 1,067 event members, 350 multi-announcement events, zero orphan members, and zero hedge-related extractions without an event membership.
- Resume `Extract Batch (LLM)` with `limit=300`, blank date, and `retry_failed=false`; handle the 85 failed rows only after pending reaches zero.

## 18. R1 closed and M3 formal frontend v1 (2026-07-19)

- R1 queue is closed: 3,516 extracted, 5 irrelevant, 11 skipped, 0 pending, and 0 failed announcements.
- Derived layer rebuilt successfully: 1,721 hedge events across 1,515 companies, including 1,210 multi-announcement events.
- M3 visual direction is fixed as the shadcn-style dense workspace (A) with an on-demand research evidence drawer (C).
- The local frontend now reads all event rows with API pagination, provides search/filter/sort/page controls, lazy-loads the announcement stream, and fetches related announcement evidence only when an event is opened.
- Browser data access continues to use the publishable key and RLS-protected read-only views; no service-role credential is exposed. The formal v1 is pending source synchronization and Pages publication.

## 19. M3 dashboard and export workspace (2026-07-19)

- Replaced the non-interactive sidebar dimension labels with three real workspaces: dashboard, event research, and announcement flow.
- Added client-side aggregates for yearly company/event coverage, industry and enterprise-nature company coverage, scope and approval event distributions, and event-field completeness.
- Added UTF-8 CSV export for the complete current filtered result set in both event and announcement views.
- Dashboard aggregation reuses the fully paginated `v_events` payload, so this stage adds no schema, database-write, or LLM cost.
- GitHub Pages deployment completed successfully from commit `f4efcfef`; the public HTML, JavaScript, CSS, and UTF-8 Chinese text were verified online.

## 20. R2 unattended historical extraction (2026-07-20)

- 2025 backfill completed with 4,920 unique announcement candidates across all 12 months and zero duplicate artifact rows.
- `Extract Batch (LLM)` now runs every 6 hours at Beijing 04:30/10:30/16:30/22:30 and processes at most 600 pending rows per scheduled run.
- Empty queues skip LLM calls and event rebuilds; automatic runs never include failed rows.
- Eight consecutive failures trip a circuit breaker, leave untouched announcements pending, and mark the workflow red for inspection.
- Scheduled extraction shares the repository-wide `cninfo` concurrency group with daily/backfill/audit, so PDF downloads and announcement queries do not overlap.
- The scheduled Daily Pipeline now fetches announcements only; its LLM/build steps remain available on manual dispatch and no longer compete with historical scheduled extraction.

## 23. M3 frontend loading resilience hotfix (2026-07-21)

- Root cause: the initial page loaded every announcement status through 9 paginated requests solely to
  calculate one metric. Together with the 4 event pages, any request that remained pending left the
  interface on its static loading spinner indefinitely because fetch had no timeout.
- Replaced status enumeration with one exact `HEAD` count. This changes only the top “结构化公告” metric;
  the announcement workspace still lazy-loads complete rows, evidence, filters, details, and CSV exports.
- Added a 20-second request timeout, up to three attempts for transient network/429/5xx failures,
  page-by-page loading progress, a 1,000-page safety guard, and global initialization error reporting.
- Removed unused API fields and versioned HTML asset URLs to prevent mixed old/new HTML and JavaScript
  from browser or Pages cache.
- Real public-API bootstrap test passed in 5.4 seconds with 3,281 events and 6,763 extracted announcements.

## 24. 衍生品风险案例库设计检查点（2026-07-25）

- 产品边界：只收录与上市公司期货、期权、远期、掉期、互换、衍生品或套期保值业务
  直接相关的问询、监管措施、处罚、重大损失和权威历史案例；不做一般负面新闻库。
- 产品形态：独立风险案例库，共享 `companies`，但不混入公告事件或定期报告事实表。
- 数据来源：交易所问询/监管/纪律处分、证监会及派出机构处罚/监管措施、上市公司相关
  公告及可回溯到权威原始材料的历史事件。
- 首版必须自动化：官方来源发现 → 关键词召回 → 衍生品相关性闸门 → LLM 结构化抽取
  → 原文证据回验 → 幂等入库。人工仅做抽样验收；手工补充/纠错接口列为后期可选。
- 开发时序：M6a 数据管线可与 M4a 年报 POC 同步推进。两者使用独立迁移、脚本、
  workflow 和测试；迁移编号、公司维表、模型额度统一协调；同一前端模块不并行修改。
- 当前状态：需求与架构已写入 PRD v1.4；尚未创建风险案例数据库迁移、采集脚本、
  Actions 工作流或前端入口。

## 25. M4 定期报告口径与前端架构检查点（2026-07-25）

- 定期报告采用「报告级摘要 + 业务级明细」，不把套期会计等随期变化的事实写入
  `companies`，也不修改现有公告事件数据契约。
- 套期会计报告级状态固定为：已应用、未应用、混合应用、未明确披露、需复核；
  业务级明细记录类别、工具、方法、未应用原因、页码、原文和回验状态。

## 26. M4 正式前端 v0.1 与 40 份报告检查点（2026-07-29）

- 已抽取 40 份 2025FY 报告，形成 40 个报告级业务画像和 265 条数值事实；正式前端
  仅展示数值与引文均已回验的事实，当前未回验事实为 0，精确重复组为 0。
- 生产站新增独立“计划与实际”工作区，按公司×报告×业务范围拆行，支持搜索、年份、
  商品/外汇/利率、套期会计与证据状态筛选，并提供右侧证据详情和 PDF 原文入口。
- 期末衍生金融资产、期末衍生金融负债、期末公允价值净额分别展示；净额仅在同口径
  资产/负债同时可得时勾稽计算，不把报告级损益强行分摊到商品或外汇业务。
- 修复显式多报告提取被默认 `limit=1` 截断、跨页衍生品表头和单位丢失、利率掉期被误分为
  外汇、正文“实际产生损益”换行后漏提四类通用问题，并增加回归测试。
- 珠海港跨页表补回 7 条事实；广宇集团依据年报原文改为“已应用现金流量套期”；
  *ST生物仍保留一项会计政策与业务表述口径的人工判断。
- 本阶段为 **M4 正式前端 v0.1**。达到 120 家优先样本、完成分层人工抽检并稳定筛选/
  导出后升级为 M4 v1.0；公告计划与实际值的自动口径判定属于 M5，当前只显示候选关联。
- 正式前端已由提交 `1962304b` 发布，Pages 工作流成功；如需整体撤回本次发布，
  以发布前 `main` 提交 `9cf4a726` 为回退基线，禁止强推，使用反向提交恢复。
- 晶科能源 2025 年报样本确认未应用套期会计，方法为空，原文未披露未应用原因；
  不得推断其未应用原因。
- 模糊的 `period_pnl` 口径必须拆分：公司披露衍生品综合损益（可能含浮动）、
  处置衍生金融工具投资收益、公允价值变动损益分别记录；衍生金融资产、负债和净额
  也分别记录。
- 定期报告新增期末保证金事实，记录金额、报告日、列示科目、受限状态、业务范围、
  对手方和证据；公告“保证金最高占用额”与年末保证金余额只做 B 级期末快照核验。
- 「计划与实际」主表将期末保证金、公允价值资产、公允价值负债和公允价值净额拆为
  四列。报告级资产/负债合计不得复制为分类事实参与汇总。
- 晶科样本两组勾稽成立：处置投资收益 + 公允价值变动损益 = 综合损益；
  衍生金融资产 - 衍生金融负债 = 期末净账面价值。
- M4 表格解析下一门槛是保留单元格坐标、修正购入/售出列错位并完成数字、引文、
  勾稽三重验证；未通过的数值不能进入图表或 M5。
- 前端将在左侧新增独立「计划与实际」工作区，采用高密度主表 + 右侧证据详情；
  套期会计作为其中的核心维度，不单独设顶级入口。现有「套保事件」和「公告原流」
  保持不变。
- 先在 `web-demo/periodic-actuals/` 制作固定样例的独立本地 Demo；用户确认后才接入
  Supabase 和正式 `web/`。设计基准见
   `docs/superpowers/specs/2026-07-25-periodic-actuals-workspace-design.md`。

## 26. M4 v1.5 契约与六份验证批次（2026-07-26）

- Supabase 已应用 `m4a_periodic_v15_contract`：报告级套期会计字段、事实层级与上下文字段、
  新损益/保证金/资产负债类型，以及业务级 `periodic_hedge_accounting_items` 均已上线；
  RLS、显式授权和 Security Advisor 已验收。
- 安全默认样本改为 6 家验证集；30 家仍保留为下一道 POC 闸门，不自动扩量。
- 定位器升级至 `v2.2`：分别保留业务、套期会计、投资收益、公允价值变动损益、OCI、
  衍生金融资产、负债、保证金和公司专属品种页，并确保 15 个候选页都实际进入模型正文。
- 年报抽取升级为 `periodic-v2.1-multipass` 四段短输出；修复 `LLM_THINKING=off`
  未显式发送 disabled、长 JSON 截断重复重试、横线误判为 0、损失/会计括号负号回验问题。
- 六份验证集均已完成流程。中集 22 条数值中 11 条双回验，格力 7/7，株冶 0/9，
  晶科旧契约 3/18；大北农与博彦当前无可靠数值。流程闸门通过，但表格质量闸门未通过。
- 下一步不扩到 30 份：先逐份人工核验 6 家，重点修复中集/株冶表格单元格与引文对齐、
  晶科旧契约迁移，以及大北农/博彦的无数值判定。

## 27. M4 年报证据规则 v2.2（2026-07-26）

- 年报取证改为程序可独立下载并渲染指定页面；人工截图仅用于下载受限、OCR 失败或
  阅读器页码偏移等例外情况。
- 提示词升级为 `periodic-v2.2-evidence`，明确覆盖“报告期实际损益情况”中的平仓与
  持仓损益，并禁止将千元、万元、亿元、万美元、亿美元换算成基础单位。
- 新增确定性损益句式兜底；株冶 P30 商品衍生品损益 `-366,065,852.86 元` 已双回验入库。
- 株冶 P31 已区分最高保证金 `5.45亿元`、商品最高合约价值 `32.70亿元` 和外汇最高
  合约价值 `1.7亿美元`，纠正了单位换算及保证金/名义本金错分。
- 新增零值单位约束，删除中集 P48 由 `0.00%` 错配出的 3 条金额零；“千元”并非
  中集引文未通过的原因，复杂表格仍需单元格坐标对齐。
- 选择性短批次空结果不再删除旧事实，防止模型偶发空响应造成数据回退。

## 28. M4 六份样本质量闸门通过（2026-07-27）

- 定位器升级至 `v2.3`，抽取契约升级至 `periodic-v2.3-tablecells`。
- 标准衍生品表按单元格坐标和表头读取；同页多表分别识别单位，跨页公允价值表可延续
  表头；合并口径自动排除母公司财务报表项目注释。
- 未通过数值与引文双回验的事实不入库；完整重跑清理旧 `period_pnl`，避免新旧口径并存。
- 会计政策和业务表不再作为实际应用套期会计的充分证据；空白“现金流量套期储备”模板
  不得误判为当期应用。
- 六份样本最终 71 条数值事实，71 条全部双回验：中集 18、格力 14、大北农 10、
  博彦 0、株冶 12、晶科 17；30 份审计时删除株冶 1 条同页同语义重复事实。
- 套期会计结论：格力已应用现金流量套期；大北农、株冶、晶科未应用；博彦当期无
  衍生品投资；中集只披露政策，保守记录为未明确披露。
- 六份样本质量闸门通过。下一步进入 30 份 POC，仍以小批量运行、失败率/耗时记录和
  异常版式复核为边界，不直接扩至全上市公司历史年报。

## 29. M4 三十份年报 POC 完成（2026-07-27）

- 30/30 份 2025FY 年报完成定位和抽取；其余 24 份按 4 个六份批次执行，无 OCR、
  下载或定位失败。
- 数据库现有 198 条定期报告数值事实，198 条全部完成数字与引文双回验；未回验事实、
  完全重复组和披露状态待复核均为 0。
- 披露分布为：23 份有数值、6 份明确提及但无数值、1 份未提及；套期会计业务明细
  22 条，待复核及引文未回验均为 0。
- 补齐多行稀疏表头、财务附注续表投资收益、明确衍生品附注纠正披露状态、同页语义
  去重等规则；排除普通交易性金融资产收益和通用会计政策误入。
- 中稀有色与航民股份候选页已由程序自行渲染核查；博彦“无数值”和大北农数值/未应用
  原因均已确认。本轮不要求用户逐份检查 30 份；下一步生成少量分层人工验收包，
  通过后冻结 v2.3 规则并决定扩量。

## 30. M4 人工验收与 120 家优先池（2026-07-28）

- 人工验收辉隆股份、生益科技、航民股份、中稀有色、博彦科技五份边界样本：
  辉隆确认未应用套期会计；生益的 `-9,950,713.48 元` 改列衍生品处置损益；
  航民排除黄金租赁保证金，并纳入黄金/白银 T+D 投资收益但保留“套保目的未明确”；
  中稀有色改为“提及无数值”，普通交易性金融资产及缺少实际套保证据的衍生工具损益
  不作为套保实际损益；博彦确认报告期无衍生品投资，通用政策不代表实际应用。
- 数据库校正后仍为 30 份报告、197 条数值事实，197 条数字与引文全部回验；
  五份人工样本 `review_status=accepted`。后续抽取默认跳过 accepted 金标准，只有显式
  `--force-reviewed` 才允许覆盖。
- 提示词升级为 `periodic-v2.4-reviewed-boundaries`：黄金租赁/融资担保保证金不得作为
  衍生品保证金，T+D 明确衍生交易可纳入但不得擅自认定套保目的；只有衍生金融工具
  附注、没有实际套保业务上下文时，披露状态进入复核而非自动判为有套保数值。
- 扩量池设为 120 家，商品、外汇、商品+外汇各 40 家，并强制包含原 30 家金标准。
  选择器新增公司主表外键校验；元数据采集支持“2025年年度报告/2025年度报告”两种
  标题，并在同公司同期存在原版和修订版时只保留修订版。
- 120/120 家已取得 2025FY 规范年报元数据；首批 10 份候选页定位成功，无 OCR 或空
  候选页。新增样本按小批量提取和审计推进，不一次性消耗全部模型额度。
- 扩量首批发现模型可能只返回 `<think>` 而没有正文。解析层现将“无 JSON/仅思考正文”
  与“已开始但截断的 JSON”分开：前者最多退避重试两次，后者仍立即停止，防止同一
  长输出重复消耗。
- 优先池新增样本已完成 7 份：新增 53 条数值事实，数字/引文未回验 0、语义重复 0、
  套期会计明细待复核 0；全库现有 37 份已抽取报告、250 条数值事实。
- 扩量探针已修复：套期会计“适用/不适用”勾选方向反转、`百万元` 单位缺失、科目前
  编号造成的语义重复、结构化状态与摘要冲突，以及标准衍生品表“投资收益”列漏取。
- 中国船舶据 P214–215 确认为已应用套期会计：外汇业务为公允价值套期、商品业务为
  现金流量套期；宝钢 P28 数值单位为百万元；东方盛虹补入商品和外汇投资收益两项。
- 当前不直接跑完剩余优先池。先继续已定位的 3 份，再按小批次审计；人工只核验程序
  无法消除的业务边界，不要求逐份检查全部扩量样本。
- 2026-07-29 人工确认爱柯迪与东方盛虹：爱柯迪 P146 的 `100 元` 期货保证金保留为
  期末事实，但不扩展报告级商品业务范围；东方盛虹报告级保持已应用套期会计，商品为
  现金流量套期，外汇业务记为未明确披露而非混合应用。两份均已标记为 `accepted`，
  人工接受样本累计 7 份。德创环保、天奈科技摘要已同步修正。

## 31. M4 正式前端 v0.2 与 2025 年扩量口径（2026-07-29）

- “计划与实际”新增“导出当前结果”：导出完整的当前搜索和筛选结果，不受屏幕可见行
  限制；CSV 使用 UTF-8 BOM，并保留报告、公司、地区、类别、品种、工具、公告候选、
  交易流量、保证金、衍生金融资产/负债/净额、三类损益、套期会计、证据与 PDF 字段。
- 主表新增保守的同口径聚合：只有指标、事实层级、类别、币种、单位和时间口径均相同，
  且每个非空分项可由品种或列示科目明确区分时才求和；详情抽屉仍保留全部分项、页码和
  引文。报告级多事实可能同时包含合计与分项，因此不自动相加；口径不兼容时继续显示
  “N 项事实”，不擅自合计。
- 锐新科技 2025FY 的数据库事实本身正确，旧前端只是没有聚合多分项。修复后商品行显示
  购入 `3,505.10 万元`、售出 `3,558.64 万元`、公允价值变动损益 `53.54 万元`；
  铜、铝分项仍可在证据详情查看。“综合损益”继续保持未披露，不以公允价值变动或 OCI
  代替。
- 2025 年当前数据库口径：公司主表 5,524 家；120 家优先池已有 121 条规范年报元数据
  （含 1 条同公司同期版本记录），40 家已抽取，剩余约 80 家；2025 年套保事件涉及
  1,812 家公司，可作为正式扩量第一波的上限候选，不等于最终需要调用模型的数量。
- 按已测单份端到端约 101 秒估算，优先池剩余 80 份纯串行模型时间约 2.2 小时，计入
  退避、重试和质量审计后预计 3–5 小时计算时间，并预留半至一个工作日完成分层抽检。
  若对 1,812 家候选全部调用模型，纯模型时间约 51 小时，实际预计 60–80 小时；若盲目
  对 5,524 家全量调用则约 155 小时纯模型时间，效率与成本均不合理。
- 正式流程从现在起可按“小批量自动定位 → 仅相关报告调用模型 → 每批质量审计”启动；
  先完成 120 家优先池作为正式质量闸门，再执行全市场确定性定位和候选收缩，不一次性
  对全市场年报调用 LLM。
- 前端 v0.2 已由提交 `fa475393` 非强制快进至 `main`；发布前回退基线为
  `57089bf2`。线上资源版本为 `v=20260729-2`，计划与实际 52 行及锐新科技三项合计
  已验收。

## 32. M4 年报安全自动批处理（2026-07-29）

- 120 家优先池改为每 6 小时自动推进：北京时间 `00:45、06:45、12:45、18:45`
  启动，每轮先定位最多 12 份，再抽取最多 6 份。
- 自动查询硬过滤 `fiscal_year=2025` 和 `report_type=annual`，不会在本轮完成后误处理
  同公司其他年度或半年报。
- 定时任务固定使用 `config/annual_priority_2025.csv`，继续与公告任务共用 `cninfo`
  并发锁；不取消正在运行的任务。若多个任务同时等待，GitHub 可能只保留最近一个
  pending，下一定时周期会继续补处理。
- 定位器默认只处理 `discovered`。下载、模型、解析或写库异常的报告标记为 `failed`，
  当前批次失败停止，后续定时任务自动跳过，避免同一异常报告循环消耗 Token。
- 定位下载和完整抽取都会在实质工作前持久化领取报告；即使 runner 被强制终止或超时，
  报告也保持 `failed`，不会在下一轮再次自动计费。前端只把 `extracted` 报告构建为
  展示行，中断产生的部分写入不会展示，人工恢复时按既有替换规则重建。
- 高级 CLI 的选择性 `--pass` 重跑同样先隐藏报告，成功后恢复其原状态；硬终止时停留
  在 `failed`。失败快照与隔离说明分别尽力写入，不会相互遮蔽原始异常。
- 手动 `locate` 增加 `retry_failed` 选项；只有人工核查后明确勾选，才重新定位失败报告。
  手动 `extract` 仍需勾选 `confirm_llm`，人工接受的 `review_status=accepted` 金标准继续
  默认保护。
- 仓库变量 `PERIODIC_AUTO_ENABLED=false` 可暂停定时年报任务；变量不存在或值不为
  `false` 时默认启用。优先池完成后定时任务正常空跑，不覆盖既有结果。
- 本轮只修改工作流、年报定位/抽取状态机和测试，不修改数据库结构、RLS、公告流程或
  前端展示。

## 33. M6a 风险案例基础纵向切片（2026-07-30）

- Supabase 已应用迁移 `m6a_derivative_risk_cases`，建立
  `risk_source_documents`、`derivative_risk_cases`、`risk_case_documents`、
  `risk_case_evidence` 四张独立表；全部启用 RLS，anon/authenticated 只读，
  service_role 具备 16 项表级 CRUD 权限。迁移后 Security Advisor 为 0 告警。
- 上交所官方监管信息适配器已接入公开 JSONP 接口，当前支持监管问询和监管措施两类，
  兼容顶层 `result` 与旧式 `pageHelp.data`，强制官方 HTTPS 原文链接，并处理 UTF-8、
  分页、重试及无原文链接记录。
- `fetch_risk_documents.py` 默认 dry-run，可下载 PDF/HTML 正文、执行确定性相关性闸门、
  生成带命中片段的 CSV 快照；仅显式 `--write` 时才按 `source_doc_id` 幂等 upsert。
  未知或退市公司代码在写入前置空，避免公司主表外键阻塞官方文档留存。
- 新增手动 `Risk Cases POC (SSE)` workflow。默认不写库；写入必须同时选择
  `write=true` 并填写 `I_UNDERSTAND`。M6a POC 阶段暂不设定时触发，也不调用 LLM。
- 真实 dry-run 已读取 75 份监管措施和 75 份问询函正文，下载失败 1 份。初始规则暴露
  “证券期货市场诚信档案”、舱位互换、应收款远期结算、远期退换货、股票期权激励与
  过渡期权益等误报；加入回归规则后，这 150 份不再误入候选。它们是来源与精度压力
  测试，不是正式案例样本，数据库四表目前均为 0 行。
- 完整 Python 回归 118 项通过；M6 新增契约测试 15 项，覆盖表结构、RLS/权限文本、
  JSONP、URL、相关性边界、候选准备、去重、公司外键安全与 workflow 写入护栏。
- 下一切片按同一契约接入 SZSE、CSRC/派出机构来源，再扩大 2024 年至今的来源扫描，
  形成至少 50 份真正的衍生品风险候选；随后接 LLM 风险分类、官方引文回验与人工分层
  抽检。达到相关性精确率不低于 90% 且每个正式案例均有官方证据后，才完成 M6a 并进入
  M6b 历史扩展、定时增量和前端。
