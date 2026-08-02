import copy
import hashlib
import importlib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_publisher():
    try:
        return importlib.import_module("scripts.publish_risk_media_reports")
    except ModuleNotFoundError as exc:
        raise AssertionError("public media publisher is missing") from exc


class PublicMediaSchemaTest(unittest.TestCase):
    def test_public_projection_is_separate_from_private_leads(self):
        migration = ROOT / "db" / "008_risk_media_public.sql"
        self.assertTrue(migration.exists(), "public media migration is missing")
        sql = migration.read_text(encoding="utf-8")
        lowered = sql.lower()

        self.assertIn(
            "create table if not exists public.risk_media_reports",
            lowered,
        )
        self.assertIn(
            "create table if not exists public.risk_media_report_sources",
            lowered,
        )
        self.assertIn(
            "alter table public.risk_media_reports enable row level security",
            lowered,
        )
        self.assertIn(
            "alter table public.risk_media_report_sources enable row level security",
            lowered,
        )
        self.assertIn("to anon, authenticated", lowered)
        self.assertIn("publish_status in ('published','corroborated')", lowered)
        self.assertNotIn(
            "grant select on public.risk_media_leads to anon",
            lowered,
        )

    def test_public_projection_has_required_fields_and_constraints(self):
        sql = (ROOT / "db" / "008_risk_media_public.sql").read_text(
            encoding="utf-8"
        ).lower()

        required_report_fields = (
            "media_key text primary key",
            "code text",
            "company_name text",
            "event_date date",
            "risk_type text",
            "instruments text[]",
            "underlyings text[]",
            "summary text",
            "verification_status text",
            "official_case_key text",
            "publish_status text",
        )
        required_source_fields = (
            "source_key text primary key",
            "publisher_name text",
            "source_domain text",
            "title text",
            "published_at timestamptz",
            "url text",
            "short_excerpt text",
            "matched_derivative_terms text[]",
            "matched_risk_terms text[]",
            "unique (media_key, url)",
        )
        for field in required_report_fields + required_source_fields:
            self.assertIn(field, sql)

        self.assertIn(
            "verification_status in ('media_unverified','officially_corroborated')",
            sql,
        )
        self.assertIn(
            "publish_status in ('published','corroborated','dismissed','withdrawn')",
            sql,
        )
        self.assertIn("char_length(short_excerpt) <= 500", sql)
        self.assertIn("url ~ '^https://'", sql)
        self.assertIn("idx_risk_media_reports_official_case", sql)

    def test_reset_and_verification_keep_raw_tables_private(self):
        reset = (ROOT / "db" / "000_reset.sql").read_text(encoding="utf-8").lower()
        verify = (ROOT / "db" / "verify.sql").read_text(encoding="utf-8").lower()

        child_drop = reset.index("drop table if exists public.risk_media_report_sources")
        parent_drop = reset.index("drop table if exists public.risk_media_reports")
        raw_drop = reset.index("drop table if exists public.risk_media_leads")
        self.assertLess(child_drop, parent_drop)
        self.assertLess(parent_drop, raw_drop)

        self.assertIn("risk_media_reports", verify)
        self.assertIn("risk_media_report_sources", verify)
        self.assertIn("risk_media_leads", verify)
        self.assertIn("risk_media_backfill_windows", verify)
        self.assertNotIn("grant select on public.risk_media_leads", verify)


