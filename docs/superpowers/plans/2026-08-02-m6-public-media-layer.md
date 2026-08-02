# M6 Public Unverified Media Layer Implementation Plan

> **Execution mode for this workspace:** Use `superpowers:executing-plans` inline. The local snapshot is not a Git checkout, and the database, workflows, Demo and connector-first atomic release share one tightly coupled validation path; subagents are intentionally not used for this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish automatically screened derivatives-risk media reports as a clearly labelled public research layer without exposing raw Tavily leads or weakening the official-case evidence contract.

**Architecture:** Keep `risk_media_leads` and backfill windows private. A new deterministic publisher reads private leads with service-role access, applies a domain and relevance policy, groups conservative same-company/same-risk reports, and writes sanitized records to two public RLS tables. The Demo consumes official and media-shaped fixtures through one normalized UI contract; the production navigation remains hidden until the existing official-case release gate is met.

**Tech Stack:** Python 3.12, PostgreSQL/Supabase RLS and PostgREST, PyYAML, GitHub Actions, vanilla JavaScript, Node.js test runner.

## Global Constraints

- Public evidence levels are exactly `官方文件／已核实` and `媒体报道／未核实`.
- Raw `risk_media_leads` and `risk_media_backfill_windows` remain service-role-only and are never queried by the browser.
- A media row requires a matched listed-company code/name, local-context derivative and actual-risk terms, a named publisher, a publication date, and an HTTPS source URL.
- Forums, stock bars, social media, anonymous self-media, hypothetical risk warnings, and unidentified publishers are not published.
- A single qualifying media source may be published but never counted as an official case.
- Finding official evidence upgrades the record to the official-case path; the media report becomes a supplementary source and must not remain a duplicate main row.
- Public summaries use short source-attributed wording and do not copy full articles or invent regulatory conclusions.
- No MiniMax call is added to the media publication path.
- Existing announcement, annual-report, official-risk, and production frontend behavior remains unchanged.
- The local directory is not a Git checkout. Preserve the established connector-first release flow: verify a scoped set of files, create an atomic GitHub commit from the observed remote parent, and update `main` with `force=false` only if the remote baseline is unchanged.

---

### Task 1: Public projection schema and access contract

**Files:**
- Create: `db/008_risk_media_public.sql`
- Modify: `db/000_reset.sql`
- Modify: `db/verify.sql`
- Create: `tests/test_risk_media_public.py`

**Interfaces:**
- Consumes: private `risk_media_leads`, `companies`, and optional `derivative_risk_cases.case_key`.
- Produces: public tables `risk_media_reports` and `risk_media_report_sources`; service-role CRUD and anon/authenticated filtered SELECT.

- [ ] **Step 1: Write the failing schema contract test**

```python
class PublicMediaSchemaTest(unittest.TestCase):
    def test_public_projection_is_separate_from_private_leads(self):
        sql = (ROOT / "db" / "008_risk_media_public.sql").read_text("utf-8")
        self.assertIn("create table if not exists public.risk_media_reports", sql)
        self.assertIn("create table if not exists public.risk_media_report_sources", sql)
        self.assertIn("alter table public.risk_media_reports enable row level security", sql)
        self.assertIn("alter table public.risk_media_report_sources enable row level security", sql)
        self.assertIn("to anon, authenticated", sql)
        self.assertIn("publish_status in ('published','corroborated')", sql)
        self.assertNotIn("grant select on public.risk_media_leads to anon", sql.lower())
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_risk_media_public.PublicMediaSchemaTest -v`

Expected: FAIL because `db/008_risk_media_public.sql` does not exist.

- [ ] **Step 3: Implement the two-table projection**

Create `risk_media_reports` with these exact fields: `media_key` primary key, `code`/`company_name`, `event_date`, nullable `risk_type`, `instruments[]`, `underlyings[]`, source-attributed `summary`, `verification_status` constrained to `media_unverified|officially_corroborated`, nullable `official_case_key`, `publish_status` constrained to `published|corroborated|dismissed|withdrawn`, and timestamps.

