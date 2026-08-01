import importlib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_collector():
    try:
        return importlib.import_module("scripts.fetch_risk_media_leads")
    except ModuleNotFoundError as exc:
        raise AssertionError("risk media collector is missing") from exc


class RiskMediaSchemaTest(unittest.TestCase):
    def test_media_leads_are_private_and_cannot_become_formal_cases(self):
        migration = ROOT / "db" / "006_risk_media_leads.sql"
        self.assertTrue(migration.exists(), "risk media migration is missing")
        sql = migration.read_text(encoding="utf-8")

        self.assertIn(
            "create table if not exists public.risk_media_leads",
            sql,
        )
        self.assertIn(
            "alter table public.risk_media_leads enable row level security",
            sql,
        )
        self.assertIn("official_corroborated boolean not null default false", sql)
        self.assertIn("need_review boolean not null default true", sql)
        self.assertIn("grant select, insert, update, delete", sql)
        self.assertIn("to service_role", sql)
        self.assertIn("create policy risk_media_leads_service_role_all", sql)
        self.assertNotRegex(sql, r"(?i)to\s+(anon|authenticated)")
        self.assertNotIn("references public.derivative_risk_cases", sql)


class TavilyMediaCollectorTest(unittest.TestCase):
    def test_search_payload_uses_basic_news_without_full_content(self):
        collector = load_collector()
        payload = collector.build_search_payload(
            "上市公司 套期保值 重大亏损",
            max_results=7,
            time_range="day",
        )
        self.assertEqual(
            payload,
            {
                "query": "上市公司 套期保值 重大亏损",
                "topic": "news",
                "search_depth": "basic",
                "max_results": 7,
                "time_range": "day",
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
                "include_usage": True,
            },
        )

    def test_limits_are_hard_capped_to_free_budget(self):
        collector = load_collector()
        self.assertEqual(collector.bounded_limits(99, 99), (12, 10))
        self.assertEqual(collector.bounded_limits(0, 0), (1, 1))

    def test_only_dual_term_results_become_leads_and_urls_are_stable(self):
        collector = load_collector()
        results = [
            {
                "title": "某上市公司商品期货套期保值发生重大亏损",
                "url": "https://news.example.com/a?id=7&utm_source=test#top",
                "content": "公司因保证金不足被强制平仓。",
                "published_date": "2026-08-01T01:02:03Z",
                "score": 0.91,
            },
            {
                "title": "某上市公司开展外汇套期保值",
                "url": "https://news.example.com/b",
                "content": "董事会审议通过日常业务方案。",
                "published_date": "2026-08-01T01:03:04Z",
                "score": 0.80,
            },
        ]
        leads = collector.prepare_leads(results, "loss")

        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead["url"], "https://news.example.com/a?id=7")
        self.assertTrue(lead["lead_key"].startswith("tavily:"))
        self.assertEqual(lead["query_keys"], ["loss"])
        self.assertIn("商品期货", lead["matched_derivative_terms"])
        self.assertIn("重大亏损", lead["matched_risk_terms"])
        self.assertFalse(lead["official_corroborated"])
        self.assertTrue(lead["need_review"])

    def test_duplicate_urls_merge_query_keys_and_keep_best_score(self):
        collector = load_collector()
        first = collector.prepare_leads(
            [{
                "title": "上市公司期货套期保值重大亏损",
                "url": "https://news.example.com/a?utm_medium=x&id=7",
                "content": "保证金不足",
                "score": 0.51,
            }],
            "loss",
        )
        second = collector.prepare_leads(
            [{
                "title": "上市公司期货套期保值亏损并被问询",
                "url": "https://news.example.com/a?id=7",
                "content": "监管问询涉及强制平仓",
                "score": 0.88,
            }],
            "inquiry",
        )
        merged = collector.merge_leads(first + second)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["query_keys"], ["loss", "inquiry"])
        self.assertEqual(merged[0]["provider_score"], 0.88)

    def test_hypothetical_risk_disclosure_is_not_an_actual_media_lead(self):
        collector = load_collector()
        results = [
            {
                "title": "某公司发行股票募集说明书",
                "url": "https://news.example.com/hypothetical",
                "content": (
                    "公司开展碳酸锂商品期货套期保值。"
                    "若保证金不足，将可能导致期货头寸被强制平仓，进而造成损失。"
                ),
                "score": 0.7,
            },
            {
                "title": "某上市公司商品期货套保发生重大亏损",
                "url": "https://news.example.com/actual",
                "content": "公司公告确认套期保值业务累计亏损2亿元，并收到监管问询函。",
                "score": 0.9,
            },
        ]

        leads = collector.prepare_leads(results, "major_hedge_loss")

        self.assertEqual([lead["url"] for lead in leads], ["https://news.example.com/actual"])
        self.assertIn("matched_contexts", leads[0]["raw_metadata"])

    def test_company_match_prefers_longest_exact_name(self):
        collector = load_collector()
        rows = [{
            "title": "上海测试股份有限公司期货套保发生亏损",
            "snippet": "公司收到监管问询函",
            "status": "new",
        }]
        companies = [
            {"code": "600002", "name": "测试股份"},
            {"code": "600001", "name": "上海测试股份有限公司"},
        ]
        matched = collector.match_companies(rows, companies)

        self.assertEqual(matched[0]["code"], "600001")
        self.assertEqual(matched[0]["company_name"], "上海测试股份有限公司")
        self.assertEqual(matched[0]["status"], "matched")

    def test_tavily_boundary_uses_bearer_key_and_rejects_missing_key(self):
        collector = load_collector()

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"results": [], "usage": {"credits": 1}}

        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return Response()

        session = Session()
        response = collector.search_tavily(
            "TEST_TAVILY_KEY",
            "上市公司 衍生品 处罚",
            max_results=3,
            time_range="day",
            session=session,
        )
        self.assertEqual(response["usage"]["credits"], 1)
        self.assertEqual(session.calls[0][0], "https://api.tavily.com/search")
        self.assertEqual(
            session.calls[0][1]["headers"]["Authorization"],
            "Bearer TEST_TAVILY_KEY",
        )
        self.assertEqual(session.calls[0][1]["timeout"], 45)

        with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY"):
            collector.search_tavily(
                "",
                "test",
                max_results=3,
                time_range="day",
                session=session,
            )


