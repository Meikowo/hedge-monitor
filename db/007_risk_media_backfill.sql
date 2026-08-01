-- M6a historical Tavily media-lead backfill queue (private, non-case data).
create table if not exists public.risk_media_backfill_windows (
  window_key text primary key,
  calendar_year smallint not null check (calendar_year between 1990 and 2100),
  query_key text not null,
  query_text text not null,
  window_start date not null,
  window_end date not null,
  granularity text not null check (granularity in ('annual','quarter')),
  parent_window_key text references public.risk_media_backfill_windows (window_key)
    on delete cascade,
  status text not null default 'pending'
    check (status in ('pending','running','completed','failed','split')),
  attempts smallint not null default 0 check (attempts >= 0),
  raw_result_count integer not null default 0 check (raw_result_count >= 0),
  lead_count integer not null default 0 check (lead_count >= 0),
  credits_used integer not null default 0 check (credits_used >= 0),
  saturated boolean not null default false,
  last_error text,
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  check (window_end >= window_start),
  unique (query_key, window_start, window_end)
);

create index if not exists idx_risk_media_backfill_queue
  on public.risk_media_backfill_windows
    (calendar_year desc, window_start, query_key)
  where status in ('pending','failed','running');
create index if not exists idx_risk_media_backfill_parent
  on public.risk_media_backfill_windows (parent_window_key)
  where parent_window_key is not null;

drop trigger if exists trg_risk_media_backfill_windows_updated
  on public.risk_media_backfill_windows;
create trigger trg_risk_media_backfill_windows_updated
before update on public.risk_media_backfill_windows
for each row execute function public.set_updated_at();

alter table public.risk_media_backfill_windows enable row level security;

revoke all on public.risk_media_backfill_windows from anon, authenticated;
grant select, insert, update, delete
  on public.risk_media_backfill_windows
  to service_role;

drop policy if exists risk_media_backfill_windows_service_role_all
  on public.risk_media_backfill_windows;
create policy risk_media_backfill_windows_service_role_all
  on public.risk_media_backfill_windows
  for all
  to service_role
  using (true)
  with check (true);

-- Atomically claim only the newest unfinished year. The function is invoker-security
-- and executable only by service_role, so normal table RLS/grants remain authoritative.
create or replace function public.claim_risk_media_backfill_windows(
  p_start_year smallint,
  p_end_year smallint,
  p_limit integer,
  p_stale_before timestamptz
)
returns setof public.risk_media_backfill_windows
language sql
volatile
set search_path = ''
as $$
  with newest as (
    select max(w.calendar_year) as calendar_year
    from public.risk_media_backfill_windows w
    where w.calendar_year between p_start_year and p_end_year
      and (
        w.status = 'pending'
        or (w.status = 'failed' and w.attempts < 3)
        or (w.status = 'running' and w.attempts < 3
            and (w.started_at is null or w.started_at <= p_stale_before))
      )
  ), candidates as (
    select w.window_key
    from public.risk_media_backfill_windows w
    join newest n on n.calendar_year = w.calendar_year
    where (
      w.status = 'pending'
      or (w.status = 'failed' and w.attempts < 3)
      or (w.status = 'running' and w.attempts < 3
          and (w.started_at is null or w.started_at <= p_stale_before))
    )
    order by w.window_start, w.query_key, w.window_key
    for update skip locked
    limit least(greatest(p_limit, 1), 12)
  )
  update public.risk_media_backfill_windows w
  set status = 'running',
      attempts = w.attempts + 1,
      started_at = now(),
      completed_at = null,
      last_error = null
  from candidates c
  where w.window_key = c.window_key
  returning w.*;
$$;

revoke all on function public.claim_risk_media_backfill_windows(
  smallint, smallint, integer, timestamptz
) from public, anon, authenticated;
grant execute on function public.claim_risk_media_backfill_windows(
  smallint, smallint, integer, timestamptz
) to service_role;

