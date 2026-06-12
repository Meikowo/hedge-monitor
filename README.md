# A股套保公告监控 · 端到端实操手册

> 你的角色：非程序员。  
> 我的角色：把这件事一次跑通。  
> 你只需要做 4 件事：(1) 建 Supabase 项目 → (2) 跑一段 SQL → (3) 把两个 key 发给我 → (4) 我把数据写进你的 Supabase + 验证网页。

---

## 0. 30 秒理解整个项目长什么样

```
你/自动机器人 ──→ Python 爬虫(每天跑)
                     ↓
                  巨潮资讯网(去抓公告)
                     ↓
                  Supabase 在线数据库 ←──── 你在网页里看到真实数据
                     ↑                        ↑
                  schema.sql(我已写好)        static/index.html(我已加好 Supabase 按钮)
```

- **Python 爬虫** = 跑在 GitHub Actions 上(免费服务器)，每天 20:30 自动抓
- **Supabase** = 在线数据库，免费层够用
- **HTML** = 你电脑上双击打开的网页，右下角"🔌 Supabase"按钮点一下就联通
- **不要在 HTML 里放 service_role key**，那个只能放 Python 的 .env 里

---

## 1. 你现在马上要做的事

### 第 1 步：注册并创建 Supabase 项目（5 分钟）

打开：https://supabase.com/

- 注册或登录
- 点 **"New Project"**
- 名字随便起，比如 `hedge-monitor`
- **Database Password** 自己设一个（记住！不会再次显示）
- **Region** 选 `Singapore` 或 `Tokyo`（离你近）
- 等 1-2 分钟初始化完成

### 第 2 步：执行建表 SQL（2 分钟）

进入项目后：
- 左侧菜单 → **SQL Editor**
- 点 **"New query"**
- 把我给你的 `supabase/schema.sql` 文件**全部内容复制进去**
- 点右下角 **"Run"**
- 看到 "Success. No rows returned" 或类似绿色成功提示就行

这一步会建 5 张表 + 1 个视图 + 启用 RLS 安全策略（前端只能读，不能写）。

### 第 3 步：拿到 3 个 key（1 分钟）

- 左侧菜单 → **Project Settings**（齿轮图标）→ **API Keys**
  - 新版界面可能叫 **API Keys** 或 **Connect**
  - 老界面可能在 **API** 下

你要复制这 3 个：

| 名称 | 用途 | 能不能发给我 |
|---|---|---|
| **Project URL** | 形如 `https://xxxxx.supabase.co` | ✅ 可以 |
| **anon public key**（也叫 publishable key） | HTML 前端只读用 | ✅ 可以 |
| **service_role / secret key** | Python 写数据用 | ❌ **绝对不要**发给我 |

> 新版 Supabase 把 key 改名为 `publishable`（前端用）和 `secret`（后端用）；老项目里你可能看到 `anon` 和 `service_role`。不管名字怎么变，**短的那个是前端只读，长得"权限大"的那个是后端写入**。

### 第 4 步：把 Project URL 和 anon key 发给我

只发这两个，service_role 自己留着。发完我会：
1. 在沙箱里跑一次爬虫，把真实公告写进你的 Supabase
2. 让你在 Table Editor 里能看到数据
3. 帮你验证 HTML 能拉到这些数据
4. 给你写好 GitHub Actions 配置文件（之后每天自动跑）

---

## 2. 你电脑本地需要准备什么

只为了打开 HTML 验证（不需要装 Python）：

- 任何现代浏览器（Chrome / Edge / Safari）
- **不要**直接双击 HTML 在 `file://` 打开（Supabase 跨域会失败）
- 正确做法：在 HTML 所在目录用命令行跑：
  ```bash
  cd /path/to/hedge-monitor/static
  python3 -m http.server 8000
  ```
  然后浏览器访问 `http://127.0.0.1:8000`

