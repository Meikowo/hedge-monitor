# A股套保公告监控 · Supabase Lite

这是一个最小可运行版本：

- Python 爬虫从巨潮资讯抓取套保相关公告；
- 抓到的数据写入 Supabase；
- 静态 HTML 直接读取 Supabase 并展示真实公告；
- 第一版不下载 PDF，只保存巨潮 PDF 原链接，避免本地和云端存储压力。

> 不要把 `SUPABASE_SERVICE_ROLE_KEY` 放进 HTML、GitHub 仓库明文或任何公开位置。

---

## 1. 你需要准备什么

需要从 Supabase 拿到：

1. `Project URL`：形如 `https://xxxx.supabase.co`
2. `anon public key`：给 HTML 前端只读使用
3. `service_role key`：只给 Python 爬虫写入使用，必须放在 `.env` 或 GitHub Secrets

在 Supabase 后台大致路径通常是：

```text
Project Settings → API
```

如果后台 UI 后续变化，只要找到 Project URL、anon key、service_role key 即可。

---

## 2. 创建表结构

打开：

```text
Supabase Dashboard → SQL Editor → New Query
```

把 `supabase/schema.sql` 内容复制进去执行。

执行后会创建：

- `announcements`
- `annual_reports`
- `tips`
- `hedge_events`
- `extraction_evidence`
- `v_announcements_with_events`

并开启 RLS：前端 anon key 只允许读取，不允许写入。

---

## 3. 本地运行爬虫写入 Supabase

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量文件：

```bash
cp .env.example .env
```

填写：

```env
SUPABASE_URL=https://你的项目.supabase.co
SUPABASE_SERVICE_ROLE_KEY=你的 service_role key
```

运行最近 3 天公告抓取：

```bash
python scripts/ingest_to_supabase.py daily --days 3
```

运行全文补捞：

```bash
python scripts/ingest_to_supabase.py fulltext --days 7 --keyword 套期保值
```

抓某一年年报，例如 2025 年年报：

```bash
python scripts/ingest_to_supabase.py annual --year 2025
```

历史回填：

```bash
python scripts/ingest_to_supabase.py backfill --start 2025-01 --end 2025-12
```

---

## 4. 打开 HTML 看真实数据

直接打开：

```text
static/index.html
```

在页面右侧填写：

- Supabase URL
- Supabase anon public key

点击“保存连接配置”，再点击“加载真实公告”。

也可以用本地静态服务打开：

```bash
python -m http.server 8000
```

然后访问：

```text
http://127.0.0.1:8000/static/index.html
```

---

## 5. GitHub Actions 定时抓取

把本项目推到 GitHub 后，在仓库中添加 Secrets：

```text
Settings → Secrets and variables → Actions → New repository secret
```

添加：

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

工作流文件已在：

```text
.github/workflows/daily-cninfo.yml
```

它会每天自动运行，也可以在 Actions 页面手动触发。

---

## 6. 当前版本能力边界

当前版本已经能做到：

- 抓取真实巨潮公告标题层结果；
- 写入 Supabase；
- HTML 展示真实公告；
- 打开巨潮 PDF 原文；
- 基于标题生成轻量提示；
- 不下载大量 PDF。

当前版本还没有做到：

- PDF 正文解析；
- 金额、期限、审批层级的精确抽取；
- 原文证据链；
- LLM 结构化抽取；
- 年报深度解析。

后续建议加一个“按需解析 PDF”按钮：用户点某条公告时，临时下载 PDF 到内存，解析文本，提取字段和证据，然后只把抽取结果写入 Supabase，不长期保存 PDF。

---

## 7. 文件说明

```text
cninfo_hedging_crawler.py          原始巨潮采集逻辑
scripts/ingest_to_supabase.py      把采集结果写入 Supabase
supabase/schema.sql                Supabase 建表和 RLS SQL
static/index.html                  读取 Supabase 的前端页面
.github/workflows/daily-cninfo.yml GitHub Actions 定时任务
.env.example                       环境变量示例
requirements.txt                   Python 依赖
```
