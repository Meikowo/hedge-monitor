-- =============================================================
-- 006_risk_media_leads.sql —— M6a 新闻风险线索（非正式案例）
-- =============================================================
create table if not exists public.risk_media_leads (
  lead_key text primary key,
  provider text not null default 'TAVILY'
    check (provider in ('TAVILY')),
  url text not null check (url ~ '^https://'),
  source_domain text,
  title text not null,
  snippet text,
  published_at timestamptz,
  code text references public.companies (code) on delete set null,
  company_name text,
  query_keys text[] not null default '{}',
  matched_derivative_terms text[] not null default '{}',
  matched_risk_terms text[] not null default '{}',
  provider_score numeric,
  status text not null default 'new'
    check (status in ('new','matched','dismissed','corroborated')),
  need_review boolean not null default true,
  official_corroborated boolean not null default false,
  raw_metadata jsonb not null default '{}'::jsonb,
  discovered_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, url)
);

create index if not exists idx_risk_media_leads_date
  on public.risk_media_leads (published_at desc);
create index if not exists idx_risk_media_leads_review
  on public.risk_media_leads (need_review, status, published_at desc);
create index if not exists idx_risk_media_leads_code
  on public.risk_media_leads (code, published_at desc);

drop trigger if exists trg_risk_media_leads_updated
  on public.risk_media_leads;
create trigger trg_risk_media_leads_updated
before update on public.risk_media_leads
for each row execute function public.set_updated_at();

alter table public.risk_media_leads enable row level security;

-- 未核实媒体线索不进入公开 Data API；仅服务端采集任务可访问。
revoke all on public.risk_media_leads from anon, authenticated;
grant select, insert, update, delete
  on public.risk_media_leads
  to service_role;

drop policy if exists risk_media_leads_service_role_all
  on public.risk_media_leads;
create policy risk_media_leads_service_role_all
  on public.risk_media_leads
  for all
  to service_role
  using (true)
  with check (true);