-- Merge machine discovery fields without ever resetting human-review state.
create or replace function public.upsert_risk_media_leads(p_rows jsonb)
returns integer
language plpgsql
volatile
set search_path = ''
as $$
declare
  affected integer := 0;
begin
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'p_rows must be a JSON array';
  end if;

  insert into public.risk_media_leads (
    lead_key, provider, url, source_domain, title, snippet, published_at,
    code, company_name, query_keys, matched_derivative_terms,
    matched_risk_terms, provider_score, status, need_review,
    official_corroborated, raw_metadata
  )
  select
    x.lead_key,
    coalesce(x.provider, 'TAVILY'),
    x.url,
    x.source_domain,
    x.title,
    x.snippet,
    x.published_at,
    x.code,
    x.company_name,
    coalesce(x.query_keys, '{}'::text[]),
    coalesce(x.matched_derivative_terms, '{}'::text[]),
    coalesce(x.matched_risk_terms, '{}'::text[]),
    x.provider_score,
    coalesce(x.status, 'new'),
    coalesce(x.need_review, true),
    coalesce(x.official_corroborated, false),
    coalesce(x.raw_metadata, '{}'::jsonb)
  from jsonb_to_recordset(p_rows) as x(
    lead_key text,
    provider text,
    url text,
    source_domain text,
    title text,
    snippet text,
    published_at timestamptz,
    code text,
    company_name text,
    query_keys text[],
    matched_derivative_terms text[],
    matched_risk_terms text[],
    provider_score numeric,
    status text,
    need_review boolean,
    official_corroborated boolean,
    raw_metadata jsonb
  )
  on conflict (lead_key) do update set
    source_domain = coalesce(risk_media_leads.source_domain, excluded.source_domain),
    title = coalesce(risk_media_leads.title, excluded.title),
    snippet = coalesce(risk_media_leads.snippet, excluded.snippet),
    published_at = coalesce(risk_media_leads.published_at, excluded.published_at),
    code = coalesce(risk_media_leads.code, excluded.code),
    company_name = coalesce(risk_media_leads.company_name, excluded.company_name),
    query_keys = array(
      select distinct value
      from unnest(risk_media_leads.query_keys || excluded.query_keys) as value
      order by value
    ),
    matched_derivative_terms = array(
      select distinct value
      from unnest(
        risk_media_leads.matched_derivative_terms || excluded.matched_derivative_terms
      ) as value
      order by value
    ),
    matched_risk_terms = array(
      select distinct value
      from unnest(risk_media_leads.matched_risk_terms || excluded.matched_risk_terms) as value
      order by value
    ),
    provider_score = greatest(
      risk_media_leads.provider_score,
      excluded.provider_score
    ),
    status = case
      when risk_media_leads.status in ('dismissed','corroborated')
        then risk_media_leads.status
      when excluded.status = 'matched' then 'matched'
      else risk_media_leads.status
    end,
    need_review = risk_media_leads.need_review,
    official_corroborated = risk_media_leads.official_corroborated,
    raw_metadata = (risk_media_leads.raw_metadata || excluded.raw_metadata)
      || jsonb_build_object(
        'matched_contexts',
        (
          select coalesce(jsonb_agg(context_value), '[]'::jsonb)
          from (
            select distinct context_value
            from jsonb_array_elements(
              case
                when jsonb_typeof(risk_media_leads.raw_metadata -> 'matched_contexts') = 'array'
                  then risk_media_leads.raw_metadata -> 'matched_contexts'
                else '[]'::jsonb
              end
              || case
                when jsonb_typeof(excluded.raw_metadata -> 'matched_contexts') = 'array'
                  then excluded.raw_metadata -> 'matched_contexts'
                else '[]'::jsonb
              end
            ) as context_value
          ) contexts
        )
      ),
    updated_at = now();

  get diagnostics affected = row_count;
  return affected;
end;
$$;

revoke all on function public.upsert_risk_media_leads(jsonb)
  from public, anon, authenticated;
grant execute on function public.upsert_risk_media_leads(jsonb)
  to service_role;
