# Periodic Automatic Batches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely automate 2025 annual-report location and extraction in bounded six-hour batches without repeatedly charging for failed reports.

**Architecture:** Extend the existing periodic POC workflow with a scheduled path while preserving its manual inputs. Move locator selection into a testable query builder and isolate per-report extraction failures by marking them `failed`; scheduled runs ignore that state until a human explicitly retries it.

**Tech Stack:** GitHub Actions YAML, Python 3.12, `unittest`, PyYAML, Supabase PostgREST.

## Global Constraints

- Scheduled runs use `config/annual_priority_2025.csv`, locate 12 and extract 6.
- Scheduled queries hard-filter `fiscal_year=2025` and `report_type=annual`.
- Cron is UTC `45 22,4,10,16 * * *`.
- Accepted human-reviewed reports are never force-overwritten.
- Failed reports are not automatically retried.
- No schema, RLS, frontend, announcement workflow or secret changes.
- Local workspace has no Git metadata; publish only after tests through the GitHub connector as a non-force fast-forward to `main`.

---

### Task 1: Query and failure-state regression tests

**Files:**
- Modify: `tests/test_periodic.py`
- Modify: `scripts/locate_periodic_pages.py`
- Modify: `scripts/extract_periodic_reports.py`

**Interfaces:**
- Produces: `build_report_query(terms, limit, report_ids=None, retry_failed=False) -> dict[str, str]` in the locator.
- Produces: `quarantine_report(report_id, error, dry_run=False) -> None` in the extractor.

- [x] **Step 1: Write failing locator tests**

Add tests asserting that default selection uses `status=eq.discovered`, explicit retry uses
`status=in.(discovered,failed)`, and report IDs bypass status filtering.

- [x] **Step 2: Run the focused tests and confirm RED**

Run: `.venv\Scripts\python.exe -m unittest tests.test_periodic.PeriodicNormalizationTest.test_periodic_locator_default_excludes_failed tests.test_periodic.PeriodicNormalizationTest.test_periodic_locator_can_explicitly_retry_failed -v`

Expected: FAIL because the locator query builder does not yet exist.

- [x] **Step 3: Implement the locator query builder and CLI flag**

Parse `--retry-failed`, call the query builder from `main`, and keep explicit `--report-id`
selection independent from status.

- [x] **Step 4: Add and run extraction quarantine tests**

Patch `sb_update`, call `quarantine_report("r1", RuntimeError("boom"))`, and assert a
`periodic_reports` update to `status=failed`; assert `dry_run=True` performs no update.

- [x] **Step 5: Implement minimal extraction quarantine helper**

Store `抽取失败: <ExceptionType>: <message>` truncated to 500 characters. Invoke it when a
single report raises, then re-raise so the workflow fails closed.

- [x] **Step 6: Run focused tests and confirm GREEN**

Run: `.venv\Scripts\python.exe -m unittest tests.test_periodic.PeriodicNormalizationTest -v`

Expected: all normalization and state tests pass.

### Task 2: Scheduled workflow

**Files:**
- Modify: `.github/workflows/periodic-poc.yml`
- Modify: `tests/test_periodic.py`

**Interfaces:**
- Consumes: locator `--retry-failed` and extractor `--confirm-llm`.
- Produces: one manual-compatible workflow with scheduled locate/extract steps.

- [x] **Step 1: Write failing workflow assertions**

Assert the cron, `PERIODIC_AUTO_ENABLED` guard, scheduled priority sample, locate limit 12,
extract limit 6, explicit `--confirm-llm`, shared `cninfo` lock, and manual `retry_failed`
input.

- [x] **Step 2: Run the workflow test and confirm RED**

Run: `.venv\Scripts\python.exe -m unittest tests.test_periodic.PeriodicValidationBatchTest.test_workflow_has_safe_scheduled_batches -v`

Expected: FAIL because there is no schedule.

- [x] **Step 3: Implement scheduled and manual branches**

Add the cron trigger; make manual step conditions explicit; add scheduled locate and extract
steps; pass `--retry-failed` only from the manual locate input; keep artifact upload on
`always()`.

- [x] **Step 4: Run workflow tests and confirm GREEN**

Run: `.venv\Scripts\python.exe -m unittest tests.test_periodic.PeriodicValidationBatchTest -v`

Expected: all workflow and sample tests pass.

### Task 3: Documentation, full verification and publication

**Files:**
- Modify: `docs/PROJECT.md`
- Create: `docs/worklogs/worklog_2026-07-29-2.md`
- Include: design and implementation plan files from this change.

**Interfaces:**
- Produces: operator instructions for automatic runs, pausing and failed-report recovery.

- [x] **Step 1: Update project state and worklog**

Document schedule, batch sizes, failure isolation, manual recovery and the fact that the next
cron starts automatically after publication.

- [x] **Step 2: Run full verification**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_periodic -v
.venv\Scripts\python.exe -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/periodic-poc.yml').read_text(encoding='utf-8')); print('yaml ok')"
.venv\Scripts\python.exe -m py_compile scripts/locate_periodic_pages.py scripts/extract_periodic_reports.py
```

Expected: zero failures, `yaml ok`, and exit code 0.

- [x] **Step 3: Review exact publication scope**

Confirm only workflow, two scripts, tests, project documentation, spec, plan and worklog are
included; verify `.env` is absent.

- [ ] **Step 4: Publish through GitHub connector**

Read remote `main`, stop if its baseline changed unexpectedly, create an atomic commit with
message `Automate periodic report batches`, and update `main` without force.

- [ ] **Step 5: Verify remote workflow**

Read the committed workflow and confirm the cron, limits, pause guard and failure-retry
semantics match the tested local files.
