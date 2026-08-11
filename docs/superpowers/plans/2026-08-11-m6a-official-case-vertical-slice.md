# M6a Official Case Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the first three verified derivatives-loss cases from existing official CNINFO announcements into the four official risk tables and expose them through the production risk workspace.

**Architecture:** A deterministic publisher reads already-extracted official announcements, applies a strict actual-loss gate, maps accepted rows into the existing risk schema, and idempotently upserts source documents, cases, relations, and evidence. A guarded GitHub Actions workflow runs the publisher without changing database structure or browser permissions.

**Tech Stack:** Python 3.12, unittest, Supabase PostgREST, GitHub Actions, vanilla JavaScript frontend.

## Global Constraints

- Do not call an LLM for documents already present in `announcements` and `extractions`; download only selected PDFs for quote verification.
- Do not publish management-policy thresholds, hypothetical risks, no-loss statements, or ordinary FX losses.
- Do not expose `SUPABASE_SERVICE_ROLE_KEY`, `.env`, private media leads, or output snapshots.
- Keep all writes idempotent and retain official HTTPS document URLs and page-level quotes.
- Push through the GitHub connector to `main` with `force=false` only after full verification.

---

### Task 1: Deterministic official-case publisher

**Files:**
- Create: `scripts/publish_official_risk_cases.py`
- Create: `tests/test_official_risk_cases.py`

**Interfaces:**
- Consumes: normalized `announcements` and `extractions` rows returned by `sb_select`.
- Produces: `assess_official_candidate(row)`, `build_official_bundle(row)`, `select_publishable(rows, limit)`, and `persist_bundles(bundles, ...)`.

- [x] Write failing tests that accept an actual loss quote and reject a management-policy threshold, “未产生浮动亏损”, and ordinary汇兑损失.
- [x] Run `python -m unittest tests.test_official_risk_cases -v` and confirm missing-module/API failures.
- [x] Implement the strict gate, selected-PDF quote verification, stable keys, exact amount parsing, four-table mappings, evidence verification flags, media corroboration patch, dry-run snapshot, and idempotent write order.
- [x] Run `python -m unittest tests.test_official_risk_cases -v` and confirm all publisher tests pass.

### Task 2: Guarded production workflow

**Files:**
- Create: `.github/workflows/risk-official.yml`
- Modify: `tests/test_risk_pipeline.py`

**Interfaces:**
- Consumes: `scripts/publish_official_risk_cases.py --limit <n> [--write]`.
- Produces: manual dry-run/write controls and a daily automatic write run using `risk-sources` concurrency.

- [x] Add a failing workflow contract test requiring schedule, manual dry-run, `I_UNDERSTAND`, `limit=3`, official snapshot artifact, and both Supabase secrets.
- [x] Run the workflow contract test and confirm it fails because the workflow is absent.
- [x] Add `risk-official.yml` with a daily Beijing-time schedule, guarded manual inputs, Python setup, publisher invocation, and artifact upload.
- [x] Run the workflow contract and publisher tests and confirm they pass.

### Task 3: Production data and frontend verification

**Files:**
- Modify: `tests/test_risk_production_bootstrap.mjs`
- Modify: `docs/PROJECT.md`
- Create: `docs/worklogs/worklog_2026-08-11-2.md`

**Interfaces:**
- Consumes: three official cases and their source/evidence relations in Supabase.
- Produces: real-API assertions and an auditable project checkpoint.

- [x] Extend the real API bootstrap test to require at least three official cases, one source relation and one evidence row per official case, and no duplicate media row for a corroborated case.
- [x] Run the bootstrap test before production write and confirm it fails on zero official cases.
- [x] Run the publisher dry-run, review the three selected rows, then run write mode and query all four tables for counts and referential completeness.
- [x] Run complete Python and Node regressions, real API bootstrap tests, Security Advisor, syntax checks, and a secret-value scan.
- [x] Update `PROJECT.md` and the phase worklog with exact counts, cases, tests, workflow status, commit, and rollback baseline.
- [x] Publish only reviewed files through the GitHub connector using an atomic fast-forward commit and verify Actions plus `https://www.hedgemonitor.site/`.
