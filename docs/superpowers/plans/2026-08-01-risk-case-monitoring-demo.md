# Risk Case Monitoring Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, interactive local Demo for the “风险案例监控” workspace so the user can approve the information architecture before production data exists.

**Architecture:** Create a dependency-free vanilla JavaScript application under `web-demo/risk-cases/`. Keep synthetic fixture data in `data.js`; keep pure filtering, formatting, CSV, document sorting and HTML rendering functions in `app.js` so Node tests can execute them without a browser. The page reuses the existing light research-terminal shell and never connects to Supabase.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, Node.js built-in `assert`, `fs`, and `vm` modules.

## Global Constraints

- All records must be visibly marked as fixed demonstration data and must not be presented as real cases.
- Do not read Supabase, Tavily, `.env`, `config.js`, or any external API.
- Do not modify `web/` or expose a production navigation entry.
- Preserve original currency and unit; render null as “未披露” and numeric zero as `0`.
- Show only the formal-case shape; do not create a media-lead review interface or risk score.
- Reuse the existing light, dense research-terminal visual language and provide a full-screen detail panel on mobile.

---

### Task 1: Define the Demo contract with failing tests

**Files:**
- Create: `tests/test_risk_demo_structure.mjs`
- Create: `tests/test_risk_demo_logic.mjs`

**Interfaces:**
- Consumes: planned files under `web-demo/risk-cases/`.
- Produces: executable structural and behavioral contracts for the fixture, filters, amount display, document ordering, CSV, table row and detail drawer.

- [ ] **Step 1: Write the structure test**

Assert that `index.html` contains the active `risk-cases` navigation item, top metrics, search/year/risk/source/status filters, reset and export buttons, result count, table body, empty state, drawer, overlay and local asset references. Assert that the HTML contains no Supabase, service-role, remote scripts or `config.js` references.

- [ ] **Step 2: Write the behavior test**

Load `data.js` and `app.js` in a Node `vm` context and assert: six fixtures exist; intersecting filters return the expected ID; null and zero amounts differ; documents sort oldest-to-newest; CSV starts with a BOM and includes official URLs; rendered rows expose a detail button; rendered drawers include “事件事实”“监管文档链”“逐字段证据”.

- [ ] **Step 3: Run both tests and verify RED**

Run: `node tests/test_risk_demo_structure.mjs; node tests/test_risk_demo_logic.mjs`

Expected: both commands fail because `web-demo/risk-cases/` does not exist.

### Task 2: Implement fixture data and pure application logic

**Files:**
- Create: `web-demo/risk-cases/data.js`
- Create: `web-demo/risk-cases/app.js`
- Test: `tests/test_risk_demo_logic.mjs`

**Interfaces:**
- Consumes: `globalThis.riskCaseRows` fixture array.
- Produces: `globalThis.RiskCasesDemo` with `displayAmount`, `filterCases`, `sortDocuments`, `casesToCsv`, `renderTableRow`, and `renderDrawer`.

- [ ] **Step 1: Add six clearly synthetic case fixtures**

Each record includes stable ID, date, company/code, province/industry, risk types, instruments, underlyings, amount/currency/unit, regulatory action, outcome, source organization, status, summary, official-style documents and verified evidence rows. Use synthetic company names/codes and `example.invalid` URLs.

- [ ] **Step 2: Implement minimal pure functions**

Implement safe HTML escaping, null-safe amount formatting, intersecting filters, chronological document ordering, UTF-8 BOM CSV serialization, high-density table row rendering and evidence drawer rendering.

- [ ] **Step 3: Run the logic test and verify GREEN**

Run: `node tests/test_risk_demo_logic.mjs`

Expected: exit code 0 and `risk case demo logic ok`.

### Task 3: Build the interactive research-terminal page

**Files:**
- Create: `web-demo/risk-cases/index.html`
- Create: `web-demo/risk-cases/styles.css`
- Modify: `web-demo/risk-cases/app.js`
- Test: `tests/test_risk_demo_structure.mjs`

**Interfaces:**
- Consumes: pure functions and fixtures from Task 2.
- Produces: local page with filtering, reset, CSV export, row details, overlay/close/Escape behavior and responsive layout.

- [ ] **Step 1: Create the page shell**

Add the five-workspace sidebar with “风险案例监控” active, a fixed-demo badge, four compact metrics, filter toolbar, export/reset actions, ten-column risk table, empty state, overlay and right detail drawer.

- [ ] **Step 2: Add the visual system**

Use white surfaces, zinc borders, 9–13 px data typography, tabular numbers, restrained red/amber/blue/green status badges, sticky table headers, a 620 px desktop drawer and a full-width mobile drawer.

- [ ] **Step 3: Bind interactions**

Populate filter options from fixtures, apply filters on input/change, render metrics and rows, export the current filtered set, open details from each row, and close through the button, overlay or Escape key.

- [ ] **Step 4: Run the structure and logic tests**

Run: `node tests/test_risk_demo_structure.mjs; node tests/test_risk_demo_logic.mjs; node --check web-demo/risk-cases/app.js; node --check web-demo/risk-cases/data.js`

Expected: all commands exit 0 with no syntax errors.

### Task 4: Visual verification and stage documentation

**Files:**
- Modify if visual defects are found: `web-demo/risk-cases/index.html`
- Modify if visual defects are found: `web-demo/risk-cases/styles.css`
- Modify if visual defects are found: `web-demo/risk-cases/app.js`
- Modify: `docs/PROJECT.md`
- Modify: `docs/worklogs/worklog_2026-08-01.md`

**Interfaces:**
- Consumes: complete local Demo.
- Produces: a visually verified entry point and an M6b-1 project checkpoint.

- [ ] **Step 1: Open and inspect the local page**

Open `web-demo/risk-cases/index.html`; verify desktop table density, horizontal scrolling, filters, export control and drawer hierarchy. Inspect a mobile-width screenshot and confirm navigation remains usable and the drawer is full-screen.

- [ ] **Step 2: Correct only observed defects**

Make focused HTML/CSS/JS changes for issues visible in the inspection, then rerun both Demo tests and syntax checks.

- [ ] **Step 3: Record the checkpoint**

Update `PROJECT.md` and the stage worklog with the local entry path, fixture-only boundary, implemented interactions, verification results and the unchanged production release gate.

- [ ] **Step 4: Run final verification**

Run: `node tests/test_risk_demo_structure.mjs; node tests/test_risk_demo_logic.mjs; node --check web-demo/risk-cases/app.js; node --check web-demo/risk-cases/data.js`

Expected: all commands exit 0. Confirm `rg -n "supabase|service[_-]?role|TAVILY|LLM_API_KEY" web-demo/risk-cases` returns no matches.