如果你要本地跑爬虫（可选，第一版可以让 GitHub Actions 帮你跑）：

- Python 3.10+
- 安装依赖：`pip install -r requirements.txt`

---

## 3. 项目文件结构

```
hedge-monitor/
├── cninfo_hedging_crawler.py     ← 巨潮爬虫(原始版本，一行没改)
├── scripts/
│   └── ingest_to_supabase.py     ← 把爬虫结果写入 Supabase
├── supabase/
│   └── schema.sql                ← 在 Supabase SQL Editor 跑这段
├── static/
│   └── index.html                ← 你打开的网页(原版 + 已加 Supabase 桥接)
├── docs/
│   ├── hedge_monitor_startup.md  ← 详细启动文档(Claude 写的)
│   └── README_lite_template.md   ← Supabase Lite 原始 README
├── .github/workflows/
│   └── daily-cninfo.yml          ← GitHub Actions 定时任务(我帮你配)
├── .env.example                  ← 环境变量模板(你复制成 .env)
├── requirements.txt              ← Python 依赖
└── README.md                     ← 本文件
```

---

## 4. 跑通后的"日常"流程

跑通一次后，什么都不用做：

```
每天 20:30 (北京时间)
  ↓
GitHub Actions 自动跑爬虫
  ↓
抓当天巨潮公告 → 写进 Supabase
  ↓
你打开 HTML → 看到今天的新公告
```

---

## 5. 常见问题快速对答

**Q: anon key 发给别人安全吗？**  
A: 安全。Supabase 官方明确说 anon key 就是给前端用的，RLS 策略会限制它只能读公开数据。

**Q: service_role key 泄露了怎么办？**  
A: 立刻去 Supabase 控制台 Reset 它，然后更新 .env 和 GitHub Secrets。这个 key 能写所有表。

**Q: Supabase 免费层够用吗？**  
A: 第一版完全够。免费层：500MB 数据库、1GB 存储、5GB 出口流量、2 个项目。只存公告元数据不存 PDF 的话，跑几年都没问题。

**Q: 500MB 公告数据大概能存多少条？**  
A: 一条公告元数据大约 1-3KB。500MB ≈ 20-50 万条公告。够你用 5-10 年。

**Q: PDF 不存吗？**  
A: 第一版不存。HTML 里的"打开 PDF"按钮会直接跳到巨潮的远程链接。等你以后真要做"解析 PDF 抽字段"再考虑。

**Q: 数据多久更新一次？**  
A: GitHub Actions 配的是每天北京时间 20:30 跑一次。如果想更频繁，改 `.github/workflows/daily-cninfo.yml` 里的 cron。

**Q: 我想看某家公司历史所有套保公告怎么办？**  
A: 在 HTML 顶部搜索框输入公司代码或简称，过滤出来所有相关公告。后续会加"公司详情页"。

**Q: 出错了怎么办？**  
A: 把错误截图发给我，**不要发 service_role key**。我会帮你看。

---

## 6. 不做什么（先不给自己加压）

第一版明确**不**做的事：
- ❌ 用户登录、权限系统
- ❌ 收费、多租户
- ❌ 主动告警推送（邮件/企微/钉钉）
- ❌ 港股美股
- ❌ 复杂向量数据库
- ❌ 全量 PDF 解析（先用标题识别）
- ❌ 漂亮但没数据的大屏

第二版再考虑：
- 按需 PDF 解析 + 金额/期限精确抽取
- 原文证据链（字段→页码→原句）
- LLM 结构化抽取
- 年报深度解析
- 行业对比

---

## 7. 接下来

把 **Project URL** 和 **anon public key** 发给我，我帮你：
1. 实跑一次，写入你的 Supabase
2. 验证 HTML 能拉到真实数据
3. 给你 GitHub Actions 配置文件
4. 教你怎么 push 到 GitHub 启用定时

不用发 service_role key，它永远只在你自己的 `.env` 里。
