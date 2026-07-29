# Periodic Export and Compatible Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add filtered CSV export to “计划与实际” and show safe totals for compatible same-scope metric facts while preserving every source fact in the evidence drawer.

**Architecture:** Keep aggregation and CSV generation as exported pure functions in `web/periodic.js`; the browser layer only reads current filters, downloads a UTF-8 BOM CSV, and shows feedback. No database schema or extraction rule changes are needed.

**Tech Stack:** Native JavaScript ES modules, static HTML/CSS, Node assertion tests, GitHub Pages.

## Global Constraints

- Aggregate only facts with the same metric type, fact level, scope, currency, unit, and time basis.
- Do not aggregate report-level facts because they may contain a total and its subtotals.
- Every aggregated item must contain a non-empty finite value and be distinguishable by underlying or account name.
- Preserve individual source facts, pages, and quotes in the detail drawer.
- Never substitute fair-value-change P&L or OCI for comprehensive P&L.
- Export the full current filtered result with UTF-8 BOM; do not export only visible rows.
- Do not modify Supabase data, schema, RLS, or annual-report extraction scripts.

---

### Task 1: Compatible metric aggregation

**Files:**
- Modify: `tests/test_periodic_production_logic.mjs`
- Modify: `web/periodic.js`

**Interfaces:**
- Consumes: `metricFor(row, metricType)` and the existing verified metric shape.
- Produces: metric objects with `value`, `multipleCount`, `items`, and `isAggregated`.

- [x] Add a two-underlying commodity fixture and assertions for purchase, sale, and fair-value-change totals.
- [x] Run `node tests/test_periodic_production_logic.mjs`; expect the old logic to fail because it returns `value: null`.
- [x] Implement conservative compatibility checks and numeric summation in `chooseMetric`.
- [x] Keep incompatible units or ambiguous duplicate facts as `N 项事实`.
- [x] Update table notes to display `合计 · N 项` for aggregated values.
- [x] Run the production logic test and confirm all assertions pass.

### Task 2: Filtered CSV export

**Files:**
- Modify: `tests/test_periodic_production_logic.mjs`
- Modify: `tests/test_web_structure.mjs`
- Modify: `web/periodic.js`
- Modify: `web/index.html`

**Interfaces:**
- Produces: `periodicRowsToCsv(rows): string`.
- Browser event consumes `filterPeriodicRows(browserState.rows, browserState.filters)`.

- [x] Add failing tests for filtered row content, safe totals, units, fact counts, PDF URL, comma/quote escaping, and UTF-8 BOM.
- [x] Add `#periodic-export-button` beside the current result count.
- [x] Implement pure CSV serialization with one row per company × period × scope.
- [x] Bind the button to the current filtered rows, reject empty exports, and download `hedge-periodic-actuals-YYYY-MM-DD.csv`.
- [x] Bump HTML, CSS, app, and periodic asset versions to `v=20260729-2`.
- [x] Run the logic and structure tests and confirm they pass.

### Task 3: Verification, documentation, and release

**Files:**
- Modify: `docs/PROJECT.md`
- Modify: `docs/worklogs/worklog_2026-07-29.md`

**Interfaces:**
- Consumes: the completed frontend and current 40-report database snapshot.
- Produces: reproducible verification evidence and a staged 2025 extraction estimate.

- [x] Run JavaScript syntax checks, annual-report Python tests, frontend logic/structure tests, demo regression tests, and the real public API bootstrap test.
- [x] Verify locally that 锐新科技 shows purchase `3,505.10 万元`, sale `3,558.64 万元`, and fair-value-change P&L `53.54 万元`.
- [x] Document the aggregation rule, export behavior, rollout gate, 2025 report counts, and measured timing.
- [ ] Publish only reviewed frontend, tests, spec/plan, project documentation, and worklog files as a non-force fast-forward to `main`.
- [ ] Wait for GitHub Pages and verify the production asset version, 锐新科技 values, filters, evidence drawer, and CSV export.