class PublicationGateTest(unittest.TestCase):
    def setUp(self):
        self.publisher = load_publisher()
        self.policy = self.publisher.load_publisher_policy(
            ROOT / "config" / "risk_media_publishers.yml"
        )
        self.accepted = {
            "lead_key": "tavily:accepted",
            "code": "002176",
            "company_name": "江西特种电机股份有限公司",
            "source_domain": "finance.sina.com.cn",
            "title": "江特电机商品期货套期保值发生亏损",
            "snippet": "据公司披露，碳酸锂期货套保累计亏损超过5000万元。",
            "published_at": "2025-12-28T00:00:00Z",
            "url": "https://finance.sina.com.cn/example.shtml",
            "status": "matched",
            "official_corroborated": False,
        }

    def rejection(self, **changes):
        lead = copy.deepcopy(self.accepted)
        lead.update(changes)
        return self.publisher.publication_rejection_reason(lead, self.policy)

    def test_named_financial_publisher_with_actual_local_context_is_accepted(self):
        self.assertEqual(
            self.publisher.publisher_for_domain("finance.sina.com.cn", self.policy),
            "新浪财经",
        )
        self.assertIsNone(
            self.publisher.publication_rejection_reason(self.accepted, self.policy)
        )

    def test_missing_company_date_or_https_url_is_rejected(self):
        self.assertEqual(self.rejection(code=None), "缺少上市公司代码或名称")
        self.assertEqual(self.rejection(published_at=None), "缺少媒体发布日期")
        self.assertEqual(
            self.rejection(url="http://finance.sina.com.cn/example.shtml"),
            "来源 URL 不是 HTTPS",
        )

    def test_blocked_unknown_and_official_sources_are_rejected(self):
        self.assertEqual(
            self.rejection(
                source_domain="guba.eastmoney.com",
                url="https://guba.eastmoney.com/news,example.html",
            ),
            "来源属于论坛、股吧或社交平台",
        )
        self.assertEqual(
            self.rejection(
                source_domain="finance.eastmoney.com",
                url="https://finance.eastmoney.com/caifuhao/123",
            ),
            "来源路径属于自媒体或社区内容",
        )
        self.assertEqual(
            self.rejection(
                source_domain="news.example.com",
                url="https://news.example.com/example",
            ),
            "来源不在具名媒体白名单",
        )
        self.assertEqual(
            self.rejection(
                source_domain="www.csrc.gov.cn",
                url="https://www.csrc.gov.cn/example.html",
            ),
            "来源属于官方证据渠道",
        )

    def test_hypothetical_risk_sentence_is_not_published(self):
        self.assertEqual(
            self.rejection(
                title="江特电机开展商品期货套期保值",
                snippet="若保证金不足可能造成损失。",
            ),
            "未找到同一语境内已发生的衍生品风险",
        )


