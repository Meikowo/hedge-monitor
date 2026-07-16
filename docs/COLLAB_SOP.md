# COLLAB_SOP.md v2.0 —— 会话协作手册（人 + 网页版 Claude + git push 自动化）

> 适用于 hedge-monitor 新仓库。对话是一次性的，仓库文档才是记忆。

## 1. 原则

- 只沉淀三样东西：**PROJECT.md**（慢变的全局事实与决策）、**worklog**（每次会话
  的事件/决策/交付/验收）、**schema_snapshot.md**（数据契约）。聊天记录本身不保存。
- 每次会话**只定一个目标**，做完收口，不顺手扩散。
- Claude 的交付形式只有两种，二选一并明说：
  1. **多文件改动** → 打成一个 zip，附「文件 → 仓库内路径」清单；
  2. **单文件改动** → 明确说"改动的是 `路径/文件名`"，并给出**可整体覆盖**的完整
     文件。永不接受"改第 X 行"式口头补丁。
- 每个交付必须附**验收步骤**（SQL / 命令 / 页面检查点）+ 涉及数据变更时的回滚说明。
- 验收不过：把报错和现象**原样**贴回会话（Actions 日志段落、SQL 输出、截图均可）。

## 2. 新会话开场模板（复制即用）

```
项目：hedge-monitor（上下文见附件 PROJECT.md，数据契约见 schema_snapshot.md）
本次唯一目标：______
本次附加文件：______（如最新 worklog、相关脚本、报错日志）
不许改动：______（例：workflows/、db/ 既有迁移、config 定稿文件）
完成标准：______（例：verify.sql V6 段 pending=0）
请先复述你对目标的理解和实施计划，我确认后再开始产出。
```

## 3. 会话收尾模板（复制即用）

```
本次会话收尾。请输出两份内容：
1) docs/worklogs/worklog_YYYY-MM-DD.md —— 沿用既有格式
   （事件与根因 / 决策 / 交付 / 验收 / 进度表更新 / 教训）
2) PROJECT.md 需要更新的段落，并标明各段替换到原文件的哪个位置
我会把它们 commit 进仓库。
```

同一天多次会话，worklog 文件名加后缀 `-2`。

## 4. 交付与落地流程

1. Claude 生成完整文件（多文件打 zip）+ 放置路径清单 + 验收步骤
2. 你下载 → 覆盖到对应路径 → `git add -A && git commit -m "..." && git push`
3. GitHub Actions 自动执行（或按指示手动触发 workflow）
4. 需要 SQL 的部分：Supabase SQL Editor 按给出的文件顺序粘贴执行
5. 按验收步骤检查；异常原样贴回会话
6. 用 §3 模板收尾，worklog 与 PROJECT.md 更新段 commit 进仓库

## 5. 对 Claude 的固定工程要求

- 文件小而独立：单文件 < 400 行；前端业务文件总数 < 10 个
- 配置类文件（workflow YAML / db 迁移 / keywords.yml 结构 / 前端构建配置）
  一次定稿，之后非必要不动，日常只改业务文件
- 所有脚本标准：自动加载 .env、**幂等可无限重跑**、网络调用指数退避、
  运行时在 output/ 落 CSV 快照备查（Actions 中作为 artifact 保留）
- 抽取提示词改动必须递增 `PROMPT_VERSION`
- 数据库变更走新增迁移文件（002_、003_…），永不回改已执行过的迁移；
  变更后同步更新 docs/schema_snapshot.md

## 6. 秘钥红线与安全自查

红线：任何 key 的**值**永不出现在对话、仓库文件、前端代码里；对话里只说 key 的
名字与存放位置。前端只可使用 anon key，前提是 RLS 只读策略在位（001_init.sql §7）。

自查命令（仓库根目录）：

```bash
git check-ignore .env              # 应有输出（.env 已被忽略）
git log --all --oneline -- .env    # 应为空（历史上从未提交过 .env）
```

若 service role key 或 LLM key 疑似泄露：立即在对应后台轮换，并同步更新
GitHub Secrets 与本地 .env。

## 7. Claude Projects（可选）

若套餐支持：新建 Project「hedge-monitor」，把 PROJECT.md、PRD.md、
schema_snapshot.md 放入 Project knowledge，新对话自动携带上下文；
文件变更后记得手动替换知识库版本。没有 Projects 时按 §2 每次上传，效果相同。