class RiskMediaWorkflowTest(unittest.TestCase):
    def test_workflow_has_one_capped_schedule_and_safe_manual_default(self):
        workflow = ROOT / ".github" / "workflows" / "risk-media.yml"
        self.assertTrue(workflow.exists(), "risk media workflow is missing")
        data = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

        triggers = data["on"]
        self.assertEqual(
            [item["cron"] for item in triggers["schedule"]],
            ["15 0 * * *"],
        )
        self.assertEqual(
            triggers["push"]["paths"],
            [
                ".github/workflows/risk-media.yml",
                "scripts/fetch_risk_media_leads.py",
                "config/risk_media_queries.yml",
            ],
        )
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["write"]["default"], "false")
        self.assertEqual(inputs["query_limit"]["default"], "1")
        self.assertEqual(inputs["max_results"]["default"], "3")

        env = data["jobs"]["collect"]["steps"][3]["env"]
        self.assertEqual(env["TAVILY_API_KEY"], "${{ secrets.TAVILY_API_KEY }}")
        self.assertTrue(env["QUERY_LIMIT"].endswith("|| '1' }}"))
        self.assertTrue(env["MAX_RESULTS"].endswith("|| '3' }}"))
        self.assertTrue(env["WRITE"].endswith("|| 'false' }}"))
        command = data["jobs"]["collect"]["steps"][3]["run"]
        self.assertIn("--query-limit \"$QUERY_LIMIT\"", command)
        self.assertIn("--max-results \"$MAX_RESULTS\"", command)
        self.assertNotIn("LLM_API_KEY", workflow.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