class PublicationGroupingTest(unittest.TestCase):
    def setUp(self):
        self.publisher = load_publisher()
        self.policy = self.publisher.load_publisher_policy(
            ROOT / "config" / "risk_media_publishers.yml"
        )
        self.lead = {
            "lead_key": "tavily:first-accepted",
            "code": "002176",
            "company_name": "江西特种电机股份有限公司",
            "source_domain": "finance.sina.com.cn",
            "title": "江特电机商品期货套期保值发生亏损",
            "snippet": "据公司披露，碳酸锂期货套保累计亏损超过5000万元。",
            "published_at": "2025-12-28T00:00:00Z",
            "url": "https://finance.sina.com.cn/first.shtml",
            "matched_derivative_terms": ["商品期货", "期货", "套保"],
            "matched_risk_terms": ["亏损"],
            "provider_score": 0.91,
            "status": "matched",
            "need_review": True,
            "official_corroborated": False,
            "raw_metadata": {"matched_contexts": ["碳酸锂期货套保累计亏损超过5000万元"]},
        }

    def test_grouping_requires_company_window_risk_and_derivative_overlap(self):
        existing = {
            "media_key": "media:existing",
            "code": "002176",
            "event_date": "2025-12-20",
            "risk_type": "loss",
            "instruments": ["商品期货"],
        }
        self.assertEqual(
            self.publisher.find_matching_report(self.lead, [existing]),
            "media:existing",
        )

        variants = (
            {"code": "600000"},
            {"event_date": "2025-12-13"},
            {"risk_type": "regulatory"},
            {"instruments": ["外汇远期"]},
        )
        for changes in variants:
            report = {**existing, **changes}
            with self.subTest(changes=changes):
                self.assertIsNone(
                    self.publisher.find_matching_report(self.lead, [report])
                )

    def test_public_rows_are_attributed_capped_and_contain_no_private_fields(self):
        media_key = "media:example"
        report, source = self.publisher.prepare_public_rows(
            self.lead, "新浪财经", media_key
        )
        self.assertEqual(report["media_key"], media_key)
        self.assertEqual(report["risk_type"], "loss")
        self.assertEqual(report["verification_status"], "media_unverified")
        self.assertEqual(report["publish_status"], "published")
        self.assertLessEqual(len(report["summary"]), 300)
        self.assertTrue(source["short_excerpt"].startswith("据新浪财经报道："))
        self.assertLessEqual(len(source["short_excerpt"]), 500)
        self.assertEqual(
            source["source_key"],
            "source:"
            + hashlib.sha256(self.lead["url"].encode("utf-8")).hexdigest()[:32],
        )
        for row in (report, source):
            for private in ("provider_score", "raw_metadata", "need_review", "snippet"):
                self.assertNotIn(private, row)

    def test_candidates_group_conservatively_and_keep_first_key_stable(self):
        second = {
            **self.lead,
            "lead_key": "tavily:second-source",
            "published_at": "2026-01-05T00:00:00Z",
            "url": "https://finance.sina.com.cn/second.shtml",
        }
        batch = self.publisher.publish_candidates(
            [self.lead, second], [], self.policy
        )
        expected_key = "media:" + hashlib.sha256(
            self.lead["lead_key"].encode("utf-8")
        ).hexdigest()[:32]
        self.assertEqual([row["media_key"] for row in batch.reports], [expected_key])
        self.assertEqual(len(batch.sources), 2)
        self.assertTrue(
            all(source["media_key"] == expected_key for source in batch.sources)
        )
        self.assertEqual(len(batch.lead_updates), 2)

    def test_dismissed_or_corroborated_leads_do_not_create_media_rows(self):
        dismissed = {**self.lead, "status": "dismissed"}
        corroborated = {
            **self.lead,
            "lead_key": "tavily:corroborated",
            "status": "corroborated",
            "official_corroborated": True,
        }
        batch = self.publisher.publish_candidates(
            [dismissed, corroborated], [], self.policy
        )
        self.assertEqual(batch.reports, [])
        self.assertEqual(batch.sources, [])

    def test_persistence_writes_parents_before_sources_and_only_public_link_to_raw(self):
        batch = self.publisher.publish_candidates([self.lead], [], self.policy)
        calls = []

        def fake_upsert(table, rows, on_conflict):
            calls.append(("upsert", table, copy.deepcopy(rows), on_conflict))
            return len(rows)

        def fake_request(method, path, **kwargs):
            calls.append(("request", method, path, copy.deepcopy(kwargs)))
            return object()

        counts = self.publisher.persist_batch(batch, fake_upsert, fake_request)
        self.assertEqual(counts, (1, 1))
        self.assertEqual(calls[0][1], "risk_media_reports")
        self.assertEqual(calls[1][1], "risk_media_report_sources")
        self.assertEqual(calls[2][2], "risk_media_leads")
        patch = calls[2][3]["json_body"]
        self.assertEqual(set(patch), {"raw_metadata"})
        self.assertIn("public_media_key", patch["raw_metadata"])

    def test_parent_failure_prevents_source_and_private_writes(self):
        batch = self.publisher.publish_candidates([self.lead], [], self.policy)
        calls = []

        def failing_upsert(table, rows, on_conflict):
            calls.append(table)
            raise RuntimeError("parent write failed")

        with self.assertRaisesRegex(RuntimeError, "parent write failed"):
            self.publisher.persist_batch(batch, failing_upsert, lambda *a, **k: None)
        self.assertEqual(calls, ["risk_media_reports"])

    def test_runner_is_dry_by_default_and_writes_only_when_explicit(self):
        self.assertFalse(self.publisher.parse_args([]).write)
        self.assertTrue(self.publisher.parse_args(["--write"]).write)

        def fake_select(table, params, paginate=False):
            if table == "risk_media_leads":
                return [copy.deepcopy(self.lead)]
            if table == "risk_media_reports":
                return []
            raise AssertionError(f"unexpected table {table}")

        writes = []

        def fake_upsert(table, rows, on_conflict):
            writes.append((table, len(rows)))
            return len(rows)

        snapshots = []
        dry_batch = self.publisher.run_publication(
            write=False,
            policy=self.policy,
            sb_select=fake_select,
            sb_upsert=fake_upsert,
            sb_request=lambda *a, **k: writes.append(("request", 1)),
            snapshot_csv=lambda name, rows: snapshots.append((name, len(rows))),
            log=lambda message: None,
        )
        self.assertEqual(len(dry_batch.reports), 1)
        self.assertEqual(writes, [])
        self.assertTrue(any(name == "risk_media_public_preview" for name, _ in snapshots))

        self.publisher.run_publication(
            write=True,
            policy=self.policy,
            sb_select=fake_select,
            sb_upsert=fake_upsert,
            sb_request=lambda *a, **k: writes.append(("request", 1)),
            snapshot_csv=lambda name, rows: None,
            log=lambda message: None,
        )
        self.assertEqual(writes[:2], [
            ("risk_media_reports", 1),
            ("risk_media_report_sources", 1),
        ])


