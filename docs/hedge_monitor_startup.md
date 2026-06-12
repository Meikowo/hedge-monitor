# 上市公司套保公告与年报披露监控系统：启动文档（MVP 到可用版）

> 适用对象：第一次做数据监控系统、准备用 Claude Code / 本地开发工具启动项目的人。  
> 当前版本目标：内部研究工具，不收费，不做用户权限，不做主动告警，只做网页提示。  
> 核心闭环：公告采集 → PDF 下载 → 文本解析 → 套保识别 → 结构化抽取 → 证据链 → 页面展示 → 提示标签。

---

## 0. 一句话目标

做一个每天自动监控 A 股上市公司公告和年报披露中“套期保值、期货和衍生品交易、远期结售汇、外汇衍生品、商品期货套保”等内容的内部网页工具。

第一版不要追求复杂金融终端，先做到：

```text
每天能看到新增套保相关公告；
点进公告能看到抽取字段；
每个字段能回到原文证据；
系统能给出提示标签，例如“大额额度”“股东会审议”“出现亏损表述”“低置信度需确认”；
年报能初步识别是否披露套保、衍生金融资产/负债、公允价值变动损益等内容。
```

---

## 1. 项目边界

### 1.1 第一版要做什么

第一版 MVP 只做以下内容：

```text
1. A 股上市公司公告监控。
2. 临时公告中的套保/衍生品相关事项识别。
3. 年度报告中的套保/衍生品披露初步识别。
4. PDF 原件保存。
5. PDF 文本解析。
6. 关键词规则召回。
7. LLM 结构化抽取核心字段。
8. 字段证据保存。
9. 页面展示公告列表、公告详情、证据句、提示标签。
10. 低置信度结果标记“需确认”。
```

### 1.2 第一版暂时不做什么

```text
1. 不做用户登录和权限系统。
2. 不做收费系统。
3. 不做多租户。
4. 不做主动告警推送，例如邮件、飞书、企微、钉钉。
5. 不做港股、美股。
6. 不做全量 OCR，OCR 只作为后续兜底能力。
7. 不一开始做多年全市场历史回填。
8. 不一开始做复杂向量数据库。
9. 不一开始做漂亮但没有数据支撑的大屏。
```

---

## 2. 推荐总架构

采用“简洁主架构 + 证据链 + 提示 + 年报专项解析 + 任务队列 + 模型校验”。

```text
数据源层
  巨潮资讯网 / 上交所 / 深交所 / 北交所 / Tushare-AKShare 辅助
        ↓
采集调度层
  定时增量采集 + 历史回填 + 失败重试 + 去重
        ↓
原文存储层
  PDF 原件 / HTML 快照 / 元数据 / 文件 hash
        ↓
解析层
  PDF 文本解析 + 表格解析 + OCR 兜底 + 段落切分
        ↓
套保识别层
  关键词规则 + LLM 结构化抽取 + 字段校验
        ↓
证据链层
  字段值 → 原文句子 → 页码 → 文档 chunk → PDF 定位
        ↓
数据存储层
  PostgreSQL + 对象存储 + Redis + 全文搜索
        ↓
业务服务层
  FastAPI：公告查询 / 公司画像 / 年报披露 / 提示生成 / 导出
        ↓
前端展示层
  React + AntD + ECharts + PDF.js
```

---

## 3. 技术栈建议

### 3.1 MVP 技术栈

```text
前端：
React + TypeScript + Ant Design + ECharts + PDF.js

后端：
FastAPI + Pydantic + SQLAlchemy + Alembic

任务队列：
Celery + Redis

数据库：
PostgreSQL

对象存储：
MinIO；本地开发也可以先用本地文件夹

PDF 解析：
PyMuPDF + pdfplumber

OCR 后续兜底：
PaddleOCR / RapidOCR

LLM 抽取：
Claude / OpenAI / 本地模型均可，先抽候选公告，不要全量抽

部署：
Docker Compose 起步
```

### 3.2 为什么不一开始用很重的架构

因为这个项目早期最大的风险不是并发，而是：

```text
公告抓取是否稳定；
PDF 能不能解析；
套保候选是否漏掉；
金额和币种是否抽错；
字段有没有原文证据；
年报披露是否能定位。
```

先把这些打通，再考虑 Kubernetes、分布式搜索、复杂权限、向量数据库等。

---

## 4. 推荐目录结构

