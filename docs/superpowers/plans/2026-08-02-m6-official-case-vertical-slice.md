# M6 Official Case Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce 1—3 real, quote-verified official derivatives-risk cases from discovery through official document storage, structured extraction and audit-ready evidence.

**Architecture:** Keep media leads as discovery aids only. Source adapters normalize official documents into the existing official four-table contract; deterministic relevance filtering precedes LLM extraction, and every displayed fact must pass exact official-quote verification. Begin with a narrow vertical slice, then use its measured precision to decide whether to expand toward the 50-document/10-case production gate.

**Tech Stack:** Python 3.12, PostgreSQL/Supabase, requests, PyYAML, MiniMax OpenAI-compatible API, GitHub Actions, unittest.

## Global Constraints

- Only derivatives, futures, options, forwards, swaps and hedging-related risk facts belong in scope.
- Media reports may locate official evidence but never fill an official-case field.
- Every non-null case fact must reference an official document and a quote that can be found in normalized source text.
- Missing official facts remain null/“未披露”; no arithmetic or model inference may manufacture a regulatory conclusion.
- Adapters are independent and idempotent; one source outage must not block the others.
- Production `web/` and navigation remain unchanged until 50 official candidates, at least 10 official cases, candidate precision of at least 90%, and complete quote verification are achieved.

---

### Task 1: Freeze the official document and evidence contracts

**Files:**
- Modify: `tests/test_derivative_risk.py`
- Modify: `docs/schema_snapshot.md`
- Modify only if the current contract is insufficient: `db/006_derivative_risk_cases.sql`

**Interfaces:**
- Consumes existing `derivative_risk_documents`, `derivative_risk_cases`, `derivative_risk_case_documents`, and `derivative_risk_evidence`.
- Produces a tested field map for source institution, document identity, company, event date, risk type, instruments, amounts, regulatory action/outcome and evidence location.

- [ ] **Step 1: Add failing contract tests** for one document supporting multiple facts, one case using multiple documents, unique source URL/hash behavior, nullable undisclosed fields and evidence quote/page anchors.
- [ ] **Step 2: Run** `python -m unittest tests.test_derivative_risk -v` **and confirm RED** only where the written contract is missing.
- [ ] **Step 3: Make the smallest schema/documentation change** needed for the slice; do not add media fields to official tables.
- [ ] **Step 4: Re-run the focused tests** and require GREEN before adapters begin.

### Task 2: Add independent SZSE, CSRC and CNINFO official adapters

**Files:**
- Create: `scripts/fetch_risk_szse.py`
- Create: `scripts/fetch_risk_csrc.py`
- Create: `scripts/fetch_risk_cninfo.py`
- Modify: `scripts/fetch_risk_sse.py`
- Create: `tests/test_risk_official_adapters.py`
- Modify: `config/risk_keywords.yml`

**Interfaces:**
- Each adapter produces the same normalized document dictionary: `source_type`, `source_org`, `external_id`, `title`, `published_at`, `url`, `code`, `company_name`, `raw_text`, `content_hash`.

- [ ] **Step 1: Write fixture-based failing tests** for pagination, date boundaries, URL normalization, company matching, hash stability and exclusion of non-derivative homonyms.
- [ ] **Step 2: Run** `python -m unittest tests.test_risk_official_adapters -v` **and confirm RED**.
- [ ] **Step 3: Implement one request/parser pair per source** with bounded retries, source-specific rate limits and no cross-adapter shared mutable state.
- [ ] **Step 4: Add media/known-event reverse lookup** that searches official sources by company, date window and derivative/risk terms without treating the media text as evidence.
- [ ] **Step 5: Re-run focused tests** and require GREEN for all four official adapters.

### Task 3: Persist official candidates idempotently

**Files:**
- Create: `scripts/store_risk_official_documents.py`
- Create: `tests/test_risk_official_persistence.py`
- Modify: `.github/workflows/risk-cases.yml`

**Interfaces:**
- Produces `prepare_document_row(document) -> dict` and `persist_documents(rows) -> PersistResult`.
- Upserts by stable official source identity/content hash without deleting prior versions needed for audit.

