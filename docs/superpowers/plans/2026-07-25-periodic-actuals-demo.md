# Periodic Actuals Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated local static demo of the “计划与实际” workspace without changing the production frontend or connecting to Supabase.

**Architecture:** Create a small ES-module application under `web-demo/periodic-actuals/`. Fixture data and pure filtering/formatting logic remain separate from DOM rendering so Node tests can validate behavior without new dependencies. The page reuses the current light, dense research-terminal visual language and opens record evidence in a right-side drawer.

**Tech Stack:** HTML5, CSS, vanilla JavaScript ES modules, Node.js built-in test/assert APIs.

## Global Constraints

- Do not modify `web/`, Supabase, workflows, migrations, or production configuration.
- Do not make network requests or include any credential.
- Use fixed illustrative data, including the verified JinkoSolar 2025FY figures.
- `null` renders as `未披露`, never `0`.
- Desktop uses a dense table and right drawer; 375px mobile remains usable through horizontal table scrolling.

---

### Task 1: Static workspace shell

**Files:**
- Create: `tests/test_periodic_demo_structure.mjs`
- Create: `web-demo/periodic-actuals/index.html`
- Create: `web-demo/periodic-actuals/styles.css`

**Interfaces:**
- Produces DOM IDs `period-filter`, `category-filter`, `accounting-filter`, `match-filter`, `search-input`, `actuals-body`, `result-count`, `detail-drawer`, `drawer-content`, and `drawer-close`.

- [ ] Write a structure test that reads `index.html` and asserts the active “计划与实际” navigation item, all filters, the research table, drawer, local `styles.css`/`app.js` references, and absence of `supabase`, `config.js`, external script URLs, and service-role text.
- [ ] Run `node tests/test_periodic_demo_structure.mjs`; expect failure because the demo does not exist.
- [ ] Add semantic HTML for the existing four-item workspace navigation, summary strip, filters, 13-column table, empty table body, and accessible drawer.
- [ ] Add CSS tokens and responsive rules matching the existing white, neutral, fine-border, compact style. Use `min-width: 1320px` on the data table and `overflow-x: auto` on its wrapper.
- [ ] Re-run the structure test; expect pass.

### Task 2: Fixture contract and pure logic

**Files:**
- Create: `tests/test_periodic_demo_logic.mjs`
- Create: `web-demo/periodic-actuals/data.js`
- Create: `web-demo/periodic-actuals/app.js`

**Interfaces:**
- `data.js` exports `periodicActualRows`.
- `app.js` exports:
  - `filterRows(rows, filters): Array`
  - `displayValue(value, suffix = ""): string`
  - `accountingLabel(row): string`
  - `evidenceProgress(row): string`

- [ ] Write logic tests for combined period/category/accounting/match/search filters, `null → 未披露`, explicit “未应用 · 原因未披露”, and evidence progress.
- [ ] Run `node tests/test_periodic_demo_logic.mjs`; expect module-not-found failure.
- [ ] Add six illustrative company-period-category rows. The JinkoSolar row must use:
  - comprehensive P&L `-3,474.88 万元`
  - disposal investment income `2,392.96 万元`
  - fair-value-change P&L `-5,867.84 万元`
  - derivative assets `5,892.25 万元`
  - derivative liabilities `5,612.87 万元`
  - net fair value `279.38 万元`
  - hedge accounting status `未应用`
  - non-application reason `null`
- [ ] Implement the four pure functions with exact-match filters and case-insensitive free-text search over company, ticker, scope, underlying, and instrument.
- [ ] Run the logic and structure tests; expect both pass.

### Task 3: Rendering, filters, and evidence drawer

**Files:**
- Modify: `web-demo/periodic-actuals/app.js`
- Modify: `web-demo/periodic-actuals/styles.css`
- Modify: `tests/test_periodic_demo_structure.mjs`

**Interfaces:**
- Consumes `periodicActualRows` and the DOM IDs from Task 1.
- Produces rendered table rows, summary counts, filter updates, drawer open/close behavior, and Escape-key dismissal.

