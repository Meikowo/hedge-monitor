-- M0: 抽取扩展列迁移(历史记录)
-- 说明: schema.sql 已包含以下全部列;本文件供从早期 schema 升级的数据库安全执行。
-- 若列已存在,alter table 会报错,故拆成多条并加异常处理提示。

-- 1) 给 hedge_events 补扩展列(若尚未添加)
-- 以下 DO 块用于在列已存在时静默跳过,避免升级报错
do $$
begin
  -- trade_venue
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='trade_venue'
  ) then
    alter table public.hedge_events add column trade_venue text;
  end if;

  -- contract_value_basis
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='contract_value_basis'
  ) then
    alter table public.hedge_events add column contract_value_basis text;
  end if;

  -- is_revolving
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='is_revolving'
  ) then
    alter table public.hedge_events add column is_revolving boolean;
  end if;

  -- use_own_funds
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='use_own_funds'
  ) then
    alter table public.hedge_events add column use_own_funds boolean;
  end if;

  -- is_hedging_announcement
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='is_hedging_announcement'
  ) then
    alter table public.hedge_events add column is_hedging_announcement boolean default true;
  end if;

  -- extracted_at
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='extracted_at'
  ) then
    alter table public.hedge_events add column extracted_at timestamptz;
  end if;

  -- pdf_storage_path
  if not exists (
    select 1 from information_schema.columns
    where table_name='hedge_events' and column_name='pdf_storage_path'
  ) then
    alter table public.hedge_events add column pdf_storage_path text;
  end if;
end $$;

-- 2) 复核队列视图: 待人工复核的抽取结果(低置信度或关键字段缺失)
create or replace view public.v_review_queue as
select
  a.announcement_id,
  a.sec_code,
  a.sec_name,
  a.title,
  a.publish_time,
  a.pdf_url,
  e.hedge_type,
  e.contract_value_limit,
  e.contract_value_currency,
  e.contract_value_basis,
  e.trade_venue,
  e.confidence,
  e.need_review,
  e.extracted_at
from public.announcements a
join public.hedge_events e on e.announcement_id = a.announcement_id
where e.need_review = true
order by e.extracted_at desc;

-- 3) Storage Bucket 说明
-- Supabase Storage 的 announcements-pdf 桶需通过 Dashboard 或 API 手动创建:
--   Dashboard -> Storage -> New bucket -> 名称填 "announcements-pdf" -> Public: 否
-- 本迁移不通过 SQL 创建桶,因 Supabase SQL 直接操作 Storage 需要特殊权限/扩展。
-- 若桶不存在,extract_pipeline.py 会上传失败但会打印警告、不阻断主流程。