Create `risk_media_report_sources` with: `source_key` primary key, `media_key` foreign key, `publisher_name`, `source_domain`, `title`, `published_at`, HTTPS `url`, `short_excerpt` limited to 500 characters, matched derivative/risk term arrays, and timestamps. Add `unique(media_key,url)`.

Enable RLS on both tables. Grant service-role CRUD. Grant anon/authenticated SELECT only where the parent report has `publish_status in ('published','corroborated')`. Use `TO` clauses and both `USING`/`WITH CHECK` for service-role policies; do not use `auth.role()` or `security definer`.

- [ ] **Step 4: Add reset and verification coverage**

Add child-before-parent drops to `db/000_reset.sql`. Add `pg_tables`, policy, privilege, public row-count and private-table denial checks to `db/verify.sql` without granting any new permission on `risk_media_leads`.

- [ ] **Step 5: Run the schema test and complete GREEN**

Run: `python -m unittest tests.test_risk_media_public.PublicMediaSchemaTest -v`

Expected: PASS.

- [ ] **Step 6: Checkpoint the task**

Verify only the four scoped files are included in the Task 1 connector commit. Suggested message: `Add public media risk projection schema`.

---

### Task 2: Publisher policy and deterministic release gate

**Files:**
- Create: `config/risk_media_publishers.yml`
- Create: `scripts/publish_risk_media_reports.py`
- Modify: `tests/test_risk_media_public.py`

**Interfaces:**
- Produces `load_publisher_policy(path) -> PublisherPolicy`.
- Produces `publication_rejection_reason(lead, policy) -> str | None`.
- Produces `publisher_for_domain(domain, policy) -> str | None`.
- Reuses `relevant_contexts(title, snippet)` from `scripts/fetch_risk_media_leads.py`.

- [ ] **Step 1: Write failing behavioral tests**

Use literal fixtures proving that:

```python
accepted = {
    "lead_key": "tavily:accepted",
    "code": "002176",
    "company_name": "江西特种电机股份有限公司",
    "source_domain": "finance.sina.com.cn",
    "title": "江特电机商品期货套保发生亏损",
    "snippet": "据公司披露，碳酸锂期货套保累计亏损超过1000万元。",
    "published_at": "2025-12-28T00:00:00Z",
    "url": "https://finance.sina.com.cn/example.shtml",
}
self.assertIsNone(publication_rejection_reason(accepted, policy))
```