- [ ] Extend the structure test to assert that `app.js` binds all four filter controls, search input, row buttons, drawer close, overlay close, and Escape.
- [ ] Run the structure test; expect failure because bindings are absent.
- [ ] Render summary metrics and table rows from fixtures. Show status badges with visible text; use `data-row-id` buttons for details.
- [ ] Populate the drawer with four sections: 公告计划、定期报告实际、套期会计、核对与证据. Include JinkoSolar reconciliation equations and page references 43/44, 235/236, 259, and 260/261.
- [ ] Bind filters and drawer behavior, then run both Node tests; expect pass.

### Task 4: Visual verification and handoff

**Files:**
- Modify only if visual defects are found: `web-demo/periodic-actuals/index.html`, `styles.css`, `app.js`
- Update: `docs/worklogs/worklog_2026-07-25.md`

**Interfaces:**
- Local entry point: `web-demo/periodic-actuals/index.html`

- [ ] Run `node --check web-demo/periodic-actuals/app.js`.
- [ ] Run both demo tests and the existing `node tests/test_web_structure.mjs`; all must pass, proving production frontend references remain intact.
- [ ] Open the local demo in the in-app browser and inspect desktop layout, filters, JinkoSolar drawer, Escape close, and a 375px mobile viewport.
- [ ] Fix only observed defects and repeat checks.
- [ ] Record the local demo path, verified behavior, unchanged production scope, and rollback method in the worklog.

### Task 5: Split JinkoSolar commodity and FX facts

**Files:**
- Modify: `web-demo/periodic-actuals/data.js`
- Modify: `web-demo/periodic-actuals/app.js`
- Modify: `tests/test_periodic_demo_logic.mjs`

**Interfaces:**
- Two rows share `reportTotals`, while category-level amounts remain separate.

- [ ] Add failing assertions for two JinkoSolar rows and the exact p43 category values.
- [ ] Add `jinko-2025fy-fx` and `jinko-2025fy-commodity`; keep report-level totals labeled and unallocated.
- [ ] Render report-level totals in the drawer without duplicating them as category facts.
- [ ] Run the logic test and expect pass.

### Task 6: Column-level header filters

**Files:**
- Modify: `web-demo/periodic-actuals/index.html`
- Modify: `web-demo/periodic-actuals/styles.css`
- Modify: `web-demo/periodic-actuals/app.js`
- Modify: `tests/test_periodic_demo_structure.mjs`
- Modify: `tests/test_periodic_demo_logic.mjs`

**Interfaces:**
- `filterRows(rows, filters)` consumes `company`, `underlying`, `planBasis`, `flowState`, `netState`, `pnlState`, `disposalState`, `fvState`, `method`, and `evidenceState` in addition to existing filters.

- [ ] Add failing behavior tests for categorical, numeric-state, method, and evidence filters.
- [ ] Add one compact filter control under every table heading.
- [ ] Bind all header controls into the existing intersection filter and reset action.
- [ ] Run Demo tests and production frontend regression tests.

### Task 7: Margin and gross fair-value columns

**Files:**
- Modify: `web-demo/periodic-actuals/index.html`
- Modify: `web-demo/periodic-actuals/styles.css`
- Modify: `web-demo/periodic-actuals/data.js`
- Modify: `web-demo/periodic-actuals/app.js`
- Modify: `tests/test_periodic_demo_structure.mjs`
- Modify: `tests/test_periodic_demo_logic.mjs`

**Interfaces:**
- Each category row adds `marginBalance`, `marginUnit`, and `marginAccount`.
- `filterRows` accepts `marginState`, `assetState`, `liabilityState`, and `netState`.

- [x] Add failing tests for the four independent columns, Jinko report-level labels, and numeric-state filters.
- [x] Add the margin, derivative asset, derivative liability, and net fair-value columns with one filter per heading.
- [x] Preserve Jinko category net values while labeling unallocated gross asset/liability facts as report-level totals.
- [x] Add margin and gross fair-value fields to the detail drawer and fixture contract.
- [x] Run full Demo and production frontend regression verification.
