-- =============================================================
-- 009_risk_public_readonly.sql — 风险数据浏览器最小权限
-- =============================================================
-- 正式前端只读取六张公开表；媒体原始线索和回填窗口仅 service_role 可见。

alter table public.risk_source_documents enable row level security;
alter table public.derivative_risk_cases enable row level security;
alter table public.risk_case_documents enable row level security;
alter table public.risk_case_evidence enable row level security;
alter table public.risk_media_reports enable row level security;
alter table public.risk_media_report_sources enable row level security;
alter table public.risk_media_leads enable row level security;
alter table public.risk_media_backfill_windows enable row level security;

revoke all on table public.risk_source_documents from anon, authenticated;
revoke all on table public.derivative_risk_cases from anon, authenticated;
revoke all on table public.risk_case_documents from anon, authenticated;
revoke all on table public.risk_case_evidence from anon, authenticated;
revoke all on table public.risk_media_reports from anon, authenticated;
revoke all on table public.risk_media_report_sources from anon, authenticated;
revoke all on table public.risk_media_leads from anon, authenticated;
revoke all on table public.risk_media_backfill_windows from anon, authenticated;

grant select on table public.risk_source_documents to anon, authenticated;
grant select on table public.derivative_risk_cases to anon, authenticated;
grant select on table public.risk_case_documents to anon, authenticated;
grant select on table public.risk_case_evidence to anon, authenticated;
grant select on table public.risk_media_reports to anon, authenticated;
grant select on table public.risk_media_report_sources to anon, authenticated;