Separate tests must reject: missing code, missing date, HTTP URL, `guba.eastmoney.com`, `/caifuhao/`, an unknown domain, a CSRC official domain that belongs in the official adapter, and a hypothetical sentence containing `若保证金不足可能造成损失`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_risk_media_public.PublicationGateTest -v`

Expected: FAIL because the publisher module and policy file do not exist.

- [ ] **Step 3: Add explicit publisher policy**

Create YAML sections `publishers`, `blocked_hosts`, `blocked_path_terms`, and `official_hosts`. Start with named financial-news domains already encountered by the project; map `finance.sina.com.cn` to `新浪财经`. Block stock-bar/forum/social paths explicitly. Route `csrc.gov.cn`, `sse.com.cn`, `szse.cn` and `cninfo.com.cn` to the official pipeline rather than publishing them as media.

- [ ] **Step 4: Implement the minimal deterministic gate**

Normalize domains to lowercase, support exact host and parent-domain policy matches, require company/date/HTTPS/source identity, rerun `relevant_contexts`, and return one stable Chinese rejection reason per failed condition. Never fetch the media page in this task; operate on the private stored lead and Tavily-matched context only.

- [ ] **Step 5: Verify GREEN**

Run: `python -m unittest tests.test_risk_media_public.PublicationGateTest -v`

Expected: PASS with accepted and rejected fixtures following the written policy.

- [ ] **Step 6: Checkpoint the task**

Suggested connector commit: `Add deterministic public media gate`.

---

### Task 3: Conservative grouping, sanitized rows, and idempotent persistence

**Files:**
- Modify: `scripts/publish_risk_media_reports.py`
- Modify: `tests/test_risk_media_public.py`

**Interfaces:**
- Produces `risk_family(terms) -> str` and `derivative_families(terms) -> tuple[str, ...]`.
- Produces `find_matching_report(lead, existing_reports) -> str | None`.
- Produces `prepare_public_rows(lead, publisher_name, media_key) -> tuple[dict, dict]`.
- Produces `publish_candidates(leads, existing_reports, policy) -> PublicationBatch`.
- Produces `persist_batch(batch, sb_upsert, sb_request) -> tuple[int, int]`.

- [ ] **Step 1: Write failing grouping and sanitization tests**

Test the following independent behaviors with hand-derived values:

- same company, dates within 14 days, same risk family, and overlapping derivative family attach to one media report;
- different companies, dates over 14 days, or disjoint risk families remain separate;
- `media_key` is stable from the first accepted `lead_key` and does not change when a later source joins;
- `short_excerpt` starts with `据新浪财经报道：` and is at most 500 characters;
- private fields `provider_score`, `raw_metadata`, `need_review`, and full `snippet` never appear in public rows;
- a corroborated/dismissed raw lead is not republished as a new main media row.

- [ ] **Step 2: Run the grouping tests and verify RED**

Run: `python -m unittest tests.test_risk_media_public.PublicationGroupingTest -v`

Expected: FAIL because grouping and row preparation functions are missing.

- [ ] **Step 3: Implement conservative event grouping**

Map risk terms into deterministic families: loss, margin/liquidity, unauthorized, speculation, regulatory, internal-control, disclosure, or other. Map derivative terms into commodity/futures, FX, option, swap, or generic derivatives. Match an existing report only when code is identical, event dates differ by no more than 14 days, risk family is identical, and derivative families overlap. Otherwise create `media:<sha256(lead_key)[:32]>`.

- [ ] **Step 4: Implement sanitized public rows**

Create report summaries only from the accepted matched context, prefix them with the named publisher, cap to 300 characters, set `verification_status=media_unverified` and `publish_status=published`, and leave unsupported regulatory action/outcome fields absent. Create one source row per URL with `source:<sha256(normalized_url)[:32]>`.

- [ ] **Step 5: Implement idempotent persistence and private audit linkage**

Upsert parent reports by `media_key`, sources by `source_key`, then update each private lead `raw_metadata.public_media_key` without changing `need_review`, `status`, or `official_corroborated`. If any parent write fails, do not write its sources. Return actual affected counts for logs.

- [ ] **Step 6: Verify GREEN and mutation boundaries**

Run: `python -m unittest tests.test_risk_media_public -v`

Expected: all public-media tests PASS. Mentally verify that changing the 14-day window, allowing unknown publishers, or copying `provider_score` would fail at least one test.

- [ ] **Step 7: Checkpoint the task**

Suggested connector commit: `Publish sanitized media risk reports`.

---

### Task 4: Automatic incremental and historical publication

**Files:**
- Modify: `.github/workflows/risk-media.yml`
- Modify: `.github/workflows/risk-media-backfill.yml`
- Modify: `tests/test_risk_media_public.py`
- Modify: `tests/test_risk_media.py`
- Modify: `tests/test_risk_media_backfill.py`

**Interfaces:**
- Runs `python scripts/publish_risk_media_reports.py --write` only after a successful write-mode Tavily collection.
- Reuses the existing `risk-media-tavily` concurrency group and repository Supabase secrets.

- [ ] **Step 1: Write failing workflow behavior tests**

Parse both YAML files and assert that scheduled/write-mode runs execute the publisher after collection, push runs execute tests only, manual `write=false` never publishes, both jobs retain the shared concurrency lock, and neither workflow adds `LLM_API_KEY`.

- [ ] **Step 2: Run focused workflow tests and verify RED**

Run: `python -m unittest tests.test_risk_media_public.PublicationWorkflowTest -v`

Expected: FAIL because neither workflow runs the publisher.

- [ ] **Step 3: Add guarded publisher steps**

In both workflows, add `config/risk_media_publishers.yml`, `scripts/publish_risk_media_reports.py`, `db/008_risk_media_public.sql`, and the new test to push path filters. On non-push runs, execute publication only when the workflow's resolved `WRITE` value is `true`. Use existing `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; do not expose them to artifacts.

