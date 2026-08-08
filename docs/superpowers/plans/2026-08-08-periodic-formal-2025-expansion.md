# 2025 Annual Report Formal Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“计划与实际”从 119 家稳定扩展到固定的 1,812 家 2025 年套保公告公司，并建立自动发现、定位、提取、失败隔离和进度报告能力。

**Architecture:** 使用提交到仓库的静态公司池作为唯一范围输入。定时工作流每 6 小时先做全市场年报元数据扫描并过滤公司池，再定位最多 48 份、提取最多 18 份；提取器隔离单份失败，并在单批累计 3 份失败时熔断。现有 Supabase 表和前端契约保持不变。

**Tech Stack:** Python 3.12、`unittest`、Supabase PostgREST、巨潮资讯适配器、GitHub Actions、静态 CSV 配置。

## Global Constraints

- 第一阶段范围固定为 `hedge_events.anchor_year = 2025` 的 1,812 家公司。
- 已 `extracted`、`skipped` 或人工 `accepted` 的结果不得被普通定时任务覆盖。
- `failed` 不自动重试；仅显式 `report_id` 恢复。
- 定时频率保持每 6 小时，定位上限 48，初始提取上限 18。
- 单批累计 3 份提取失败后停止剩余 LLM 调用。
- 不修改数据库表结构、RLS、公告事件数据或前端字段契约。
- 不提交 `.env`、API Key 或 service role key。

---

### Task 1: 固化 2025 年正式公司池

**Files:**
- Create: `scripts/select_periodic_formal.py`
- Create: `tests/test_periodic_formal.py`
- Create: `config/annual_formal_2025.csv`

**Interfaces:**
- Consumes: `sb_select("v_events", ...)` 和 `sb_select("companies", ...)`。
- Produces: `aggregate_formal(event_rows, company_codes, anchor_year=2025) -> list[dict]`；CSV 列为 `code,name,scope_group,industry,ent_type,event_count,latest_ann_date,locator_terms`。

- [ ] **Step 1: Write failing tests for scope filtering, uniqueness and deterministic ordering**

在 `tests/test_periodic_formal.py` 使用手写事件记录，断言非 2025 事件、B 股代码和公司主表缺失代码被排除；同一代码多个事件聚合为一行；输出按代码稳定排序。

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_periodic_formal.PeriodicFormalPoolTest -v`

Expected: FAIL because `scripts.select_periodic_formal` does not exist.

- [ ] **Step 3: Implement the formal selector**

实现纯函数 `aggregate_formal(...)`，查询时显式传入 `anchor_year=eq.2025`，写 CSV 前验证代码非空、唯一且每行 `event_count >= 1`；命令行增加 `--expected-count`，默认 1812，不匹配时以非零退出。

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_periodic_formal.PeriodicFormalPoolTest -v`

Expected: all pool tests PASS.

- [ ] **Step 5: Generate and verify the production snapshot**

Run: `python scripts/select_periodic_formal.py --anchor-year 2025 --expected-count 1812 --output config/annual_formal_2025.csv`

Verify: CSV has exactly 1,812 unique codes, no empty codes and no duplicate codes.

### Task 2: 增加公司级进度报告

**Files:**
- Create: `scripts/periodic_progress.py`
- Modify: `tests/test_periodic_formal.py`

**Interfaces:**
- Consumes: 正式池 CSV、2025 annual `periodic_reports`、`periodic_derivatives.review_status`。
- Produces: `summarize_progress(target_codes, report_rows, derivative_rows) -> dict` 和 `output/periodic_progress_*.json`。

- [ ] **Step 1: Write failing tests for canonical company status and counts**

测试一家公司同时有旧版 `skipped` 和修订版 `extracted` 时只计入 `extracted`；没有报告的公司计入 `missing`；结果包含 target、discovered、located、extracted、skipped、failed、needs_ocr、missing、accepted 和 verification_rate。

- [ ] **Step 2: Run the progress tests and verify RED**

Run: `python -m unittest tests.test_periodic_formal.PeriodicProgressTest -v`

Expected: FAIL because progress functions do not exist.

- [ ] **Step 3: Implement progress aggregation and CLI**

