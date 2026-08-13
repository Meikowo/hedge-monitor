# M4 Periodic Throughput Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Split daily metadata discovery from the six-hour processing queue and raise each extraction batch from 18 to 36 reports.

**Architecture:** Keep one workflow and distinguish scheduled modes through cron identity. A once-daily metadata branch performs only discovery; four queue runs perform only locate and extract. Existing manual dispatch and the shared cninfo concurrency lock remain unchanged.

**Tech Stack:** GitHub Actions YAML, Python unittest, PyYAML.

## Global Constraints

- Queue schedule: Beijing 00:45、06:45、12:45、18:45.
- Metadata schedule: Beijing 05:20.
- Queue limits: locate 48, extract 36.
- Do not change database schema, extraction prompts, LLM concurrency, failure isolation, or manual inputs.

---

### Task 1: Workflow contract

**Files:**
- Modify: tests/test_periodic.py
- Modify: tests/test_periodic_formal.py
- Modify: .github/workflows/periodic-poc.yml

**Interfaces:**
- Consumes: GitHub schedule event github.event.schedule.
- Produces: separate metadata and queue step conditions.

- [ ] Add failing assertions for two cron groups, metadata-only discovery, queue-only locate/extract, locate 48 and extract 36.
- [ ] Run the targeted periodic tests and confirm failures reference the old single schedule and extract limit 18.
- [ ] Add the daily cron and condition each scheduled step by cron identity.
- [ ] Remove discovery from queue runs and set automatic extraction to 36.
- [ ] Run the targeted periodic tests and confirm they pass.

### Task 2: Documentation, verification and release

**Files:**
- Modify: docs/PROJECT.md
- Create: docs/worklogs/worklog_2026-08-13.md

**Interfaces:**
- Consumes: verified workflow contract and test outputs.
- Produces: auditable project checkpoint and GitHub release.

- [ ] Record the new schedule, throughput ceiling, unchanged safety rules and pre-change baseline.
- [ ] Run the complete Python and offline Node test suites.
- [ ] Scan the release files for secrets and exclude .env and output artifacts.
- [ ] Create one GitHub plugin commit from the current remote main and update main with force=false.
- [ ] Verify remote blob SHAs and inspect the first automatic runs without claiming future database throughput before evidence exists.