- [ ] **Step 4: Verify workflow GREEN**

Run: `python -m unittest tests.test_risk_media tests.test_risk_media_backfill tests.test_risk_media_public -v`

Expected: all media collector, backfill and publication tests PASS.

- [ ] **Step 5: Checkpoint the task**

Suggested connector commit: `Automate public media projection`.

---

### Task 5: Update the local risk-monitoring Demo for both evidence levels

**Files:**
- Modify: `web-demo/risk-cases/index.html`
- Modify: `web-demo/risk-cases/data.js`
- Modify: `web-demo/risk-cases/app.js`
- Modify: `web-demo/risk-cases/styles.css`
- Modify: `tests/test_risk_demo_structure.mjs`
- Modify: `tests/test_risk_demo_logic.mjs`

**Interfaces:**
- Adds normalized field `evidenceLevel` with values `official_verified|media_unverified`.
- Adds filters `all|official_verified|media_unverified` and media-specific detail rendering.
- CSV adds evidence level, verification status, publisher, source date and source URL.

- [ ] **Step 1: Write failing Demo tests**

Add one synthetic `media_unverified` fixture with a named publisher and `example.invalid` URL. Assert separate official/media metric counts, evidence-level filter intersection, visible `媒体报道／未核实` label, media detail without a fabricated official document chain, and CSV columns `证据级别,核实状态,来源名称,来源日期,来源URL`.

- [ ] **Step 2: Run Node tests and verify RED**

Run: `node tests/test_risk_demo_structure.mjs` and `node tests/test_risk_demo_logic.mjs`.

Expected: FAIL because evidence-level controls and media detail branches are absent.

- [ ] **Step 3: Implement the minimal unified UI contract**

Add an evidence-level select to the existing filter bar. Keep the high-density table and drawer layout unchanged; replace the current evidence column with the explicit badge. For media fixtures show publisher/date/domain/short excerpt/source link and `尚未找到官方依据`. Preserve official document-chain and quote rendering for official fixtures.

- [ ] **Step 4: Update metrics and export**

Count official cases and media leads separately. Keep “involved companies” deduplicated across both layers. Export the full current filtered result with UTF-8 BOM and the five new provenance fields; never export private Tavily metadata.

- [ ] **Step 5: Verify GREEN and syntax**

Run:

```powershell
node tests/test_risk_demo_structure.mjs
node tests/test_risk_demo_logic.mjs
node --check web-demo/risk-cases/app.js
node --check web-demo/risk-cases/data.js
```

Expected: all commands exit 0.

- [ ] **Step 6: Checkpoint the task**

Suggested connector commit: `Show official and media risk layers in demo`.

---

### Task 6: Apply Supabase schema and validate real publication safely

**Files:**
- No new production files beyond Tasks 1–4.
- Update after verification: `docs/worklogs/worklog_2026-08-02.md`

**Interfaces:**
- Uses Supabase MCP against project `uwxzftnpsrqlvetwjjjj`.
- Uses the existing private lead set as real input; expected first publishable lead is determined by policy, not hard-coded.

- [ ] **Step 1: Verify current Supabase guidance before DDL**

Read the current Supabase changelog and official RLS/Data API guidance. Confirm there is no relevant breaking change to RLS policies, grants, or PostgREST table exposure.

- [ ] **Step 2: Apply the final SQL through Supabase MCP**

