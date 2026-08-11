# Risk Monitoring Early Production Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将风险案例监控接入正式网站，并以严格发布闸门清理媒体误报，同时保持公开数据只读、私有线索不可从浏览器访问。

**Architecture:** 正式前端从 Supabase 读取四张官方风险表和两张已发布媒体表，在浏览器内归一化、去重并优先展示官方证据；私有媒体线索只由服务端发布脚本读取。发布脚本采用保守的公司身份、已发生事实和重要性校验，并可将既有误报撤回。数据库通过显式授权和 RLS 保证匿名用户仅能读取公开表。

**Tech Stack:** Python 3、Node.js ES modules、原生 HTML/CSS/JavaScript、Supabase Postgres/PostgREST、GitHub Actions/Pages。

---

### Task 1: 收紧媒体风险案例发布闸门并清理既有误报

**Files:**
- Modify: `scripts/publish_risk_media_reports.py`
- Modify: `tests/test_risk_media_public.py`

1. 先为公司代码/名称冲突、通用风险提示、仅外汇损失但无衍生品实际损失、重大损失事实、既有误报撤回和幂等重跑编写失败测试。
2. 运行 `python -m unittest tests.test_risk_media_public`，确认新增测试因缺少闸门或撤回逻辑失败。
3. 实现公司身份校验、实际衍生品不利事件校验、重要性校验和既有公开记录 reconciliation；保留江特电机、仙乐健康，撤回玲珑轮胎和公司错配记录。
4. 再次运行测试并确认通过。

### Task 2: 将风险公开表权限收紧为匿名只读

**Files:**
- Create: `db/009_risk_public_readonly.sql`
- Modify: `db/verify.sql`
- Modify: `tests/test_risk_schema.py`

1. 先增加结构测试，要求官方四表和公开媒体两表仅向 `anon`/`authenticated` 授予 `SELECT`，私有线索表不得公开授权。
2. 运行 `python -m unittest tests.test_risk_schema`，确认迁移尚不存在时测试失败。
3. 编写可重复执行的权限迁移，并扩充数据库核验 SQL。
4. 运行结构测试；随后通过 Supabase migration 应用到生产库，再执行授权查询、RLS 检查和安全顾问检查。

### Task 3: 把风险案例监控接入正式网站

**Files:**
- Create: `web/risk.js`
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Create: `tests/test_risk_production_logic.mjs`
- Modify: `tests/test_web_structure.mjs`

1. 先为官方/媒体数据归一化、官方优先去重、筛选、排序和 CSV 导出编写失败测试。
2. 运行 Node 测试确认失败。
3. 实现 `HedgeRisk` 模块，读取四张官方表和两张公开媒体表；增加左侧入口、核心指标、筛选器、高密度表格、右侧详情、证据链接、导出、进度、重试和明确错误状态。
4. 更新资源版本号，接入全局刷新，并补齐桌面和移动端样式。
5. 运行逻辑测试、结构测试和 `node --check`。

### Task 4: 真实数据启动测试与生产数据清理

**Files:**
- Create: `tests/test_risk_production_bootstrap.mjs`
- Modify: `scripts/publish_risk_media_reports.py`

1. 增加真实公开 API 启动测试，要求 60 秒内完成、官方空表可正常呈现、仅发布状态媒体记录可见、私有线索表匿名访问失败。
2. 使用服务角色运行一次发布 reconciliation，撤回不符合新闸门的既有公开媒体记录。
3. 核验生产库保留的媒体案例、官方案例数量、公开授权和安全顾问结果。
4. 运行所有 Python/Node 风险测试与现有前端测试。

### Task 5: 文档、原子发布和线上验收

**Files:**
- Modify: `docs/PROJECT.md`
- Create: `docs/worklogs/worklog_2026-08-11.md`

1. 更新当前阶段、真实数据口径、M6a/M6b 进度、已知限制和下一步官方渠道建设。
2. 进行完整测试、密钥扫描和变更范围检查。
3. 以最新远端 `main` 为父提交，通过 GitHub 连接器创建单一非强制提交并更新 `main`；远端基线变化时停止并重新核对，不强推。
4. 等待 GitHub Pages 部署，核验 `https://www.hedgemonitor.site/` 的资源版本、风险入口、真实数据、CSV、详情抽屉、移动端和错误处理。