按公司归并报告状态，状态优先级为 `extracted > located > discovered > needs_ocr > failed > skipped`；从数据库读取全部 2025 annual 报告后在本地按正式池过滤，避免构造过长 URL；输出 JSON 快照和一行可读摘要。

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_periodic_formal.PeriodicProgressTest -v`

Expected: all progress tests PASS.

### Task 3: 提取失败隔离与三次失败熔断

**Files:**
- Modify: `scripts/extract_periodic_reports.py`
- Modify: `tests/test_periodic_formal.py`

**Interfaces:**
- Consumes: 查询得到的 report 列表和现有 `extract_one_report(...)`。
- Produces: `run_extraction_batch(..., failure_limit=3) -> BatchResult`，其中包含成功记录、失败摘要、是否熔断。

- [ ] **Step 1: Write failing behavior tests**

覆盖三种行为：第一份失败后第二份继续；第三份失败后第四份不调用；失败报告被隔离而成功报告保留。测试只替换外部 PDF/LLM 边界，断言真实批次控制结果。

- [ ] **Step 2: Run circuit-breaker tests and verify RED**

Run: `python -m unittest tests.test_periodic_formal.PeriodicExtractionBatchTest -v`

Expected: FAIL because `run_extraction_batch` is missing.

- [ ] **Step 3: Implement minimal batch controller**

将 `main()` 的循环抽为批次函数；每份异常调用现有 `record_report_failure` 后继续；累计 3 份失败时写入 `circuit_breaker` 摘要并停止。普通查询仍只选 `located`，显式 `--report-id` 仍绕过状态和 limit。

- [ ] **Step 4: Make workflow failure explicit after preserving partial success**

批次熔断后先写完整 `periodic_extract_run` 快照，再以非零状态结束，让 GitHub Actions 明确显示失败；少于 3 份失败的批次正常完成并在摘要中显示失败数。

- [ ] **Step 5: Run focused and existing periodic tests**

Run: `python -m unittest tests.test_periodic_formal.PeriodicExtractionBatchTest tests.test_periodic -v`

Expected: all tests PASS.

### Task 4: 将 GitHub Actions 切换到正式池

**Files:**
- Modify: `.github/workflows/periodic-poc.yml`
- Modify: `tests/test_periodic_formal.py`

**Interfaces:**
- Consumes: `config/annual_formal_2025.csv`。
- Produces: 定时 metadata → locate → extract → progress 流程；手动 `report_id` 恢复入口。

- [ ] **Step 1: Write failing workflow behavior tests**

解析 YAML 并断言：schedule 使用正式池；metadata 带 `--strategy full --write`；定位上限 48；提取上限 18；前后运行进度脚本；手动输入支持 `formal1812` 和可选 `report_id`；定时任务不带 `--retry-failed`。

- [ ] **Step 2: Run workflow test and verify RED**

Run: `python -m unittest tests.test_periodic_formal.PeriodicFormalWorkflowTest -v`

Expected: FAIL against the current priority120 workflow.

- [ ] **Step 3: Update the workflow**

定时任务每 6 小时按顺序执行全市场元数据发现、48 份定位、18 份提取和进度快照；`timeout-minutes` 设为 330；保留 `concurrency.group=cninfo` 与 `cancel-in-progress=false`。手动模式将可选 `report_id` 安全组装为 `--report-id` 参数，仅显式使用时恢复失败报告。

- [ ] **Step 4: Run workflow and regression tests**

Run: `python -m unittest tests.test_periodic_formal.PeriodicFormalWorkflowTest tests.test_periodic -v`

Expected: all tests PASS after updating obsolete priority120 expectations in existing workflow tests to the approved formal values.

### Task 5: 文档、全量验证与发布

**Files:**
- Modify: `docs/PROJECT.md`
- Create: `docs/worklogs/worklog_2026-08-08.md`
- Modify: `docs/superpowers/plans/2026-08-08-periodic-formal-2025-expansion.md`

**Interfaces:**
- Produces: 可审计的项目状态、实施记录和远端原子提交。

- [ ] **Step 1: Update project status and worklog**

记录 1,812 家范围、当前 119 家基线、正式批量参数、失败规则、回退提交和下一步“无公告但有衍生品披露”评估门槛；不得把尚未运行的生产批次写成已完成。

- [ ] **Step 2: Run the full local verification suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Run each existing Node structure/logic test with the bundled Node runtime.

Expected: all Python and Node tests PASS; warnings may only be pre-existing library deprecation output.

- [ ] **Step 3: Validate the snapshot and secret boundary**

检查正式 CSV 为 1,812 个唯一代码；扫描本次文件确保没有 `SUPABASE_SERVICE_ROLE_KEY`、真实 API Key 或 `.env` 内容。

- [ ] **Step 4: Publish atomically through the GitHub connector**

以最新远端 `main` 为父提交，只上传本计划涉及的代码、测试、配置和文档文件；创建 commit 后重新确认远端基线未变化，再以 `force=false` 更新 `main`。

- [ ] **Step 5: Verify GitHub Actions and recover 南钢股份**

确认发布后的 workflow 可见且配置为正式池。先用手动 `report_id=1225011770`、stage=`extract`、confirm_llm=true 恢复南钢股份；若连接器不能触发 workflow，向用户提供精确点击参数。随后观察首个正式定时批次，不把工作流触发失败重复三次以上。

