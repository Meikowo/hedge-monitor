-- M1: 公司维表迁移
-- 用法: Supabase Dashboard -> SQL Editor -> New Query -> 粘贴执行
-- 作用: 建立 companies 表与前端增强视图，支撑"分行业、分公司类型"查询

-- 1) 公司维表
-- 来源: 巨潮 szse_stock.json + 乐咕乐股/巨潮行业 + 实控人推断企业性质
create table if not exists public.companies (
  sec_code text primary key,            -- 证券代码(去重键)
  sec_name text not null,               -- 证券简称
  org_id text,                          -- 巨潮 orgId
  sw_industry text,                     -- 申万三级行业
  plate text,                           -- 主板 / 创业板 / 科创板 / 北交所
  ent_type text,                        -- 央企 / 地方国企 / 民企 / 外资 / 其他
  market_cap numeric,                   -- 市值(万元或元,统一即可)
  list_date date,                       -- 上市日期
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- updated_at 自动维护
drop trigger if exists set_companies_updated_at on public.companies;
create trigger set_companies_updated_at
before update on public.companies
for each row execute function public.set_updated_at();

-- RLS: 允许前端只读
alter table public.companies enable row level security;

drop policy if exists "public read companies" on public.companies;
create policy "public read companies"
on public.companies for select
to anon, authenticated
using (true);

-- 2) 增强视图: 公告 + 抽取字段 + 公司维度(行业/板块/性质)
-- 前端列表页与 Dashboard 的主数据源
create or replace view public.v_announcements_enriched as
select
  a.id,
  a.announcement_id,
  a.sec_code,
  a.sec_name,
  a.title,
  a.publish_time,
  a.pdf_url,
  a.source,
  e.hedge_type,
  e.instrument_type,
  e.underlying_asset,
  e.risk_type,
  e.approval_level,
  e.authorization_period,
  e.contract_value_limit,
  e.contract_value_currency,
  e.contract_value_raw_text,
  e.contract_value_basis,
  e.trade_venue,
  e.is_revolving,
  e.use_own_funds,
  e.is_hedging_announcement,
  e.confidence,
  e.need_review,
  e.extracted_at,
  e.pdf_storage_path,
  c.sw_industry,
  c.plate,
  c.ent_type,
  c.market_cap,
  c.list_date
from public.announcements a
left join public.hedge_events e on e.announcement_id = a.announcement_id
left join public.companies c on c.sec_code = a.sec_code;

-- 3) 预聚合统计视图: 按月 × 行业 × 企业性质
-- 给 Dashboard 趋势图用,减少前端实时计算
create or replace view public.v_stats_monthly as
select
  date_trunc('month', a.publish_time)::date as month,
  c.sw_industry,
  c.ent_type,
  count(distinct a.announcement_id) as announcement_count,
  count(distinct a.sec_code) as company_count,
  sum(case when e.is_hedging_announcement = true then 1 else 0 end) as hedging_announcement_count
from public.announcements a
left join public.hedge_events e on e.announcement_id = a.announcement_id
left join public.companies c on c.sec_code = a.sec_code
where a.publish_time is not null
group by 1, 2, 3;
