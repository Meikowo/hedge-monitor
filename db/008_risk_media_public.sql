-- =============================================================
-- 008_risk_media_public.sql — M6b 公开媒体风险投影
-- =============================================================
-- 原始 Tavily 线索继续保存在 risk_media_leads，仅 service_role 可访问。
-- 浏览器只读取经过确定性门槛筛选、脱敏后的两张公开投影表。

create table if not exists public.risk_media_reports (
  media_key text primary key,
  code text not null references public.companies (code) on delete cascade,
  company_name text not null,
  event_date date not null,
  risk_type text,
  instruments text[] not null default '{}',
  underlyings text[] not null default '{}',
  summary text not null check (char_length(summary) <= 300),
  verification_status text not null default 'media_unverified'
    check (verification_status in ('media_unverified','officially_corroborated')),
  official_case_key text references public.derivative_risk_cases (case_key)
    on delete set null,
  publish_status text not null default 'published'
    check (publish_status in ('published','corroborated','dismissed','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (verification_status = 'officially_corroborated' and official_case_key is not null)
    or verification_status = 'media_unverified'
  )
);

create index if not exists idx_risk_media_reports_date
  on public.risk_media_reports (event_date desc);
create index if not exists idx_risk_media_reports_company
  on public.risk_media_reports (code, event_date desc);
create index if not exists idx_risk_media_reports_public
  on public.risk_media_reports (publish_status, event_date desc);
create index if not exists idx_risk_media_reports_official_case
  on public.risk_media_reports (official_case_key)
  where official_case_key is not null;

create table if not exists public.risk_media_report_sources (
  source_key text primary key,
  media_key text not null references public.risk_media_reports (media_key)
    on delete cascade,
  publisher_name text not null,
  source_domain text not null,
  title text not null,
  published_at timestamptz not null,
  url text not null check (url ~ '^https://'),
  short_excerpt text not null check (char_length(short_excerpt) <= 500),
  matched_derivative_terms text[] not null default '{}',
  matched_risk_terms text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (media_key, url)
);

create index if not exists idx_risk_media_sources_report
  on public.risk_media_report_sources (media_key, published_at desc);
create index if not exists idx_risk_media_sources_domain
  on public.risk_media_report_sources (source_domain, published_at desc);

drop trigger if exists trg_risk_media_reports_updated
  on public.risk_media_reports;
create trigger trg_risk_media_reports_updated
before update on public.risk_media_reports
for each row execute function public.set_updated_at();

drop trigger if exists trg_risk_media_report_sources_updated
  on public.risk_media_report_sources;
create trigger trg_risk_media_report_sources_updated
before update on public.risk_media_report_sources
for each row execute function public.set_updated_at();

alter table public.risk_media_reports enable row level security;
alter table public.risk_media_report_sources enable row level security;

revoke all on public.risk_media_reports from anon, authenticated;
revoke all on public.risk_media_report_sources from anon, authenticated;

grant select on public.risk_media_reports, public.risk_media_report_sources
  to anon, authenticated;
grant select, insert, update, delete
  on public.risk_media_reports, public.risk_media_report_sources
  to service_role;

drop policy if exists risk_media_reports_public_select
  on public.risk_media_reports;
create policy risk_media_reports_public_select
  on public.risk_media_reports
  for select
  to anon, authenticated
  using (publish_status in ('published','corroborated'));

drop policy if exists risk_media_reports_service_role_all
  on public.risk_media_reports;
create policy risk_media_reports_service_role_all
  on public.risk_media_reports
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists risk_media_report_sources_public_select
  on public.risk_media_report_sources;
create policy risk_media_report_sources_public_select
  on public.risk_media_report_sources
  for select
  to anon, authenticated
  using (
    exists (
      select 1
      from public.risk_media_reports report
      where report.media_key = risk_media_report_sources.media_key
        and report.publish_status in ('published','corroborated')
    )
  );

drop policy if exists risk_media_report_sources_service_role_all
  on public.risk_media_report_sources;
create policy risk_media_report_sources_service_role_all
  on public.risk_media_report_sources
  for all
  to service_role
  using (true)
  with check (true);
