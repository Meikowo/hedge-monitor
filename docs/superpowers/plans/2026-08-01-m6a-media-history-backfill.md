# M6a Historical Media Backfill Implementation Plan

**Goal:** Add a resumable, quota-bounded 2000—2025 Tavily backfill without promoting media leads to formal risk cases.

**Architecture:** A private Supabase window queue records deterministic annual and quarterly search windows. A Python worker processes one newest year per run, reuses the existing relevance and URL deduplication logic, and a daily GitHub Actions workflow advances the queue.

- [ ] Add failing tests for exact-date payloads, deterministic window generation, quarter splitting, retry/recovery selection, private schema and workflow budgets.
- [ ] Extend the Tavily boundary without changing current live-search behavior.
- [ ] Add the private window migration and resumable backfill worker.
- [ ] Add the daily backfill workflow and reduce live monitoring to once daily with a shared concurrency group.
- [ ] Run focused and full tests, apply and verify Supabase migration, perform a real no-write smoke test, publish atomically, and update project/worklog documentation.
