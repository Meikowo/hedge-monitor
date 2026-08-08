import importlib
import unittest
from unittest.mock import patch
from pathlib import Path

import scripts.fetch_periodic_reports as periodic_fetch
import scripts.extract_periodic_reports as periodic_extract
import scripts.locate_periodic_pages as periodic_locator
import scripts.cninfo as cninfo
import yaml


def load_formal_module():
    try:
        return importlib.import_module("scripts.select_periodic_formal")
    except ModuleNotFoundError as exc:
        raise AssertionError("formal pool selector is not implemented") from exc


def load_progress_module():
    try:
        return importlib.import_module("scripts.periodic_progress")
    except ModuleNotFoundError as exc:
        raise AssertionError("periodic progress reporter is not implemented") from exc


class PeriodicFormalPoolTest(unittest.TestCase):
    def test_pool_keeps_every_2025_event_company_even_if_master_is_missing(self):
        formal = load_formal_module()
        events = [
            {
                "code": "000001", "name": "甲公司", "anchor_year": 2025,
                "scope": ["商品"], "instruments": ["期货"],
                "underlyings": ["铜"], "latest_ann_date": "2025-12-01",
                "ind_l1": "制造业", "ent_type": "民营企业",
            },
            {
                "code": "000001", "name": "甲公司", "anchor_year": 2025,
                "scope": ["外汇"], "instruments": ["远期"],
                "underlyings": ["美元"], "latest_ann_date": "2025-12-20",
                "ind_l1": "制造业", "ent_type": "民营企业",
            },
            {
                "code": "000002", "name": "跨年公司", "anchor_year": 2024,
                "scope": ["商品"], "instruments": ["期货"],
                "underlyings": ["铝"], "latest_ann_date": "2025-03-01",
                "ind_l1": "制造业", "ent_type": "其他",
            },
            {
                "code": "200001", "name": "B股公司", "anchor_year": 2025,
                "scope": ["外汇"], "instruments": ["远期"],
                "underlyings": ["美元"], "latest_ann_date": "2025-08-01",
                "ind_l1": "制造业", "ent_type": "其他",
            },
            {
                "code": "000003", "name": "主表缺失", "anchor_year": 2025,
                "scope": ["商品"], "instruments": ["期货"],
                "underlyings": ["钢材"], "latest_ann_date": "2025-07-01",
                "ind_l1": "制造业", "ent_type": "其他",
            },
        ]

        rows = formal.aggregate_formal(events, {"000001", "000002"}, 2025)

        self.assertEqual([row["code"] for row in rows], ["000001", "000003", "200001"])
        first = rows[0]
        self.assertEqual(first["event_count"], 2)
        self.assertEqual(first["latest_ann_date"], "2025-12-20")
        self.assertEqual(first["scope_group"], "商品+外汇")
        self.assertEqual(first["locator_terms"], ["期货", "美元", "远期", "铜"])

    def test_pool_output_is_unique_and_sorted_by_code(self):
        formal = load_formal_module()
        events = [
            {
                "code": code, "name": name, "anchor_year": 2025,
                "scope": ["外汇"], "instruments": ["远期"],
                "underlyings": [], "latest_ann_date": "2025-01-01",
                "ind_l1": "未分类", "ent_type": "其他",
            }
            for code, name in (("600002", "乙公司"), ("000001", "甲公司"), ("600002", "乙公司"))
        ]

        rows = formal.aggregate_formal(events, {"000001", "600002"}, 2025)

        self.assertEqual([row["code"] for row in rows], ["000001", "600002"])
        self.assertEqual([row["event_count"] for row in rows], [1, 2])

    def test_pool_rejects_empty_malformed_and_unsupported_codes(self):
        formal = load_formal_module()
        base = {
            "name": "测试公司", "anchor_year": 2025,
            "scope": ["商品"], "instruments": ["期货"],
            "underlyings": [], "latest_ann_date": "2025-01-01",
            "ind_l1": "制造业", "ent_type": "其他",
        }
        events = [
            {**base, "code": None},
            {**base, "code": "ABCDEF"},
            {**base, "code": "123456"},
            {**base, "code": "000001"},
        ]

        rows = formal.aggregate_formal(events, set(), 2025)

        self.assertEqual([row["code"] for row in rows], ["000001"])

    def test_missing_company_rows_are_built_from_formal_snapshot(self):
        sample = {
            "000001": {
                "code": "000001", "name": "已有公司", "industry": "银行",
                "ent_type": "其他",
            },
            "200001": {
                "code": "200001", "name": "缺失公司", "industry": "制造业",
                "ent_type": "外资",
            },
        }

        rows = periodic_fetch.build_missing_company_rows(sample, {"000001"})

        self.assertEqual(rows, [{
            "code": "200001",
            "name": "缺失公司",
            "ind_l1": "制造业",
            "ent_type": "外资",
            "source": "periodic_formal_pool",
        }])

    def test_full_market_discovery_uses_quarter_windows(self):
        visited = []

        def fake_iter_query(**kwargs):
            visited.append(kwargs["se_date"])
            return iter(())

        with patch.object(periodic_fetch.cninfo, "iter_query", side_effect=fake_iter_query):
            rows = list(periodic_fetch.iter_full_market_reports(
                "category_ndbg_szsh", "2026-01-01", "2026-12-31"
            ))

        self.assertEqual(rows, [])
        self.assertEqual(visited, [
            "2026-01-01~2026-03-31",
            "2026-04-01~2026-06-30",
            "2026-07-01~2026-09-30",
            "2026-10-01~2026-12-31",
        ])

    def test_cninfo_query_raises_instead_of_silently_truncating(self):
        response = {"announcements": [{"announcementId": "x"}], "hasMore": True}
        with (
            patch.object(cninfo, "MAX_PAGES", 2),
            patch.object(cninfo, "_request_json", return_value=response),
            patch.object(cninfo, "polite_sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "截断"):
                list(cninfo.iter_query(category="annual", se_date="2026-01-01~2026-03-31"))

    def test_over_cap_market_window_is_split_until_queries_complete(self):
        visited = []

        def fake_iter_query(**kwargs):
            window = kwargs["se_date"]
            visited.append(window)
            if window == "2026-01-01~2026-03-31":
                raise periodic_fetch.cninfo.QueryTruncatedError("too many pages")
            return iter([{"window": window}])

        with patch.object(periodic_fetch.cninfo, "iter_query", side_effect=fake_iter_query):
            rows = list(periodic_fetch.iter_bounded_market_window(
                "category_ndbg_szsh", "2026-01-01", "2026-03-31"
            ))

        self.assertEqual(visited, [
            "2026-01-01~2026-03-31",
            "2026-01-01~2026-02-14",
            "2026-02-15~2026-03-31",
        ])
        self.assertEqual([row["window"] for row in rows], visited[1:])

    def test_superseded_extracted_or_accepted_reports_are_preserved(self):
        superseded = [
            {"report_id": "old-extracted"},
            {"report_id": "old-accepted"},
            {"report_id": "old-discovered"},
        ]
        statuses = {
            "old-extracted": "extracted",
            "old-accepted": "located",
            "old-discovered": "discovered",
        }

        rows = periodic_fetch.select_superseded_to_skip(
            superseded, statuses, {"old-accepted"}
        )

        self.assertEqual([row["report_id"] for row in rows], ["old-discovered"])

    def test_report_id_filters_reject_comma_injection(self):
        with self.assertRaises(ValueError):
            periodic_extract.build_report_query(
                sample="config/annual_formal_2025.csv",
                limit=1,
                report_ids=["1225011770,1225011771"],
            )
        with self.assertRaises(ValueError):
            periodic_locator.build_report_query(
                terms={"600282": []},
                limit=1,
                report_ids=["1225011770,1225011771"],
            )


class PeriodicProgressTest(unittest.TestCase):
    def test_progress_counts_one_canonical_state_per_target_company(self):
        progress = load_progress_module()
        target_codes = {"000001", "000002", "000003", "000004", "000005", "000006", "000007"}
        reports = [
            {"report_id": "old-a", "code": "000001", "status": "skipped"},
            {"report_id": "new-a", "code": "000001", "status": "extracted"},
            {"report_id": "b", "code": "000002", "status": "located"},
            {"report_id": "c", "code": "000003", "status": "discovered"},
            {"report_id": "d", "code": "000004", "status": "failed"},
            {"report_id": "e", "code": "000005", "status": "needs_ocr"},
            {"report_id": "g", "code": "000007", "status": "skipped"},
            {"report_id": "outside", "code": "600999", "status": "extracted"},
        ]
        derivatives = [
            {"report_id": "old-a", "review_status": "accepted"},
            {"report_id": "new-a", "review_status": "accepted"},
            {"report_id": "outside", "review_status": "accepted"},
        ]

        result = progress.summarize_progress(target_codes, reports, derivatives)

        self.assertEqual(result, {
            "target": 7,
            "found": 6,
            "discovered": 1,
            "located": 1,
            "extracted": 1,
            "skipped": 1,
            "failed": 1,
            "needs_ocr": 1,
            "missing": 1,
            "accepted": 1,
            "verification_rate": 1.0,
        })

    def test_progress_deterministically_prefers_revised_extracted_report(self):
        progress = load_progress_module()
        reports = [
            {
                "report_id": "old", "code": "000001", "status": "extracted",
                "is_revised": False, "publish_date": "2026-04-01",
            },
            {
                "report_id": "new", "code": "000001", "status": "extracted",
                "is_revised": True, "publish_date": "2026-03-20",
            },
        ]
        derivatives = [{"report_id": "old", "review_status": "accepted"}]

        result = progress.summarize_progress({"000001"}, reports, derivatives)

        self.assertEqual(result["extracted"], 1)
        self.assertEqual(result["accepted"], 0)


def successful_report_run(report):
    return {
        "report": report,
        "extraction": {"disclosure_status": "有数值"},
        "metrics": [],
        "hedge_accounting_items": [],
        "raw": {},
    }


class PeriodicExtractionBatchTest(unittest.TestCase):
    def test_one_failed_report_does_not_stop_the_next_report(self):
        reports = [
            {"report_id": "r1", "name": "失败公司", "report_period": "2025FY"},
            {"report_id": "r2", "name": "成功公司", "report_period": "2025FY"},
        ]
        attempted = []

        def fake_extract(report, *_args):
            attempted.append(report["report_id"])
            if report["report_id"] == "r1":
                raise RuntimeError("bad json")
            return successful_report_run(report)

        with (
            patch.object(periodic_extract, "extract_one_report", side_effect=fake_extract),
            patch.object(periodic_extract, "claim_report"),
            patch.object(periodic_extract, "record_report_failure"),
        ):
            result = periodic_extract.run_extraction_batch(
                reports, {}, ["profile"], False, True, False, failure_limit=3
            )

        self.assertEqual(attempted, ["r1", "r2"])
        self.assertEqual([item["report"]["report_id"] for item in result["completed"]], ["r2"])
        self.assertEqual([item["report_id"] for item in result["failures"]], ["r1"])
        self.assertFalse(result["circuit_breaker"])

    def test_third_failure_trips_circuit_breaker_before_fourth_report(self):
        reports = [
            {"report_id": rid, "name": rid, "report_period": "2025FY"}
            for rid in ("r1", "r2", "r3", "r4")
        ]
        attempted = []

        def fake_extract(report, *_args):
            attempted.append(report["report_id"])
            if report["report_id"] != "r4":
                raise RuntimeError("model malformed")
            return successful_report_run(report)

        with (
            patch.object(periodic_extract, "extract_one_report", side_effect=fake_extract),
            patch.object(periodic_extract, "claim_report"),
            patch.object(periodic_extract, "record_report_failure"),
        ):
            result = periodic_extract.run_extraction_batch(
                reports, {}, ["profile"], False, True, False, failure_limit=3
            )

        self.assertEqual(attempted, ["r1", "r2", "r3"])
        self.assertEqual(len(result["failures"]), 3)
        self.assertEqual(result["remaining"], 1)
        self.assertTrue(result["circuit_breaker"])

    def test_circuit_breaker_snapshot_is_written_before_nonzero_exit(self):
        batch = {
            "completed": [],
            "failures": [{"report_id": "r1"}, {"report_id": "r2"}, {"report_id": "r3"}],
            "circuit_breaker": True,
        }
        with patch.object(periodic_extract, "snapshot_json") as snapshot:
            with self.assertRaises(SystemExit):
                periodic_extract.finalize_extraction_batch(batch)

        snapshot.assert_called_once_with("periodic_extract_run", batch)


class PeriodicFormalWorkflowTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_schedule_runs_full_formal_funnel_with_safe_limits(self):
        workflow = yaml.safe_load(
            (self.ROOT / ".github" / "workflows" / "periodic-poc.yml")
            .read_text(encoding="utf-8")
        )
        triggers = workflow.get("on") or workflow.get(True)
        dispatch = triggers["workflow_dispatch"]
        job = workflow["jobs"]["periodic-poc"]
        steps = {step.get("name"): step for step in job["steps"] if step.get("name")}

        self.assertEqual(triggers["schedule"], [{"cron": "45 22,4,10,16 * * *"}])
        self.assertEqual(job["timeout-minutes"], 330)
        self.assertIn("formal1812", dispatch["inputs"]["sample_set"]["options"])
        self.assertIn("report_id", dispatch["inputs"])
        self.assertIn("config/annual_formal_2025.csv", job["env"]["SAMPLE_FILE"])
        self.assertIn("--strategy full", steps["Auto-discover formal reports (no LLM)"]["run"])
        self.assertIn("--limit 48 --write", steps["Auto-locate formal reports (no LLM)"]["run"])
        self.assertIn("--limit 18 --confirm-llm", steps["Auto-extract formal reports (LLM)"]["run"])
        self.assertNotIn("--retry-failed", steps["Auto-locate formal reports (no LLM)"]["run"])
        self.assertIn("periodic_progress.py", steps["Report formal progress before batch"]["run"])
        self.assertIn("periodic_progress.py", steps["Report formal progress after batch"]["run"])

    def test_manual_report_id_is_forwarded_only_by_explicit_dispatch(self):
        workflow = yaml.safe_load(
            (self.ROOT / ".github" / "workflows" / "periodic-poc.yml")
            .read_text(encoding="utf-8")
        )
        job = workflow["jobs"]["periodic-poc"]
        steps = {step.get("name"): step for step in job["steps"] if step.get("name")}
        commands = "\n".join(
            step.get("run", "") for step in job["steps"] if isinstance(step, dict)
        )

        self.assertEqual(
            steps["Locate candidate pages manually (no LLM)"]["env"]["REPORT_ID"],
            "${{ inputs.report_id }}",
        )
        self.assertEqual(
            steps["Extract annual reports manually (LLM)"]["env"]["REPORT_ID"],
            "${{ inputs.report_id }}",
        )
        self.assertIn('EXTRA_ARGS+=(--report-id "$REPORT_ID")', commands)


if __name__ == "__main__":
    unittest.main()