Execute the reviewed `db/008_risk_media_public.sql` once. Do not change or grant access to `risk_media_leads` or `risk_media_backfill_windows`.

- [ ] **Step 3: Verify database access and security**

Run SQL checks for tables, columns, constraints, policies and grants. Use anon REST requests to prove the two projection tables are readable and the two raw media tables remain unreadable. Run Supabase security and performance advisors; fix any new finding before continuing.

- [ ] **Step 4: Run a dry publication against real private leads**

Execute the publisher without `--write`; inspect the generated snapshot and rejection reasons. Confirm no official-domain or blocked-source row appears in the public batch and no raw score/metadata is present.

- [ ] **Step 5: Enable the first idempotent write**

Run the publisher with `--write` once, then rerun it and verify counts do not grow from duplicates. Query public rows and compare each to its private source for code, date, URL and short attributed excerpt.

- [ ] **Step 6: Record evidence in the worklog**

Record exact row counts, publisher distribution, rejected reasons, advisor results, anon/private access checks, and whether the current Jiangte Motor lead passed. Do not call the result an official case.

---

### Task 7: Full regression, atomic release and next-slice handoff

**Files:**
- Modify: `docs/PROJECT.md`
- Modify: `docs/worklogs/worklog_2026-08-02.md`
- Create after this plan is complete: `docs/superpowers/plans/2026-08-02-m6-official-case-vertical-slice.md`

**Interfaces:**
- Publishes the scoped media-layer implementation to `main` with a non-force fast-forward.
- Leaves production `web/` and navigation untouched.

- [ ] **Step 1: Run complete regression verification**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
node tests/test_risk_demo_structure.mjs
node tests/test_risk_demo_logic.mjs
node tests/test_periodic_demo_structure.mjs
node tests/test_periodic_demo_logic.mjs
node tests/test_periodic_production_logic.mjs
node tests/test_web_structure.mjs
node tests/test_web_bootstrap.mjs
```

Expected: zero failures. If a real public API bootstrap count has legitimately changed, update only the expectation that represents the current contract, not a hard-coded historical count.

- [ ] **Step 2: Review release scope and secrets**

List every changed file. Scan for `TAVILY_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, JWT-like strings and `.env` content. Confirm `web/` is unchanged and raw media tables still have no anon grant.

- [ ] **Step 3: Update project status**

Document the public media projection, actual first-run counts, access model, Demo status, rollback baseline and remaining official-case work. Preserve the independent 50-official-document/10-official-case/90%-precision gate.

- [ ] **Step 4: Publish atomically through the GitHub connector**

Read the current remote `main` SHA and tree. Upload only reviewed files, create a commit whose parent is that exact SHA, re-read `main`, and update `main` with `force=false` only if unchanged. Suggested release message: `Add public unverified media risk layer`.

- [ ] **Step 5: Verify the remote release**

Fetch the created commit, confirm its file list, and inspect any push-triggered tests. The public projection release must not trigger real Tavily consumption on push.

- [ ] **Step 6: Write the next independent implementation plan**

Create the official-case vertical-slice plan covering media/known-event reverse lookup, SZSE/CSRC/CNINFO official adapters, official document persistence, structured extraction, quote verification and 1–3 real official cases. Do not mix that work into the media projection release.

---

## Plan Self-Review Result

- Spec coverage: public/private separation, automated publisher gate, source attribution, dual-layer Demo, CSV provenance, upgrade deduplication, RLS, workflow automation and release rollback are each assigned to a task.
- Scope boundary: this plan deliberately stops before production navigation and official-case extraction; those are independent deliverables and receive the next plan.
- Type consistency: `media_key`, `source_key`, `official_case_key`, `evidenceLevel`, `verification_status` and `publish_status` use the same names throughout schema, publisher, Demo and tests.
- Security boundary: browser access is limited to sanitized projection tables; raw Tavily tables and service-role credentials remain private.
