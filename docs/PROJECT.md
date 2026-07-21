# PROJECT.md —— 套保监控（hedge-monitor）项目上下文主文件 v2.0

> 用途：每次与 Claude 开新会话时上传本文件（或放入 Claude Project 知识库）。
> 由你维护；每次会话结束让 Claude 输出更新段落，你替换后 commit。
> 需求的唯一基准是 docs/PRD.md（v1.2），本文件记录"现状与决策"，不复述需求。
> 最后更新：2026-07-20（R2 自动抽取 + M4a 年报 POC）

## 1. 一句话定位

自用专业研究工具：A 股上市公司套保披露的日更监控、结构化抽取与「计划 vs 实际」
对比分析，服务期货研究所研究员的风险管理研究与展业线索需求。单用户，无对外服务。

## 2. 架构与技术栈（R0 定稿）

- **采集**：GitHub Actions（Python）→ 巨潮 hisAnnouncement（标题层）+
  fulltextSearch（正文审计层）。✅ Actions 直连巨潮已长期验证可达。
- **抽取**：MiniMax-M3，OpenAI 兼容接口 `https://api.minimaxi.com/v1`，
  thinking=adaptive，temperature=1.0，强容错 JSON 解析（剥 think 块+括号配对）。
  ⚠️ Actions→MiniMax 可达性待 probe workflow 实测（沿用 7/8 教训：逐源实测）。
- **存储**：Supabase Postgres，PostgREST REST 直写（service_role），
  迁移文件在 db/ 且为唯一事实源（"照仓库即可重建库"）。
- **公司维表**：iFind 手动导出（季度刷新）为权威来源，含企业性质+同花顺三级行业，
  一并解决了旧 #7 ent_type 补全。akshare/东财路线已废弃（Actions 不可达，两次实测证伪）。
- **前端**：GitHub Pages 静态站（M3 重做），数据通路定为 **anon key 直连
  Supabase + RLS 只读**（策略已随 001_init.sql 就位）；读取契约=视图
  v_ann_flow / v_events。设计语言按 PRD 7.6「研报纸感的数据终端」。
- **调度**：daily（北京03:00）负责公告采集；extract 每6小时自动抽取最多600条
  pending；audit（每月1日）自动补漏；backfill / import-companies / probe 手动触发。

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

## 6. 进度清单（2026-07-17 版）

| # | 事项 | 状态 |
|---|------|------|
| R0.1 | 三层数据模型 + 迁移 + 视图 + RLS（db/） | ✅ 新 Supabase 已执行并验收 |
| R0.2 | 采集/审计/抽取/事件/导入五条管线 + 6 workflows | ✅ 已合并 main |
| R0.3 | 用户侧部署 8 步（README 首次部署节） | ✅ 已完成核心部署 |
| R0.4 | MiniMax@Actions 探活结论 | ✅ Actions 探活成功 |
| R1 | 回填 2026 + 清积压 + 首轮 verify.sql 全量回贴 | ✅ 2026 公告积压与失败项已清零，事件层重建完成 |
| R2 | 逐年回填 2025→2021，每年配抽取清零（挂机） | 🔄 2025 已回填，自动抽取已启用 |
| R3 | 抽取质量金标准评测：50 份人工标注 vs 抽取结果，字段级准确率 | ⏸ 建议 R1 后 |
| M3 | 前端正式版（PRD 7.x + 设计语言 7.6，先视觉方向稿再落码） | ✅ v1 已部署：高密度事件研究 + 证据详情 + 数据看板 + CSV 导出 |
| M4a/b | 定期报告（年报+半年报）采集与解析 | 🔄 M4a POC：30份2025FY元数据、2份定位、1份真实抽取 |
| M5 | 计划 vs 实际三维核对（PRD 5.6） | ⏸ 依赖 M4 |

## 7. 风险与已知局限

1. **MiniMax@Actions 未实测**（本周探活出结论；不可达则抽取本地跑，脚本同一套）。
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
8. **年报复杂表格证据**：首份样本 18 条数值中 3 条数字+引文双回验通过，15 条表格值仅数字回验通过；
   未解决表格原文对齐前不得批量扩张，也不得让未双回验数值进入图表。

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
