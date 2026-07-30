# M6a Risk Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable M6a slice: independent risk schema, SSE official-source discovery, deterministic relevance gating, idempotent candidate persistence, and a manual POC workflow.

**Architecture:** Keep transport, normalization, business gating, and persistence separate. The SSE adapter returns normalized source documents; `risk_relevance.py` evaluates text without database access; `fetch_risk_documents.py` orchestrates discovery and optional Supabase upsert.

**Tech Stack:** Python 3.12, requests, PyMuPDF, Supabase PostgREST, PostgreSQL/RLS, GitHub Actions.

## Global Constraints

- Do not modify the current frontend, announcement tables, periodic-report tables, or their workflows.
- Only official source URLs are accepted.
- A candidate is not a formal risk case until model extraction and evidence verification pass.
- Public clients receive SELECT only; service_role is never exposed.

---

### Task 1: Risk schema contract

**Files:**
- Create: `db/005_derivative_risk_cases.sql`
- Modify: `db/000_reset.sql`
- Modify: `db/verify.sql`
- Test: `tests/test_risk_pipeline.py`

**Interfaces:**
- Produces four public tables: `risk_source_documents`, `derivative_risk_cases`, `risk_case_documents`, `risk_case_evidence`.

- [x] Write schema-structure tests that require the four tables, closed risk-type constraint, RLS, anon SELECT grants, and service-role writes.
- [x] Run `python -m unittest tests.test_risk_pipeline -v` and verify the tests fail because migration 005 does not exist.
- [x] Add migration 005 and reset/verification coverage.
- [x] Re-run the focused tests and verify they pass.

### Task 2: SSE source adapter

**Files:**
- Create: `scripts/risk_sources/__init__.py`
- Create: `scripts/risk_sources/sse.py`
- Test: `tests/test_risk_pipeline.py`

**Interfaces:**
- Produces `iter_documents(kind, start_date, end_date, max_pages=None) -> Iterator[dict]`.
- Produces `normalize_document(raw, kind) -> dict`.
- Produces `unwrap_jsonp(text) -> dict`.

- [x] Add failing tests with literal SSE JSONP fixtures for inquiry/measure normalization, official URL enforcement, pagination, and malformed JSONP.
- [x] Run the focused tests and confirm expected failures for missing module/functions.
- [x] Implement the minimal adapter with retries, referer headers, date filters, page limit and polite sleep.
- [x] Re-run focused tests and keep them green.

### Task 3: Derivatives-risk relevance gate

**Files:**
- Create: `scripts/risk_relevance.py`
- Test: `tests/test_risk_pipeline.py`

**Interfaces:**
- Produces `assess_relevance(title, text, source_type) -> dict` with `candidate`, `relevant`, `matched_derivative_terms`, `matched_risk_terms`, `reason`.

- [x] Add failing table-driven tests for direct derivatives loss/violation, generic policy language, law-title-only mentions, and unrelated inquiry letters.
- [x] Run the focused tests and confirm failures for the missing gate.
- [x] Implement normalized matching and bounded co-occurrence windows.
- [x] Re-run focused tests and keep them green.

### Task 4: Discovery orchestration and persistence

**Files:**
- Create: `scripts/fetch_risk_documents.py`
- Test: `tests/test_risk_pipeline.py`

**Interfaces:**
- Consumes normalized SSE documents and `assess_relevance`.
- Produces candidate rows for `risk_source_documents`, CSV snapshots, and optional `sb_upsert(..., on_conflict="source_doc_id")`.

- [x] Add failing tests for dry-run no-write behavior, deterministic IDs/statuses, duplicate collapse, and write-mode upsert arguments.
- [x] Run focused tests and confirm expected failures.
- [x] Implement CLI options `--source`, `--kind`, `--start-date`, `--end-date`, `--max-pages`, `--limit`, and `--write`.
- [x] Re-run focused tests and the complete Python test suite.

### Task 5: Manual POC workflow and documentation

**Files:**
- Create: `.github/workflows/risk-poc.yml`
- Modify: `docs/PROJECT.md`
- Modify: `docs/schema_snapshot.md`
- Create: `docs/worklogs/worklog_2026-07-30.md`
- Test: `tests/test_risk_pipeline.py`

**Interfaces:**
- Workflow dispatches SSE inquiry/measure discovery for a bounded date range and defaults to dry-run.

- [x] Add a failing workflow-structure test for manual dispatch, bounded limits, explicit write confirmation, independent concurrency, secrets, and artifact retention.
- [x] Add the workflow with `confirm_write` guard; do not add a schedule yet.
- [x] Update project/schema/worklog documents with the M6a-1 boundary and next gate.
- [x] Run Python tests, YAML parse, and Python syntax checks.

### Task 6: Supabase and live-source verification

**Files:**
- No new production files.

**Interfaces:**
- Applies `db/005_derivative_risk_cases.sql` to project `uwxzftnpsrqlvetwjjjj`.

- [x] Run Supabase advisors before applying the migration.
- [x] Apply migration 005 and query information_schema/RLS/policies/grants to verify it.
- [x] Run a bounded SSE dry-run probe for both inquiry and measure sources.
- [x] Review the generated candidate distribution before any write-mode ingestion.
