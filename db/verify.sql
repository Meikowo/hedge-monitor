-- =============================================================
-- verify.sql —— 验收查询（逐段选中执行，对照注释里的预期值）
-- =============================================================

-- V1. 表清单与 RLS 开关（预期：6 张表全部 rowsecurity = true）
select tablename, rowsecurity from pg_tables
where schemaname = 'public' order by tablename;

-- V2. anon 策略（预期：6 条 select 策略，各表一条）
select tablename, policyname, cmd from pg_policies
where schemaname = 'public' order by tablename;

-- V3. companies 导入验收（预期：total=5524；央企≈479、地方国企≈1049、民企≈3493、外资≈342）
select count(*) as total from companies;
select ent_type, count(*) from companies group by ent_type order by 2 desc;
select market, count(*) from companies group by market;

-- V4. 公告采集验收（回填 2026 后：total 数千量级；覆盖窗自 2026-01-01 起）
select count(*) as total,
       min(ann_date) as first_day,
       max(ann_date) as last_day
from announcements;
select status, count(*) from announcements group by status order by 2 desc;

-- V5. 召回结构（各关键词命中量；fulltext-audit 出现说明 L2 审计已闭环）
select source, count(*) from announcements group by source order by 2 desc limit 20;

-- V6. 抽取验收（清完积压后：pending≈0；irrelevant 占比通常 5%~20%）
select count(*) as extracted from extractions;
select ann_role, count(*) from extractions
where is_hedge_related group by ann_role order by 2 desc;
select round(avg(confidence)::numeric, 3) as avg_conf,
       count(*) filter (where confidence < 0.75) as low_conf
from extractions where is_hedge_related;

-- V7. 口径结构化验收（basis 分布；amount_verified=false 是复核队列，占比应 <10%）
select basis, count(*),
       count(*) filter (where amount_verified) as verified,
       count(*) filter (where amount_verified = false) as verify_failed
from quota_items group by basis order by 2 desc;

-- V8. 事件层验收（事件数应明显小于套保相关公告数——这正是去重的意义）
select
  (select count(*) from extractions where is_hedge_related) as related_anns,
  (select count(*) from hedge_events) as events,
  (select count(*) from hedge_events where ann_count > 1) as multi_ann_events;
select stage, count(*) from hedge_events group by stage order by 2 desc;

-- V9. 孤儿检查（预期两项均为 0：已抽取的相关公告都应挂到事件）
select count(*) as related_but_no_event
from extractions e
left join event_members m on m.ann_id = e.ann_id
where e.is_hedge_related and m.ann_id is null;
select count(*) as member_without_event
from event_members m
left join hedge_events ev on ev.event_key = m.event_key
where ev.event_key is null;

-- V10. 前端视图冒烟（各返回若干行即可）
select * from v_ann_flow order by publish_time desc limit 5;
select * from v_events order by latest_ann_date desc limit 5;

-- V11. M4a 年报 POC（预期：3 张表 RLS=true；30份元数据；已抽取样本的事实均为 reported）
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename like 'periodic_%' order by tablename;
select status, count(*) from periodic_reports group by status order by status;
select d.report_id, r.code, r.name, r.report_period, d.disclosure_status,
       count(m.*) as metrics,
       count(m.*) filter (where m.value_verified and m.quote_verified) as fully_verified
from periodic_derivatives d
join periodic_reports r using (report_id)
left join periodic_metric_items m using (report_id)
group by d.report_id, r.code, r.name, r.report_period, d.disclosure_status;
select count(*) as forbidden_non_reported
from periodic_metric_items where value_origin <> 'reported';
