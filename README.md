# hedge-monitor —— A股上市公司套期保值监控

自用专业研究工具：套保公告日更监控、结构化抽取（额度/口径/品种/场所/审批）、
事件层去重、计划 vs 实际对比分析。需求基准见 `docs/PRD.md`（v1.2），
项目上下文见 `docs/PROJECT.md`，协作方式见 `docs/COLLAB_SOP.md`。

## 架构一图流

```
巨潮资讯 ──┐
           ├─ GitHub Actions（定时/手动）── Python 脚本 ──► Supabase Postgres
MiniMax-M3 ┘                                                  │  (RLS: anon 只读)
                                                              ▼
iFind 导出(xlsx, 季度手动) ─ import workflow ─► companies     GitHub Pages 前端(M3)
```

数据三层：`announcements`（公告层）→ `extractions` + `quota_items`（抽取层）
→ `hedge_events` + `event_members`（事件层，去重后的"一次套保决策"）。

## 目录

```
config/keywords.yml     召回词表（查全率的单一事实源，加词即生效）
data/                   iFind 公司表（季度替换后跑 import workflow）
db/                     000_reset → 001_init → verify（SQL Editor 手动执行）
scripts/                common/cninfo 基础层 + 5 个业务脚本
.github/workflows/      daily / backfill / extract / audit / import-companies / probe
docs/                   PRD、PROJECT、COLLAB_SOP、schema_snapshot、worklogs
output/                 运行快照（gitignore，Actions 里以 artifact 保留）
```

## 首次部署（按顺序做，约 30 分钟人工 + 数小时挂机）

1. **仓库**：旧代码存档到分支再覆盖 main
   ```bash
   cd hedge-monitor
   git checkout -b legacy-demo && git push origin legacy-demo   # 存档旧 demo
   git checkout main
   # 删除 main 下全部旧文件（保留 .git），把本包全部内容复制进来
   git add -A && git commit -m "R0: 重建底座（三层数据模型+全自动管线）" && git push
   ```
   注意：旧 Pages demo 会失效，旧代码完整保留在 `legacy-demo` 分支。

2. **数据库**：Supabase → SQL Editor，先执行 `db/000_reset.sql`（⚠️ 销毁旧表，
   数据均可由管线重建），再执行 `db/001_init.sql`。跑 `db/verify.sql` 的
   V1/V2 段确认 6 张表 RLS 全开、6 条 anon 只读策略就位。

3. **秘钥**（名字固定，值只出现在这两处）：
   - GitHub repo → Settings → Secrets and variables → Actions，新建 3 个：
     `SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`LLM_API_KEY`（= MiniMax key）
   - 本地：`cp .env.example .env` 后填同样 3 个值（本地跑脚本才需要）

4. **探活**：Actions → *Probe MiniMax Reachability* → Run。
   绿色 = 抽取跑 Actions；红色 = 把日志贴回会话，抽取降级本地跑（脚本完全同一套）。

5. **公司维表**：Actions → *Import Companies (iFind)*，先 `dry_run=true` 看统计，
   正常后 `dry_run=false` 正式导入。验收：`verify.sql` V3 段，total=5524。

6. **回填 2026**：Actions → *Backfill Announcements*，year=2026。
   跑完看 V4/V5 段：应有数千条、覆盖 2026-01-01 至今。

7. **清抽取积压**：Actions → *Extract Batch (LLM)*，limit=300，反复触发直到
   V4 段 pending≈0（每轮约 1–2.5 小时，取决于 MiniMax 响应速度）。

8. 之后 **daily 每天北京 03:00 自动接管**（抓3天窗+抽60条+重建事件层），
   **audit 每月1日自动补捞漏检**。历史年份（2025→2021）逐年重复第 6–7 步。

## 日常运维

| 场景 | 操作 |
|---|---|
| 看每天跑没跑 | Actions → Daily Pipeline 的运行记录（快照在 artifact 里） |
| 发现漏检某类表述 | `config/keywords.yml` 加词 → push，次日生效；历史用 backfill 补 |
| 换季度公司表 | 新 xlsx 放 `data/`（命名 companies_ifind_YYYYMMDD.xlsx）→ push → 跑 import workflow 并填新路径 |
| 改抽取提示词 | 改 `scripts/prompt_extract.py` 并**递增 PROMPT_VERSION** |
| 重抽某几条 | 本地 `python scripts/extract_announcements.py --ids <ann_id> ...` |
| Supabase 保活 | daily 每日写库即天然保活；若 Actions 断档超一周需手动进后台看一眼 |

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env   # 填值
python scripts/fetch_announcements.py daily --days 3 --dry-run
python scripts/extract_announcements.py --limit 5 --dry-run
python scripts/build_events.py --dry-run
```

## 故障排查

- **fetch 报"非JSON响应，疑似被临时风控"**：巨潮临时限流，脚本会自动退避重试；
  若整轮失败，等 1 小时重跑同一 workflow 即可（幂等，不会重复入库）。
- **extract 大量 failed**：先跑 probe 确认可达性；确认后用 extract workflow
  的 `retry_failed=true` 重试。失败原因在 `announcements.note` 列。
- **事件分组看着不对**：`hedge_events` 是派生表，改 `scripts/build_events.py`
  规则后重跑即可全量重算，不影响底层数据。
- 其他异常：把 Actions 日志相关段落 + `verify.sql` 对应段结果，按
  `docs/COLLAB_SOP.md` 的方式原样贴回下次会话。