```text
hedge-monitor/
  README.md
  .env.example
  docker-compose.yml

  apps/
    web/                         # React 前端
      package.json
      src/
        pages/
        components/
        services/
        types/

    api/                         # FastAPI 后端
      pyproject.toml
      app/
        main.py
        config.py
        db.py
        models/
        schemas/
        routers/
        services/

  workers/
    crawler/                     # 公告采集
      crawl_cninfo.py
      crawl_sse.py
      crawl_szse.py
      crawl_bse.py

    downloader/                  # PDF 下载
      download_document.py

    parser/                      # PDF 解析
      parse_pdf.py
      parse_tables.py
      chunk_text.py

    extractor/                   # 规则识别 + LLM 抽取 + 校验
      keywords.yml
      detect_candidates.py
      llm_extract.py
      validators.py
      generate_tips.py

    annual_report/               # 年报专项解析
      detect_annual_report.py
      extract_annual_sections.py
      extract_annual_fields.py

  packages/
    shared/
      field_schema.json
      extraction_schema.json

  scripts/
    init_db.py
    run_daily.py
    backfill_announcements.py
    backfill_annual_reports.py

  docs/
    startup.md
    data_dictionary.md
    extraction_schema.md
    prompt_versions.md
    runbook.md
    quality_review.md
```

---

## 5. 第一阶段开发原则

### 5.1 一次只做一个闭环

不要让 Claude Code 一次写完整系统。你要让它分阶段写：

```text
第 1 步：建项目骨架。
第 2 步：建数据库表。
第 3 步：写公告采集。
第 4 步：写 PDF 下载。
第 5 步：写 PDF 解析。
第 6 步：写关键词召回。
第 7 步：写 LLM 抽取。
第 8 步：写字段校验。
第 9 步：写提示生成。
第 10 步：写前端页面。
```

### 5.2 先做最近 7 天，不要直接回填几年

```text
第一版：最近 7 天公告。
第二版：最近 30 天公告。
第三版：最近 1 年公告。
第四版：最近 3 年年报。
```

### 5.3 先做可用，不要先做完美

第一天目标：

```text
数据库有公告；
本地有 PDF 文件；
网页能看到公告标题。
```

不是：

```text
全市场稳定运行；
所有字段都完美；
UI 完全成品；
年报全量解析。
```

---

## 6. 数据源方案

### 6.1 第一版数据源优先级

```text
第一优先级：巨潮资讯网公告检索。
第二优先级：上交所、深交所、北交所官网作为校验源。
第三优先级：Tushare / AKShare 作为辅助索引或原型验证。
```

### 6.2 采集内容

每条公告至少保存：

```text
source：来源，例如 cninfo / sse / szse / bse
source_id：源站公告 ID，如果能拿到
stock_code：证券代码
stock_name：证券简称
title：公告标题
announcement_date：公告日期
publish_time：发布时间，如果能拿到
category：公告类别
source_url：公告详情页链接
pdf_url：PDF 附件链接
file_type：PDF / HTML / DOC / XBRL
created_at：入库时间
updated_at：更新时间
```

### 6.3 合规和稳健性注意事项

```text
1. 优先遵守公开网站 robots 和访问频率限制。
2. 不要高频并发请求源站。
3. 保存原始文件 hash，避免重复下载。
4. 源站接口可能变动，不要把某一个非官方接口当成唯一依赖。
5. 若后续对外商业化，需要考虑数据授权；当前内部研究 MVP 可先验证技术链路。
```

---

## 7. 数据库核心表设计

### 7.1 companies：公司表

