# 年报安全自动批处理设计

## 目标

在保留现有手动 POC 操作入口的前提下，让 2025 年 120 家优先池按固定节奏自动完成
候选页定位和 LLM 抽取，并避免异常报告反复消耗 Token。

## 运行策略

- 继续使用 `.github/workflows/periodic-poc.yml`，不新增第二套年报工作流。
- 定时任务按 UTC `22:45, 04:45, 10:45, 16:45` 运行，即北京时间
  `06:45、12:45、18:45、00:45`。
- 每轮固定使用 `config/annual_priority_2025.csv`：
  - 定位最多 12 份 `discovered` 报告；
  - 抽取最多 6 份 `located` 报告。
- 定位和抽取查询都硬过滤 `fiscal_year=2025`、`report_type=annual`，优先池完成后不会
  越界处理同公司其他年度或半年报。
- 定时与手动任务继续共用 `cninfo` 并发锁，`cancel-in-progress: false`，避免与公告下载
  同时运行或覆盖在途任务。
- 仓库变量 `PERIODIC_AUTO_ENABLED=false` 时跳过定时任务；变量不存在或不是 `false`
  时默认启用。

## 状态与失败安全

- 定位器默认只读取 `discovered`，不再自动重试 `failed`。
- 手动定位增加 `--retry-failed`；工作流增加 `retry_failed` 复选框，只有用户明确选择时
  才重试失败报告。
- 单份报告抽取过程中发生下载、模型、解析或数据库写入异常时：
  - 在 PDF 下载或 LLM 调用前，先把报告持久化领取为 `failed`；
  - 非 dry-run 将该报告标记为 `failed`，记录截断后的异常摘要；
  - 当前工作流失败停止，保留现场供核查；
  - 后续定时任务跳过该报告，不形成 Token 消耗循环。
- `review_status=accepted` 的人工金标准继续默认保护，不使用 `--force-reviewed`。
- 没有 `discovered` 或 `located` 报告时正常空跑，不修改既有数据。
- 多表写入仍由既有 PostgREST 请求完成，不在本轮引入数据库 RPC；只有最终状态为
  `extracted` 的报告会被前端构建为展示行。中断后的部分写入保持隐藏，人工重试会按既有替换
  规则重建；`accepted` 报告在领取和写入前即被跳过。

## 手动兼容

- 保留 metadata、locate、extract 三个手动阶段及样本集选择。
- 手动 extract 仍必须勾选 `confirm_llm`。
- 手动 locate 只有勾选 `retry_failed` 才包含失败报告。
- 所有运行继续上传 `output/*` 审计快照。

## 验收

- YAML 结构测试覆盖 cron、批量上限、自动启停、并发锁和明确 LLM 确认。
- Python 单元测试覆盖定位查询默认排除失败、显式重试失败、抽取异常隔离和 dry-run
  不写状态。
- 完整年报测试、YAML 解析和 Python 语法检查通过后才发布。
- 发布使用 GitHub 插件，以远端最新 `main` 为父提交做非强制快进；远端变化时停止重核，
  不强推。