- [ ] **Step 1: Write failing persistence tests** for duplicate URL, changed content hash, partial adapter failure and replay after interruption.
- [ ] **Step 2: Run** `python -m unittest tests.test_risk_official_persistence -v` **and confirm RED**.
- [ ] **Step 3: Implement parent-first idempotent writes** and an artifact snapshot containing accepted/rejected documents and stable reasons.
- [ ] **Step 4: Guard the workflow** so push runs tests only; scheduled/manual write mode performs real source calls under the existing M6 concurrency group.
- [ ] **Step 5: Re-run persistence and workflow tests** and require GREEN.

### Task 4: Extract official cases and verify every quote

**Files:**
- Create: `scripts/extract_risk_official_cases.py`
- Create: `scripts/verify_risk_case_evidence.py`
- Create: `tests/test_risk_official_extraction.py`
- Create: `tests/fixtures/risk_official/expected_cases.json`

**Interfaces:**
- Extraction returns strict JSON for case facts plus evidence records.
- Verification normalizes whitespace only, then requires every evidence quote to occur in the stored official text and every fact to reference a verified evidence key.

- [ ] **Step 1: Add failing golden tests** covering loss, margin/liquidity, unauthorized/speculative activity, accounting/disclosure and a false-positive official document.
- [ ] **Step 2: Run** `python -m unittest tests.test_risk_official_extraction -v` **and confirm RED**.
- [ ] **Step 3: Implement deterministic relevance screening** before any MiniMax call and strict JSON/schema validation after it.
- [ ] **Step 4: Implement quote verification** that rejects unsupported values, preserves source units/currencies and leaves absent fields null.
- [ ] **Step 5: Run the golden tests** and require all facts and quotes to match expected fixtures.

### Task 5: Validate 1—3 real official cases end to end

**Files:**
- Update: `docs/worklogs/worklog_2026-08-02.md`
- Update: `docs/PROJECT.md`
- Add reviewed source fixtures under: `tests/fixtures/risk_official/`

**Interfaces:**
- Uses at least one known media event for reverse lookup and at least one direct official-source scan result.
- Produces exact counts for candidates, accepted cases, rejected reasons and verified evidence coverage.

- [ ] **Step 1: Run all adapters in dry-run mode** and save only official source metadata/text snapshots required for reproducible tests.
- [ ] **Step 2: Select 1—3 qualifying cases** using the written relevance contract, not subjective “most complete” criteria.
- [ ] **Step 3: Write candidates, extract cases and run quote verification**; any unsupported fact is cleared or the case remains unpublished.
- [ ] **Step 4: Have the user review only genuinely ambiguous business judgments**, with exact document URL, page/section, quote and proposed field value.
- [ ] **Step 5: Record measured candidate precision and evidence coverage** without extrapolating the small sample to production readiness.

### Task 6: Regression, release and expansion decision

**Files:**
- Modify: `docs/PROJECT.md`
- Modify: latest worklog

**Interfaces:**
- Publishes one atomic, non-force fast-forward commit through the GitHub connector after the remote `main` parent is rechecked.

- [ ] **Step 1: Run the complete Python and frontend regression suites** plus all new official-risk tests.
- [ ] **Step 2: Run Supabase policy/advisor checks** and anon/private access probes; official drafts must not be anonymously readable.
- [ ] **Step 3: Scan the exact release scope for secrets** and confirm no downloaded full document or media article is committed accidentally.
- [ ] **Step 4: Publish atomically through the GitHub connector** and verify push-triggered tests do not make real source or MiniMax calls.
- [ ] **Step 5: Decide expansion from measured evidence:** proceed toward 50 documents only if the slice is reproducible and quote-complete; otherwise revise adapters/extraction first.

---

## Plan Self-Review Result

- Coverage: discovery, official adapters, persistence, extraction, quote verification, real cases, user ambiguity review and release are assigned to separate testable tasks.
- Boundaries: media remains a discovery/source supplement; production navigation and bulk 50-document expansion are intentionally excluded from the first slice.
- Security: service-role writes and unpublished drafts stay private; no key, raw search metadata or unreviewed document dump enters the frontend.
- Placeholders: every task names exact files, interfaces, test commands and acceptance conditions; no implementation step is deferred without a gate.