class PublicationWorkflowTest(unittest.TestCase):
    def _workflow(self, name):
        path = ROOT / ".github" / "workflows" / name
        return (
            yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader),
            path.read_text(encoding="utf-8"),
        )

    def test_live_and_backfill_publish_only_after_explicit_write_collection(self):
        for workflow_name, job_name in (
            ("risk-media.yml", "collect"),
            ("risk-media-backfill.yml", "backfill"),
        ):
            data, raw = self._workflow(workflow_name)
            steps = data["jobs"][job_name]["steps"]
            publisher_steps = [
                step for step in steps
                if step.get("name") == "Publish sanitized media reports"
            ]
            with self.subTest(workflow=workflow_name):
                self.assertEqual(data["concurrency"]["group"], "risk-media-tavily")
                self.assertEqual(len(publisher_steps), 1)
                publisher = publisher_steps[0]
                condition = publisher["if"]
                self.assertIn("github.event_name != 'push'", condition)
                self.assertIn("inputs.write == 'true'", condition)
                self.assertIn("github.event_name == 'schedule'", condition)
                self.assertEqual(
                    publisher["run"],
                    "python scripts/publish_risk_media_reports.py --write",
                )
                self.assertIn("SUPABASE_URL", publisher["env"])
                self.assertIn("SUPABASE_SERVICE_ROLE_KEY", publisher["env"])
                self.assertNotIn("LLM_API_KEY", raw)

    def test_push_runs_publication_tests_without_consuming_tavily(self):
        required_paths = {
            "scripts/publish_risk_media_reports.py",
            "config/risk_media_publishers.yml",
            "db/008_risk_media_public.sql",
            "tests/test_risk_media_public.py",
        }
        for workflow_name, job_name in (
            ("risk-media.yml", "collect"),
            ("risk-media-backfill.yml", "backfill"),
        ):
            data, _ = self._workflow(workflow_name)
            with self.subTest(workflow=workflow_name):
                self.assertTrue(
                    required_paths.issubset(set(data["on"]["push"]["paths"]))
                )
                validation = next(
                    step for step in data["jobs"][job_name]["steps"]
                    if step.get("if") == "github.event_name == 'push'"
                )
                self.assertIn("tests.test_risk_media_public", validation["run"])
                self.assertNotIn("TAVILY_API_KEY", validation.get("env", {}))


if __name__ == "__main__":
    unittest.main()
