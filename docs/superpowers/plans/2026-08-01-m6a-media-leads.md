# M6a Media Leads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free-quota Tavily news POC that stores private, unverified derivatives-risk leads without changing formal risk cases.

**Architecture:** A focused Python collector reads capped query groups, calls Tavily News Search, applies a deterministic derivatives-and-risk gate, normalizes URLs, optionally matches companies, and upserts into a private Supabase table. A separate workflow runs twice daily and supports a safe manual dry-run.

**Tech Stack:** Python 3.12, requests, PyYAML, Supabase PostgREST, PostgreSQL RLS, GitHub Actions.

## Global Constraints

- Maximum 12 basic Tavily searches per run and 10 results per search.
- No article full text, MiniMax call, public frontend exposure, or automatic formal-case promotion.
- Secrets remain only in local `.env` or GitHub repository Secrets.

---

### Task 1: Private media-lead contract

**Files:**
- Create: `db/006_risk_media_leads.sql`
- Modify: `db/000_reset.sql`, `db/verify.sql`, `docs/schema_snapshot.md`
- Test: `tests/test_risk_media.py`

**Interfaces:**
- Produces: private `risk_media_leads` table keyed by `lead_key`.

- [ ] Write a failing contract test that requires RLS, service-role-only grants, no anonymous policy, and the lead/corroboration fields.
- [ ] Run `python -m unittest tests.test_risk_media.RiskMediaSchemaTest -v` and confirm the migration is missing.
- [ ] Add the table, indexes, update trigger, grants, reset and verification SQL.
- [ ] Re-run the schema test and confirm it passes.

### Task 2: Tavily collector

**Files:**
- Create: `config/risk_media_queries.yml`, `scripts/fetch_risk_media_leads.py`
- Test: `tests/test_risk_media.py`

**Interfaces:**
- Produces: `build_search_payload(query, max_results, time_range)`, `prepare_leads(results, query_key)`, `match_companies(rows, companies)`, and a CLI with `--write`.

- [ ] Write failing tests for safe Tavily parameters, the 12/10 caps, dual-term relevance, URL deduplication, and company matching.
- [ ] Run the focused tests and confirm failures are caused by the missing collector.
- [ ] Implement the smallest collector that satisfies the tests and uses `sb_upsert(..., on_conflict="lead_key")` only under `--write`.
- [ ] Re-run focused and full Python tests.

### Task 3: Scheduled workflow and documentation

**Files:**
- Create: `.github/workflows/risk-media.yml`, `docs/worklogs/worklog_2026-08-01.md`
- Modify: `.env.example`, `README.md`, `docs/PROJECT.md`, `docs/PRD.md`
- Test: `tests/test_risk_media.py`

**Interfaces:**
- Consumes: `TAVILY_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` repository secrets.

- [ ] Write a failing workflow contract test for two schedules, secret references, dry-run default and hard caps.
- [ ] Add the workflow and document the private media-lead boundary and free-credit budget.
- [ ] Run all tests, compile the collector, and parse the workflow YAML.
- [ ] Apply and verify the Supabase migration, publish an atomic GitHub commit, then run a one-query dry-run and inspect its artifact/logs.
