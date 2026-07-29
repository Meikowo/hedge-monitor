# Periodic Actuals Production Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production “计划与实际” workspace to the existing GitHub Pages frontend and display the currently verified periodic-report facts from Supabase.

**Architecture:** Keep the existing announcement terminal intact. Add one lazy-loaded periodic workspace backed by a focused `periodic.js` module; `app.js` only supplies the shared API client, company/event context, navigation, and drawer shell. The module joins four public periodic tables in memory and renders one row per company × report × scope.

**Tech Stack:** Static HTML/CSS, vanilla JavaScript, Supabase PostgREST, Node.js assertions, GitHub Pages.

## Global Constraints

- Do not change the four periodic database tables or existing announcement data contracts.
- Do not fetch periodic data during initial event-page startup; fetch it only on first entry to “计划与实际”.
- Display `null` as `未披露`, never as zero.
- Only metrics with both `value_verified=true` and `quote_verified=true` enter the main table.
- Report-level metrics must be labelled `报告级合计` and must not be silently allocated to a scope.
- M5 automatic matching is not implemented in this release; comparisons remain `待口径核对`.
- Reuse the approved light, dense table and right-side evidence drawer design.

---

### Task 1: Production shell and lazy navigation

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Modify: `tests/test_web_structure.mjs`

**Interfaces:**
- Produces the `actuals` view, `#periodic-view`, periodic filters/table/status nodes, and version `v=20260729-1`.
- Exposes `window.HedgeShell` with `apiAll`, `openDrawer`, `escapeHtml`, `safeExternalUrl`, and read-only event context.

- [ ] Add failing structure assertions for the new side-nav entry, periodic workspace IDs, `periodic.js`, and lazy activation hook.
- [ ] Run `node tests/test_web_structure.mjs`; expect failure.
- [ ] Add the hidden periodic workspace and shared shell interface.
- [ ] Extend view switching so `actuals` activates the module and hides the announcement-only controls.
- [ ] Add compact production styles derived from the approved demo.
- [ ] Run the structure test; expect pass.

### Task 2: Join verified periodic facts into scope rows

**Files:**
- Create: `web/periodic.js`
- Create: `tests/test_periodic_production_logic.mjs`

**Interfaces:**
- Exports `buildPeriodicRows(payload, eventRows)`, `metricFor(row, metricType)`, `filterPeriodicRows(rows, filters)`, and `displayMetric(metric)`.
- Consumes `periodic_reports`, `periodic_derivatives`, `periodic_metric_items`, and `periodic_hedge_accounting_items`.

- [ ] Write failing logic tests for scope splitting, report-level labels, verified-only metrics, asset/liability/net separation, hedge-accounting status, `null → 未披露`, and combined filters.
- [ ] Run `node tests/test_periodic_production_logic.mjs`; expect module-not-found failure.
- [ ] Implement pure joins and formatting without DOM access.
- [ ] Compute a net fair-value display only when both verified asset and liability facts exist; mark it `勾稽计算`.
- [ ] Run the logic test; expect pass.

### Task 3: Live loading, table, filters, and evidence drawer

**Files:**
- Modify: `web/periodic.js`
- Modify: `web/index.html`
- Modify: `web/styles.css`
- Modify: `tests/test_web_structure.mjs`

**Interfaces:**
- `window.HedgePeriodic.activate()` lazily fetches the four tables once and renders the workspace.
- The shared detail drawer renders report metadata, all verified facts, hedge-accounting evidence, and the annual-report PDF link.

- [ ] Add failing structure assertions for four API paths, 20-second timeout behavior inherited from `HedgeShell.apiAll`, filter bindings, row detail buttons, and explicit failure state.
- [ ] Fetch the four tables in parallel on first activation and show progress/error text.
- [ ] Render the approved high-density columns, including period flow, margin, derivative assets, derivative liabilities, net fair value, P&L components, and hedge accounting.
- [ ] Bind year, scope, accounting-status, evidence and text filters; all filters intersect.
- [ ] Render report-level evidence in the shared right drawer and preserve annual-report page references.
- [ ] Run structure and logic tests; expect pass.

### Task 4: Regression, documentation, and release

**Files:**
- Modify: `docs/PROJECT.md`
- Modify: `docs/worklogs/worklog_2026-07-29.md`

**Interfaces:**
- Local/online entry point remains `web/index.html`; GitHub Pages deploys from `main`.

- [ ] Run `node --check web/app.js` and `node --check web/periodic.js`.
- [ ] Run periodic logic, web structure, web bootstrap, demo regression, and Python periodic tests.
- [ ] Use the public API to confirm 40 profiles and at least 265 verified metric facts load without startup regression.
- [ ] Record the extraction fixes, 40-report checkpoint, production frontend scope, remaining M5 boundary, and rollback commit in project documents.
- [ ] Commit only intended files, push `main` through the GitHub connector, wait for Pages, and verify the production asset version and “计划与实际” view.

