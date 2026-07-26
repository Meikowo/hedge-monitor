# M4 POC Contract Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the periodic-report POC to the approved PRD v1.5 contract before any further paid extraction, then prepare a six-report validation batch.

**Architecture:** Keep the existing report → summary → metric-fact pipeline and add only backward-compatible columns, metric types, and a hedge-accounting detail table. Pure normalization and verification remain testable without Supabase or LLM calls. The six-report batch reuses the existing 30-company POC and performs metadata/page location before extraction.

**Tech Stack:** Python 3.12, unittest, PostgreSQL/Supabase migrations, GitHub Actions, MiniMax-compatible JSON extraction.

## Global Constraints

- Do not call the LLM while upgrading or locating samples.
- Preserve existing `period_pnl`, `hedge_accounting`, and extracted rows for backward compatibility.
- New facts are reported values only; no estimation, allocation, or derived category split.
- `null` is not `0`.
- Report-level totals use `fact_level=report` and `scope=null`; they must not be copied into category aggregates.
- New public tables must enable RLS and use explicit Data API grants.

---

### Task 1: POC v1.5 normalization contract

**Files:**
- Modify: `tests/test_periodic.py`
- Modify: `scripts/prompt_periodic.py`
- Modify: `scripts/extract_periodic_reports.py`

**Interfaces:**
- `normalize(result, body)` returns a report summary with hedge-accounting status/type/reason/evidence plus metric facts.
- Metric facts add `fact_level`, `account_name`, `is_restricted`, and `counterparty`.

- [x] Add failing tests proving separate comprehensive/disposal/FV-change metrics survive normalization, report-level facts cannot carry a category scope, margin metadata is retained, and explicit hedge-accounting status/reason is normalized.
- [x] Run `python -m unittest tests.test_periodic -v`; expect failures against the old contract.
- [x] Upgrade the prompt contract and implement the minimum normalizer changes.
- [x] Re-run the periodic tests; expect pass.

### Task 2: Backward-compatible database migration

**Files:**
- Create: `db/004_periodic_v15.sql`
- Modify: `docs/schema_snapshot.md`

**Interfaces:**
- Adds report-level hedge-accounting fields to `periodic_derivatives`.
- Extends `periodic_metric_items` metric types and attribution/context columns.
- Creates `periodic_hedge_accounting_items` with RLS and explicit grants.

- [x] Write idempotent SQL that retains old metric types while adding the v1.5 types.
- [x] Backfill `fact_level` from existing `scope`, then enforce its closed set.
- [x] Add indexes on report/detail lookups; enable RLS and explicit read/service grants.
- [x] Update the human-readable schema snapshot and security notes.

### Task 3: Six-report validation batch

**Files:**
- Create: `config/annual_validation_2025.csv`
- Modify: `.github/workflows/periodic-poc.yml`
- Modify: `tests/test_periodic.py`

**Interfaces:**
- Validation sample contains JinkoSolar, Beyondsoft, Gree, DBN, CIMC, and Zhuzhou Smelter Group.
- Workflow `sample_set=validation6|poc30` passes the selected CSV to metadata and locate stages.

- [x] Add a failing test that loads the validation CSV and confirms six unique codes and all three scope groups.
- [x] Add the six-company CSV, copying deterministic locator terms from the 30-company POC.
- [x] Add a workflow sample-set choice; keep `validation6` as the safe default and leave extract confirmation mandatory.
- [x] Re-run tests and inspect the rendered workflow command arguments.

### Task 4: Documentation and handoff

**Files:**
- Modify: `docs/M4A_POC.md`
- Modify: `docs/PROJECT.md`
- Create: `docs/worklogs/worklog_2026-07-26-3.md`

**Interfaces:**
- Documents the gate: 6 human-reviewed reports → 30-report POC → production batches.

- [x] Record the v1.5 contract, validation sample, extraction results, and acceptance criteria.
- [x] Run Python syntax checks, unit tests, Demo regressions, and workflow/YAML structural checks.
- [x] Report whether remote Supabase and GitHub synchronization remain pending.