```sql
CREATE TABLE companies (
  id BIGSERIAL PRIMARY KEY,
  stock_code VARCHAR(20) NOT NULL UNIQUE,
  stock_name VARCHAR(100),
  exchange VARCHAR(20),
  board VARCHAR(50),
  industry VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### 7.2 announcements：公告表

```sql
CREATE TABLE announcements (
  id BIGSERIAL PRIMARY KEY,
  source VARCHAR(50),
  source_id VARCHAR(100),
  stock_code VARCHAR(20),
  stock_name VARCHAR(100),
  title TEXT NOT NULL,
  announcement_date DATE,
  publish_time TIMESTAMP,
  category VARCHAR(100),
  source_url TEXT,
  pdf_url TEXT,
  file_sha256 VARCHAR(128),
  download_status VARCHAR(30) DEFAULT 'pending',
  parse_status VARCHAR(30) DEFAULT 'pending',
  is_candidate BOOLEAN DEFAULT FALSE,
  candidate_score NUMERIC(6, 3),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(source, source_id)
);
```

### 7.3 documents：文档表

```sql
CREATE TABLE documents (
  id BIGSERIAL PRIMARY KEY,
  announcement_id BIGINT REFERENCES announcements(id),
  file_path TEXT,
  file_type VARCHAR(20),
  file_size BIGINT,
  sha256 VARCHAR(128),
  page_count INTEGER,
  text_length INTEGER,
  parse_status VARCHAR(30) DEFAULT 'pending',
  ocr_used BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### 7.4 document_chunks：文本分块表

```sql
CREATE TABLE document_chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT REFERENCES documents(id),
  announcement_id BIGINT REFERENCES announcements(id),
  page_no INTEGER,
  chunk_index INTEGER,
  text TEXT NOT NULL,
  char_count INTEGER,
  bbox_json JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.5 hedge_events：套保事件表

```sql
CREATE TABLE hedge_events (
  id BIGSERIAL PRIMARY KEY,
  announcement_id BIGINT REFERENCES announcements(id),
  company_id BIGINT REFERENCES companies(id),
  document_id BIGINT REFERENCES documents(id),

  event_type VARCHAR(100),
  hedge_type VARCHAR(100),
  instrument_type JSONB,
  underlying_asset JSONB,
  risk_type JSONB,

  contract_value_limit NUMERIC(24, 4),
  contract_value_currency VARCHAR(20),
  contract_value_raw_text TEXT,

  margin_limit NUMERIC(24, 4),
  margin_currency VARCHAR(20),
  margin_raw_text TEXT,

  authorization_period TEXT,
  approval_level VARCHAR(50),
  uses_raised_funds BOOLEAN,
  has_loss_disclosure BOOLEAN,
  is_non_hedging_speculation BOOLEAN,

  confidence NUMERIC(6, 3),
  need_review BOOLEAN DEFAULT FALSE,
  review_status VARCHAR(30) DEFAULT 'unreviewed',

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### 7.6 extraction_evidence：证据表

```sql
CREATE TABLE extraction_evidence (
  id BIGSERIAL PRIMARY KEY,
  hedge_event_id BIGINT REFERENCES hedge_events(id),
  field_name VARCHAR(100),
  chunk_id BIGINT REFERENCES document_chunks(id),
  page_no INTEGER,
  quote_text TEXT,
  bbox_json JSONB,
  confidence NUMERIC(6, 3),
  created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.7 tips：提示表

```sql
CREATE TABLE tips (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT REFERENCES companies(id),
  announcement_id BIGINT REFERENCES announcements(id),
  hedge_event_id BIGINT REFERENCES hedge_events(id),
  tip_type VARCHAR(100),
  tip_level VARCHAR(30),
  tip_title TEXT,
  tip_message TEXT,
  trigger_field VARCHAR(100),
  trigger_value TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.8 annual_hedge_disclosures：年报披露表

```sql
CREATE TABLE annual_hedge_disclosures (
  id BIGSERIAL PRIMARY KEY,
  company_id BIGINT REFERENCES companies(id),
  report_year INTEGER,
  announcement_id BIGINT REFERENCES announcements(id),
  document_id BIGINT REFERENCES documents(id),

  has_hedging BOOLEAN,
  hedge_type JSONB,
  instrument_type JSONB,
  underlying_asset JSONB,

  derivative_assets NUMERIC(24, 4),
  derivative_liabilities NUMERIC(24, 4),
  fair_value_change_gain_loss NUMERIC(24, 4),
  investment_income NUMERIC(24, 4),
  hedge_reserve NUMERIC(24, 4),
  notional_amount NUMERIC(24, 4),
  contract_value_limit NUMERIC(24, 4),

  hedge_effectiveness_description TEXT,
  risk_management_description TEXT,
  accounting_policy TEXT,

  confidence NUMERIC(6, 3),
  need_review BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### 7.9 task_runs：任务运行表

```sql
CREATE TABLE task_runs (
  id BIGSERIAL PRIMARY KEY,
  task_name VARCHAR(100),
  source VARCHAR(50),
  status VARCHAR(30),
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  records_found INTEGER DEFAULT 0,
  records_success INTEGER DEFAULT 0,
  records_failed INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.10 manual_corrections：人工修正表

```sql
CREATE TABLE manual_corrections (
  id BIGSERIAL PRIMARY KEY,
  target_type VARCHAR(50),
  target_id BIGINT,
  field_name VARCHAR(100),
  old_value TEXT,
  new_value TEXT,
  reason TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 8. 关键词词典第一版

建议放在：

```text
workers/extractor/keywords.yml
```

示例：

```yaml
core:
  - 套期保值
  - 套保
  - 套期工具
  - 被套期项目
  - 套期会计

derivatives:
  - 期货
  - 期权
  - 远期
  - 掉期
  - 互换
  - 远期结售汇
  - 外汇远期
  - 外汇期权
  - 金融衍生品
  - 衍生品交易
  - 衍生金融资产
  - 衍生金融负债

risk:
  - 外汇风险
  - 汇率风险
  - 商品价格风险
  - 原材料价格波动
  - 利率风险
  - 信用风险

documents:
  - 可行性分析报告
  - 套期保值业务管理制度
  - 金融衍生品交易管理制度
  - 期货和衍生品交易管理制度

loss:
  - 亏损
  - 浮亏
  - 损失
  - 公允价值变动损失
  - 未按预期抵销
  - 未有效对冲

underlying_assets:
  - 美元
  - 欧元
  - 日元
  - 港币
  - 铜
  - 铝
  - 锌
  - 镍
  - 黄金
  - 白银
  - 原油
  - 天然气
  - 煤炭
  - 焦煤
  - 焦炭
  - 铁矿石
  - 螺纹钢
  - 热卷
  - PTA
  - 甲醇
  - 纯碱
  - 玻璃
  - 棉花
  - 豆粕
  - 豆油
  - 玉米
```

---

## 9. 规则召回逻辑

第一版规则不要复杂，先追求高召回。

### 9.1 标题规则

```text
标题包含“套期保值”或“套保”：高优先级候选。
标题包含“期货和衍生品交易”：高优先级候选。
标题包含“金融衍生品交易”：高优先级候选。
标题包含“外汇衍生品”或“远期结售汇”：高优先级候选。
标题包含“可行性分析报告”：中高优先级候选。
标题包含“管理制度”：中优先级候选。
标题包含“年度报告”：进入年报专项解析。
```

### 9.2 正文规则

```text
正文中核心词出现次数 ≥ 2：候选。
正文出现“衍生金融资产”或“衍生金融负债”：候选。
正文出现“现金流量套期”或“公允价值套期”：候选。
正文出现“远期结售汇 + 汇率风险”：候选。
正文出现“期货 + 原材料价格波动”：候选。
正文出现“浮亏/亏损/损失 + 衍生品”：提示关注。
```

### 9.3 候选分数示例

```text
标题命中“套期保值”：+50
标题命中“金融衍生品”：+40
标题命中“远期结售汇”：+40
正文命中核心词：每次 +10，最高 +40
正文命中交易工具：每次 +5，最高 +30
正文命中损失词：+20
年报标题：+10，但进入年报流程
最终分数 ≥ 40：进入 LLM 抽取
最终分数 20—39：进入人工待确认/暂存
```

---

## 10. LLM 结构化抽取

### 10.1 调用原则

```text
1. 不要全量公告都送 LLM。
2. 只对规则召回的候选公告调用 LLM。
3. 输入不要直接塞整个 PDF。
4. 输入公告标题、公司、日期、命中段落、页码。
5. 输出必须是固定 JSON。
6. JSON 入库前必须经过 validator 校验。
```

### 10.2 第一版抽取 JSON Schema

```json
{
  "is_hedging_related": true,
  "document_type": "临时公告",
  "event_type": "开展外汇套期保值业务",
  "hedge_type": "外汇套期保值",
  "instrument_type": ["远期结售汇", "外汇期权"],
  "underlying_asset": ["美元", "欧元"],
  "risk_type": ["汇率风险"],
  "contract_value_limit": {
    "amount": 1000000000,
    "currency": "CNY",
    "unit_text": "人民币10亿元",
    "raw_text": "任一交易日持有的最高合约价值不超过人民币10亿元"
  },
  "margin_or_premium_limit": {
    "amount": null,
    "currency": null,
    "raw_text": null
  },
  "authorization_period": "董事会审议通过之日起12个月",
  "approval_level": "董事会",
  "uses_raised_funds": false,
  "has_loss_disclosure": false,
  "is_non_hedging_speculation": false,
  "confidence": 0.88,
  "evidence": [
    {
      "field": "contract_value_limit",
      "page_no": 3,
      "quote": "任一交易日持有的最高合约价值不超过人民币10亿元"
    }
  ]
}
```

### 10.3 Prompt 模板

```text
你是一个上市公司公告信息抽取助手。你的任务是从公告文本中识别是否涉及套期保值、期货和衍生品交易、外汇衍生品、远期结售汇、商品期货套保等事项，并抽取结构化字段。

要求：
1. 只能根据给定文本抽取，不得编造。
2. 没有明确证据的字段填 null。
3. 每个非 null 字段必须提供原文证据 quote 和页码 page_no。
4. 金额必须保留原文 raw_text，并尽量换算为数字 amount。
5. 区分“最高合约价值”和“保证金/权利金上限”，不要混淆。
6. 区分“套期保值”和“非套保衍生品交易”。
7. 输出必须是合法 JSON，不要输出解释文字。

输入：
公司代码：{stock_code}
公司名称：{stock_name}
公告日期：{announcement_date}
公告标题：{title}
相关文本：
{chunks}

请输出 JSON。
```

---

## 11. 模型校验规则

不要直接相信 LLM 输出，必须校验。

### 11.1 金额校验

```text
1. 如果模型输出 amount，但 evidence quote 中找不到对应金额，need_review = true。
2. 如果原文是“万元”，必须乘以 10,000。
3. 如果原文是“亿元”，必须乘以 100,000,000。
4. 如果原文是“万美元”，币种应为 USD，单位换算为美元数值。
5. 如果原文写“等值人民币”，currency = CNY，并保留 raw_text。
6. 如果同一段出现多个金额，且无法判断哪个是最高合约价值，need_review = true。
```

### 11.2 审批层级校验

```text
模型输出“董事会”时，原文附近应出现“董事会审议”。
模型输出“股东会”时，原文附近应出现“股东大会”或“股东会”。
如果标题是“股东大会决议公告”，但正文没有明确套保事项，不要误判审批层级。
```

### 11.3 套保类型校验

```text
出现“汇率风险、远期结售汇、外汇远期、外汇期权”：倾向外汇套保。
出现“铜、铝、原油、铁矿石、纯碱、期货、原材料价格波动”：倾向商品套保。
出现“利率掉期、利率互换、利率风险”：倾向利率套保。
出现“不以套期保值为目的”：is_non_hedging_speculation = true。
```

### 11.4 证据校验

```text
所有关键字段都应有 evidence。
无 evidence 的字段可以暂存，但 confidence 下调。
金额、交易工具、套保类型、审批层级、授权期限是重点校验字段。
```

---

## 12. 提示系统设计

你暂时不做告警推送，只做网页提示。

### 12.1 提示等级

```text
info：普通提示。
notice：值得关注。
warning：风险提示。
review：需要人工确认。
```

### 12.2 第一版提示类型

```text
新增套保公告：info
大额额度：notice 或 warning
股东会审议：notice
涉及境外交易：notice
涉及场外衍生品：notice
出现亏损表述：warning
疑似非套保投资交易：warning
低置信度结果：review
年报披露了套保：info
年报披露与临时公告待核对：review
```

### 12.3 提示规则示例

```text
contract_value_limit >= 1,000,000,000 CNY → 大额额度。
approval_level = 股东会 → 股东会审议。
has_loss_disclosure = true → 出现亏损表述。
is_non_hedging_speculation = true → 疑似非套保交易。
confidence < 0.75 → 低置信度需确认。
年报中 derivative_liabilities 较大 → 关注衍生金融负债。
```

---

## 13. 年报专项解析

### 13.1 为什么年报要单独做

普通公告标题比较明确，但年报里的套保信息可能隐藏在多个章节中：

```text
管理层讨论与分析
重要事项
财务报告附注
金融工具风险管理
公允价值披露
衍生金融资产
衍生金融负债
交易性金融资产
投资收益
公允价值变动收益
其他综合收益
套期储备
外汇风险
商品价格风险
利率风险
```

所以年报不要和普通公告完全用同一套规则。

### 13.2 年报解析流程

```text
识别年度报告全文
  ↓
下载年报 PDF
  ↓
解析目录和章节标题
  ↓
召回套保相关章节
  ↓
提取表格和附近段落
  ↓
抽取衍生金融资产/负债、损益、套期储备、套保效果描述
  ↓
保存证据
  ↓
与当年临时公告交叉核对
```

### 13.3 年报第一版字段

```text
公司代码
公司名称
报告年度
是否披露套保
套保类型
交易工具
标的品种
衍生金融资产
衍生金融负债
公允价值变动损益
投资收益
套期储备
名义本金或合约金额
套保效果描述
风险管理描述
会计政策描述
证据页码和原文
置信度
是否需要复核
```

---

## 14. 任务队列设计

### 14.1 Celery 任务拆分

```text
crawl_announcements_task
  抓公告列表。

download_document_task
  下载 PDF / Word / HTML。

parse_document_task
  解析 PDF 文本和表格。

detect_candidate_task
  规则识别候选公告。

extract_hedge_event_task
  LLM 结构化抽取。

validate_extraction_task
  字段校验和证据校验。

generate_tips_task
  生成页面提示。

parse_annual_report_task
  年报专项解析。

backfill_task
  历史公告回填。
```

### 14.2 每天运行流程

```text
每天 17:00、20:00、23:00 分别跑一次增量采集；
每次只抓当天和前一天公告；
新公告入库后下载 PDF；
下载成功后解析 PDF；
解析成功后跑候选识别；
候选公告进入 LLM 抽取；
抽取后做校验；
校验后生成提示；
前端页面自动读取最新数据。
```

### 14.3 历史回填不要和每日任务混跑

```text
每日增量：小任务，优先稳定。
历史回填：大任务，放在夜间或手动运行。
```

---

## 15. FastAPI 接口第一版

```text
GET /api/dashboard/summary
  首页统计。

GET /api/announcements
  公告列表，支持日期、公司、标题、套保类型、提示等级筛选。

GET /api/announcements/{id}
  公告详情。

GET /api/announcements/{id}/evidence
  公告证据列表。

GET /api/companies/{stock_code}
  公司详情。

GET /api/companies/{stock_code}/hedge-events
  公司历史套保事件。

GET /api/annual-reports
  年报披露列表。

GET /api/tips
  提示列表。

POST /api/review/hedge-events/{id}
  人工修正结构化字段。

POST /api/tasks/run-daily
  手动触发每日任务。

POST /api/tasks/backfill
  手动触发历史回填。
```

---

## 16. 前端页面第一版

### 16.1 首页总览

展示：

```text
今日新增公告数
候选套保公告数
结构化抽取成功数
需要复核数
年报披露数
提示数量
```

图表：

```text
按套保类型分布
按交易所分布
按提示等级分布
按行业分布，后续加
```

### 16.2 公告列表页

字段：

```text
日期
公司
代码
标题
套保类型
交易工具
标的品种
最高合约价值
审批层级
提示标签
置信度
查看详情
```

筛选：

```text
日期
公司代码
公司名称
交易所
套保类型
交易工具
标的品种
金额区间
提示等级
是否需要复核
```

### 16.3 公告详情页

推荐三栏布局：

```text
左侧：抽取字段
中间：原文证据
右侧：PDF 预览
```

必须支持：

```text
点击字段 → 看到证据句。
点击证据句 → 打开 PDF 对应页。
低置信度字段 → 标记“需确认”。
人工可修正字段。
```

### 16.4 公司详情页

展示：

```text
公司历史套保公告时间线
每次披露的最高合约价值
套保类型变化
交易工具变化
年报披露摘要
提示记录
```

### 16.5 年报披露页

展示：

```text
公司
年度
是否披露套保
披露位置
衍生金融资产
衍生金融负债
公允价值变动损益
套保效果描述
证据
```

---

## 17. Claude Code 工作方式建议

### 17.1 不要这样问

不要一次性说：

```text
帮我写一个完整的上市公司套保监控系统。
```

这样容易得到一堆跑不起来的代码。

### 17.2 应该这样拆任务

#### Prompt 1：建项目骨架

```text
请为“上市公司套保公告与年报披露监控系统”创建一个 MVP 项目骨架。
要求：
1. 使用 docker-compose 启动 PostgreSQL、Redis、MinIO。
2. 后端使用 FastAPI。
3. 前端使用 React + TypeScript + Ant Design。
4. 创建 apps/api、apps/web、workers、docs、scripts 目录。
5. 给出 README.md 和 .env.example。
6. 先不要写复杂业务，只保证项目可以启动。
```

#### Prompt 2：建数据库模型

```text
请在 FastAPI 后端中使用 SQLAlchemy 创建以下表：companies、announcements、documents、document_chunks、hedge_events、extraction_evidence、tips、annual_hedge_disclosures、task_runs、manual_corrections。
要求：
1. 字段参考 docs/startup.md。
2. 使用 Alembic 管理迁移。
3. 提供初始化命令。
4. 提供一个健康检查接口 /health。
```

#### Prompt 3：写公告采集基础模块

```text
请创建 workers/crawler/crawl_cninfo.py。
目标：先实现一个可替换的数据采集接口，不要求一定连接真实源站。
要求：
1. 定义 AnnouncementMeta 数据结构。
2. 支持从 mock JSON 读取公告列表。
3. 后续可替换为真实巨潮/交易所采集。
4. 写入 announcements 表。
5. 做去重。
```

#### Prompt 4：写 PDF 下载模块

```text
请创建 workers/downloader/download_document.py。
要求：
1. 从 announcements 表读取 pdf_url。
2. 下载文件到 storage/documents/{date}/{stock_code}/。
3. 计算 sha256。
4. 写入 documents 表。
5. 更新 download_status。
6. 下载失败要记录错误，不要让程序崩溃。
```

#### Prompt 5：写 PDF 解析模块

```text
请创建 workers/parser/parse_pdf.py。
要求：
1. 使用 PyMuPDF 提取每页文本。
2. 按段落切分，写入 document_chunks 表。
3. 记录 page_no、chunk_index、text、char_count。
4. 如果提取文本少于阈值，标记 need_ocr 或 parse_status=low_text。
```

#### Prompt 6：写关键词召回模块

```text
请创建 workers/extractor/keywords.yml 和 detect_candidates.py。
要求：
1. 根据标题和正文命中关键词计算 candidate_score。
2. 分为 title_score、body_score、loss_score、final_score。
3. final_score >= 40 的公告标记 is_candidate=true。
4. 记录命中关键词，方便前端展示。
```

#### Prompt 7：写 LLM 抽取模块

```text
请创建 workers/extractor/llm_extract.py。
要求：
1. 只处理 is_candidate=true 的公告。
2. 从 document_chunks 中选择相关 chunk，不要直接传全文。
3. 使用固定 JSON schema 抽取字段。
4. 支持 mock LLM 模式，便于本地测试。
5. 输出 hedge_events 和 extraction_evidence。
```

#### Prompt 8：写校验和提示模块

```text
请创建 validators.py 和 generate_tips.py。
要求：
1. 校验金额、币种、单位、证据句。
2. confidence < 0.75 时 need_review=true。
3. 生成提示：大额额度、股东会审议、出现亏损表述、疑似非套保、低置信度。
4. 写入 tips 表。
```

#### Prompt 9：写 API

```text
请为前端提供以下接口：
GET /api/dashboard/summary
GET /api/announcements
GET /api/announcements/{id}
GET /api/announcements/{id}/evidence
GET /api/tips
GET /api/annual-reports
POST /api/tasks/run-daily
要求返回结构清晰，带分页和筛选。
```

#### Prompt 10：写前端页面

```text
请创建 React 前端 MVP：
1. 首页仪表盘。
2. 公告列表页。
3. 公告详情页。
4. 证据句展示。
5. 提示标签展示。
6. 简单移动端适配。
暂时不做用户登录。
```

---

## 18. 本地开发启动步骤

### 18.1 安装基础工具

你本地需要：

```text
Git
Docker Desktop
Node.js LTS
Python 3.11+
Poetry 或 uv
VS Code / Cursor / Claude Code
```

### 18.2 初始化仓库

```bash
mkdir hedge-monitor
cd hedge-monitor
git init
mkdir -p apps/api apps/web workers docs scripts packages/shared
```

### 18.3 启动基础服务

`docker-compose.yml` 第一版：

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    container_name: hedge_postgres
    environment:
      POSTGRES_USER: hedge
      POSTGRES_PASSWORD: hedge_password
      POSTGRES_DB: hedge_monitor
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    container_name: hedge_redis
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    container_name: hedge_minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio_password
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

启动：

```bash
docker compose up -d
```

### 18.4 环境变量示例

`.env.example`：

```env
DATABASE_URL=postgresql+psycopg://hedge:hedge_password@localhost:5432/hedge_monitor
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=minio_password
MINIO_BUCKET=hedge-documents
LLM_PROVIDER=mock
LLM_API_KEY=
```

---

## 19. 每日任务脚本设计

`scripts/run_daily.py` 逻辑：

```python
def run_daily():
    run_id = create_task_run("daily_pipeline")

    announcements = crawl_announcements(date_range="today_and_yesterday")
    save_announcements(announcements)

    docs = download_new_documents()
    parse_documents(docs)

    candidates = detect_candidates()
    extracted = extract_hedge_events(candidates)

    validated = validate_extractions(extracted)
    generate_tips(validated)

    finish_task_run(run_id)
```

命令：

```bash
python scripts/run_daily.py
```

---

## 20. 第一版质量评估

做完第一版后，抽样 100 条候选公告人工检查。

### 20.1 评估指标

```text
公告下载成功率：目标 > 95%
PDF 文本解析成功率：目标 > 90%
套保候选召回率：优先追求高召回
核心字段证据覆盖率：目标 > 80%
金额字段人工核对准确率：逐步优化到 > 85%
低置信度结果能进入复核队列
```

### 20.2 常见错误类型

```text
1. 把保证金上限误当成最高合约价值。
2. 把美元金额误存成人民币金额。
3. 把制度公告误当成实际开展业务公告。
4. 把年报中的历史披露误当成新增事件。
5. 把非套保衍生品交易误当成套保。
6. 年报表格解析错列。
7. PDF 扫描件无文本，导致漏识别。
```

---

## 21. 开发周计划

### 第 1 周：最小数据闭环

```text
目标：能抓公告、下载 PDF、入库、网页看到公告列表。

任务：
1. 搭建 Docker Compose。
2. 初始化 PostgreSQL。
3. 创建 announcements / documents / document_chunks 三张表。
4. 写 mock 公告采集。
5. 写 PDF 下载。
6. 做公告列表 API。
7. 做公告列表前端。
```

### 第 2 周：PDF 解析和关键词识别

```text
目标：能解析 PDF，筛出疑似套保公告。

任务：
1. PyMuPDF 提取文本。
2. 按页和段落写入 document_chunks。
3. 建关键词词典。
4. 写候选识别规则。
5. 前端展示命中关键词和候选分数。
```

### 第 3 周：LLM 抽取和证据链

```text
目标：能抽核心字段，每个字段有证据。

任务：
1. 设计 JSON schema。
2. 写 Prompt v1。
3. 写 mock LLM 模式。
4. 写真实 LLM 接口适配。
5. 写 hedge_events 和 extraction_evidence 入库。
6. 前端展示字段和证据句。
```

### 第 4 周：提示系统和复核页面

```text
目标：网页能给出提示，低置信度可以人工修正。

任务：
1. 写提示规则。
2. 建 tips 表。
3. 前端展示提示标签。
4. 做简单复核页面。
5. 保存 manual_corrections。
```

### 第 5—6 周：年报专项解析

```text
目标：能识别年报中的套保和衍生品披露。

任务：
1. 识别年度报告全文。
2. 抽取年报相关章节。
3. 抽取衍生金融资产/负债等字段。
4. 做 annual_hedge_disclosures 表。
5. 做年报披露页面。
```

### 第 7—8 周：历史回填和稳定性优化

```text
目标：系统能稳定运行，并能回填最近一年数据。

任务：
1. 回填最近 30 天。
2. 回填最近 1 年。
3. 任务失败重试。
4. 数据质量看板。
5. 导出 Excel / CSV。
6. 移动端优化。
```

---

## 22. 第一版验收标准

第一版成功标准：

```text
1. 打开网页能看到公告列表。
2. 能按关键词识别套保相关公告。
3. 能看到结构化字段：套保类型、工具、品种、金额、审批层级、期限。
4. 能看到字段证据句和页码。
5. 能看到提示标签。
6. 能看到低置信度需要确认。
7. 能导出 JSON 或 CSV。
8. 每日任务可以手动运行。
```

---

## 23. 你今晚回家可以照着做的顺序

```text
1. 打开 Claude Code。
2. 创建 hedge-monitor 仓库。
3. 把本启动文档放进 docs/startup.md。
4. 先运行我提供的单文件 HTML 原型，理解页面和数据流。
5. 用 Prompt 1 让 Claude Code 建项目骨架。
6. 用 Prompt 2 建数据库模型。
7. 暂时用 mock 公告数据，不要一开始就抓真实网站。
8. 用 mock 数据跑通“公告 → 解析 → 抽取 → 提示 → 前端”。
9. 再接真实采集。
10. 每完成一个小模块就提交一次 git commit。
```

建议的提交节奏：

```bash
git add .
git commit -m "init project scaffold"
git commit -m "add database models"
git commit -m "add mock announcement pipeline"
git commit -m "add pdf parser"
git commit -m "add candidate detector"
git commit -m "add extraction schema and mock extractor"
git commit -m "add tips and evidence UI"
```

---

## 24. 重要提醒

这个项目的核心不是“写一个网页”，而是建设一个可信的信息处理链路：

```text
数据来源可信；
原文文件保存；
解析过程可复现；
字段抽取可校验；
每个字段有证据；
低置信度可复核；
提示有明确触发规则。
```

先做内部可用版，不要过度设计。等你能稳定每天看新增套保公告，再扩展年报、历史回填、行业画像、公司年度对比等高级能力。
