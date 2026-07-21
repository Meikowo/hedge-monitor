-- =============================================================
-- 000_reset.sql —— ⚠️ 销毁性操作：清空旧 demo 时代的全部表
-- =============================================================
-- 只在「从头重建」时执行一次。执行前请确认你接受以下事实：
--   · 旧 announcements（约4000+条）、旧 hedge_events、companies 等将被删除；
--   · 全部数据可由新管线重建：companies ← data/xlsx（import-companies workflow），
--     公告 ← backfill workflow 重新召回（新词表召回率更高，本就该重抓），
--     抽取 ← extract workflow 重跑（会重新消耗 MiniMax token，属预期成本）。
-- 执行方式：Supabase Dashboard → SQL Editor → 粘贴 → Run。
-- =============================================================

drop view if exists public.v_announcements_with_events;
drop view if exists public.v_ann_flow;
drop view if exists public.v_events;

drop table if exists public.periodic_metric_items;
drop table if exists public.periodic_derivatives;
drop table if exists public.periodic_reports;
drop table if exists public.event_members;
drop table if exists public.quota_items;
drop table if exists public.extraction_evidence;
drop table if exists public.extractions;
drop table if exists public.hedge_events;
drop table if exists public.tips;
drop table if exists public.announcements;
drop table if exists public.companies;

-- 触发器随表删除；函数在 001_init.sql 中以 create or replace 重建
