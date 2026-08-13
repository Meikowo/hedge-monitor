# M4 年报吞吐优化设计

## 目标

在不改变 2025 年正式池、抽取口径、数据库结构和质量闸门的前提下，移除每 6 小时重复执行的全市场元数据扫描，并将年报自动抽取吞吐由每天最多 72 家提高到每天最多 144 家。

## 调度设计

- Periodic Reports Formal 保留每天四次队列处理，时间仍为北京时间 00:45、06:45、12:45、18:45。
- 四次队列任务仅执行：进度快照、候选页定位最多 48 家、LLM 抽取最多 36 家、结束进度快照。
- 新增每天一次的元数据扫描任务，北京时间 05:20 执行全市场 2025 年年报扫描并按 config/annual_formal_2025.csv 过滤写入。
- 两类任务继续共用 cninfo concurrency group，避免同时访问巨潮接口或争用同一批报告。
- 手工 metadata / locate / extract 入口及其确认规则保持不变。

## 安全与失败处理

- 不修改失败隔离、三次失败熔断、failed/needs_ocr 状态或显式重试规则。
- 不修改 LLM_THINKING=off、模型密钥或 Supabase 权限。
- 不增加并行 LLM 调用；36 家仍按现有脚本串行处理，因此不会引入并发写入竞争。
- 元数据任务失败不阻塞之后的定位和抽取任务；队列继续消费数据库中已有的 discovered 和 located 报告。

## 验收标准

- 工作流存在每日一次的 metadata schedule 和每天四次的 queue schedule。
- queue schedule 不执行 fetch_periodic_reports.py --strategy full。
- queue schedule 保持定位上限 48，抽取上限变为 36。
- metadata schedule 只执行进度、全市场扫描和结果快照，不调用定位器或 LLM。
- 现有 Python 全量测试、前端结构/逻辑测试全部通过。

