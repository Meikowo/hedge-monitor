import datetime as dt
import importlib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_backfill():
    try:
        return importlib.import_module("scripts.backfill_risk_media_leads")
    except ModuleNotFoundError as exc:
        raise AssertionError("risk media history backfill worker is missing") from exc


class ExactDateSearchTest(unittest.TestCase):
    def test_exact_dates_replace_relative_time_range(self):
        collector = importlib.import_module("scripts.fetch_risk_media_leads")
        payload = collector.build_search_payload(
            "A股 上市公司 期货 重大亏损",
            max_results=10,
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        self.assertEqual(payload["start_date"], "2025-01-01")
        self.assertEqual(payload["end_date"], "2025-12-31")
        self.assertNotIn("time_range", payload)

    def test_relative_and_exact_dates_are_mutually_exclusive(self):
        collector = importlib.import_module("scripts.fetch_risk_media_leads")
        with self.assertRaises(ValueError):
            collector.build_search_payload(
                "test",
                max_results=3,
                time_range="day",
                start_date="2025-01-01",
                end_date="2025-12-31",
            )
        with self.assertRaises(ValueError):
            collector.build_search_payload(
                "test",
                max_results=3,
                start_date="2025-01-01",
            )

    def test_exact_dates_must_be_valid_and_ordered(self):
        collector = importlib.import_module("scripts.fetch_risk_media_leads")
        for start, end in (
            ("2025-02-30", "2025-12-31"),
            ("2025/01/01", "2025-12-31"),
            ("20250101", "2025-12-31"),
            ("2025-W01-1", "2025-12-31"),
            ("2025-12-31", "2025-01-01"),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                collector.build_search_payload(
                    "test",
                    max_results=3,
                    start_date=start,
                    end_date=end,
                )


class BackfillWindowTest(unittest.TestCase):
    def test_annual_seed_is_deterministic_and_covers_every_query_year(self):
        worker = load_backfill()
        queries = [
            {"key": "loss", "query": "期货 亏损"},
            {"key": "penalty", "query": "衍生品 处罚"},
        ]
        rows = worker.annual_windows(queries, 2024, 2025)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["calendar_year"] for row in rows], [2025, 2025, 2024, 2024])
        self.assertEqual(rows[0]["window_start"], "2025-01-01")
        self.assertEqual(rows[0]["window_end"], "2025-12-31")
        self.assertEqual(rows[0]["window_key"], "loss|2025-01-01|2025-12-31")
        self.assertEqual(rows, worker.annual_windows(queries, 2024, 2025))

    def test_quarter_split_has_exact_non_overlapping_dates_in_leap_year(self):
        worker = load_backfill()
        parent = worker.annual_windows(
            [{"key": "loss", "query": "期货 亏损"}], 2024, 2024
        )[0]
        rows = worker.quarter_windows(parent)
        self.assertEqual(
            [(row["window_start"], row["window_end"]) for row in rows],
            [
                ("2024-01-01", "2024-03-31"),
                ("2024-04-01", "2024-06-30"),
                ("2024-07-01", "2024-09-30"),
                ("2024-10-01", "2024-12-31"),
            ],
        )
        self.assertTrue(all(row["parent_window_key"] == parent["window_key"] for row in rows))

    def test_selection_uses_one_newest_year_and_recovers_only_stale_runs(self):
        worker = load_backfill()
        now = dt.datetime(2026, 8, 1, 12, tzinfo=dt.timezone.utc)
        rows = [
            {"window_key": "a", "calendar_year": 2025, "status": "pending", "attempts": 0},
            {"window_key": "b", "calendar_year": 2025, "status": "failed", "attempts": 2},
            {"window_key": "c", "calendar_year": 2025, "status": "failed", "attempts": 3},
            {"window_key": "d", "calendar_year": 2025, "status": "running", "attempts": 1,
             "started_at": "2026-08-01T07:00:00Z"},
            {"window_key": "e", "calendar_year": 2025, "status": "running", "attempts": 1,
             "started_at": "2026-08-01T11:00:00Z"},
            {"window_key": "f", "calendar_year": 2024, "status": "pending", "attempts": 0},
        ]
        selected = worker.select_windows(rows, now=now, limit=12)
        self.assertEqual([row["window_key"] for row in selected], ["a", "b", "d"])

    def test_backfill_limits_are_hard_capped(self):
        worker = load_backfill()
        self.assertEqual(worker.bounded_backfill_limits(99, 99), (12, 10))
        self.assertEqual(worker.bounded_backfill_limits(0, 0), (1, 1))

    def test_saturated_annual_splits_but_saturated_quarter_completes(self):
        worker = load_backfill()
        annual = {"granularity": "annual"}
        quarter = {"granularity": "quarter"}
        self.assertEqual(worker.window_outcome(annual, 10, 10), ("split", True))
        self.assertEqual(worker.window_outcome(quarter, 10, 10), ("completed", True))
        self.assertEqual(worker.window_outcome(annual, 9, 10), ("completed", False))


class BackfillSchemaTest(unittest.TestCase):
    def test_window_queue_is_private_and_indexed_for_pending_work(self):
        migration = ROOT / "db" / "007_risk_media_backfill.sql"
        self.assertTrue(migration.exists(), "risk media backfill migration is missing")
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.risk_media_backfill_windows", sql)
        self.assertIn("unique (query_key, window_start, window_end)", sql)
        self.assertIn("where status in ('pending','failed','running')", sql)
        self.assertIn("alter table public.risk_media_backfill_windows enable row level security", sql)
        self.assertIn("to service_role", sql)
        self.assertNotRegex(sql, r"(?i)to\s+(anon|authenticated)")
        self.assertNotIn("references public.derivative_risk_cases", sql)

    def test_database_rpcs_claim_atomically_and_preserve_review_state(self):
        sql = (ROOT / "db" / "007_risk_media_backfill.sql").read_text(encoding="utf-8")
        self.assertIn("create or replace function public.claim_risk_media_backfill_windows", sql)
        self.assertIn("for update skip locked", sql.lower())
        self.assertIn("create or replace function public.upsert_risk_media_leads", sql)
        self.assertIn("official_corroborated = risk_media_leads.official_corroborated", sql)
        self.assertIn("need_review = risk_media_leads.need_review", sql)
        self.assertIn("jsonb_array_elements", sql)
        self.assertIn("revoke all on function", sql.lower())

    def test_worker_uses_controlled_upsert_and_atomic_claim(self):
        source = (ROOT / "scripts" / "backfill_risk_media_leads.py").read_text(encoding="utf-8")
        collector = (ROOT / "scripts" / "fetch_risk_media_leads.py").read_text(encoding="utf-8")
        self.assertIn('"rpc/claim_risk_media_backfill_windows"', source)
        self.assertIn('"rpc/upsert_risk_media_leads"', collector)
        self.assertNotIn('sb_upsert("risk_media_leads"', source)
        reset = (ROOT / "db" / "000_reset.sql").read_text(encoding="utf-8")
        self.assertIn("drop function if exists public.claim_risk_media_backfill_windows", reset)
        self.assertIn("drop function if exists public.upsert_risk_media_leads", reset)

    def test_write_mode_requires_canonical_result_limit(self):
        worker = load_backfill()
        with self.assertRaises(ValueError):
            worker.validate_write_limits(True, 3)
        worker.validate_write_limits(True, 10)
        worker.validate_write_limits(False, 3)


class BackfillWorkflowTest(unittest.TestCase):
    def test_live_and_history_jobs_share_quota_lock_and_safe_schedules(self):
        live_path = ROOT / ".github" / "workflows" / "risk-media.yml"
        backfill_path = ROOT / ".github" / "workflows" / "risk-media-backfill.yml"
        self.assertTrue(backfill_path.exists(), "risk media backfill workflow is missing")
        live = yaml.load(live_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        backfill = yaml.load(backfill_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

        self.assertEqual([item["cron"] for item in live["on"]["schedule"]], ["15 0 * * *"])
        self.assertEqual(live["concurrency"]["group"], "risk-media-tavily")
        self.assertEqual(backfill["concurrency"]["group"], "risk-media-tavily")
        self.assertEqual(
            [item["cron"] for item in backfill["on"]["schedule"]],
            ["45 12 * * *"],
        )
        inputs = backfill["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["window_limit"]["default"], "1")
        self.assertEqual(inputs["max_results"]["default"], "3")
        self.assertEqual(inputs["write"]["default"], "false")
        command = backfill["jobs"]["backfill"]["steps"][3]["run"]
        self.assertIn('--window-limit "$WINDOW_LIMIT"', command)
        self.assertIn('--max-results "$MAX_RESULTS"', command)
        self.assertIn("--write", command)
        self.assertEqual(backfill["jobs"]["backfill"]["steps"][3]["if"], "github.event_name != 'push'")
        self.assertEqual(live["jobs"]["collect"]["steps"][3]["if"], "github.event_name != 'push'")


if __name__ == "__main__":
    unittest.main()
