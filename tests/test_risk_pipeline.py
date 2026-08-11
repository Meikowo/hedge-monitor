import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_risk_documents import (
    SOURCE_ITERATORS,
    collect_requested_sources,
    deduplicate_documents,
    persist_documents,
    prepare_document,
    resolve_sources,
    sanitize_company_codes,
)
from scripts.risk_relevance import assess_relevance
from scripts.risk_sources.sse import normalize_document, unwrap_jsonp
from scripts.risk_sources.sse import iter_documents
from scripts.risk_sources.szse import iter_documents as iter_szse_documents
from scripts.risk_sources.szse import parse_page as parse_szse_page
from scripts.risk_sources.szse import parse_payload as parse_szse_payload


ROOT = Path(__file__).resolve().parents[1]


class RiskSchemaContractTest(unittest.TestCase):
    def test_migration_defines_isolated_risk_tables_and_access_boundary(self):
        migration = ROOT / "db" / "005_derivative_risk_cases.sql"
        self.assertTrue(migration.exists(), "M6a risk migration is missing")
        sql = migration.read_text(encoding="utf-8")

        for table in (
            "risk_source_documents",
            "derivative_risk_cases",
            "risk_case_documents",
            "risk_case_evidence",
        ):
            self.assertRegex(
                sql,
                rf"create table if not exists public\.{table}\b",
            )
            self.assertRegex(
                sql,
                rf"alter table public\.{table} enable row level security",
            )

        for risk_type in (
            "超授权或未经授权开展",
            "偏离套保目的/投机化",
            "重大衍生品损失",
            "保证金与流动性风险",
            "审批或内控缺陷",
            "衍生品会计与信息披露违规",
            "品种/额度/期限/场所与授权不一致",
            "监管整改/处罚/追责",
        ):
            self.assertIn(f"'{risk_type}'", sql)

        self.assertRegex(
            sql,
            re.escape(
                "grant select on public.risk_source_documents, "
                "public.derivative_risk_cases,"
            ),
        )
        self.assertIn("to anon, authenticated", sql)
        self.assertIn("to service_role", sql)


class SseRiskSourceTest(unittest.TestCase):
    def test_unwrap_jsonp_and_normalize_official_document(self):
        payload = unwrap_jsonp(
            'jsonpCallback({"pageHelp":{"data":[{"docId":"SSE-1",'
            '"docTitle":"关于对某公司及有关责任人予以监管警示的决定",'
            '"docURL":"/disclosure/credibility/supervision/measures/abc.pdf",'
            '"createTime":"2026-07-01","extSECURITY_CODE":"600001",'
            '"extGSJC":"测试公司","extWTFL":"监管措施","channelId":"10007"}]}})'
        )
        row = payload["pageHelp"]["data"][0]
        doc = normalize_document(row, source_type="regulatory_measure")

        self.assertEqual(doc["source_doc_id"], "sse:SSE-1")
        self.assertEqual(doc["source_org"], "SSE")
        self.assertEqual(doc["source_type"], "regulatory_measure")
        self.assertEqual(doc["code"], "600001")
        self.assertEqual(doc["publish_date"], "2026-07-01")
        self.assertEqual(
            doc["document_url"],
            "https://www.sse.com.cn/disclosure/credibility/supervision/measures/abc.pdf",
        )
        self.assertEqual(doc["document_format"], "pdf")

    def test_unwrap_jsonp_rejects_invalid_wrapper(self):
        with self.assertRaises(ValueError):
            unwrap_jsonp("<html>not jsonp</html>")

    def test_normalize_host_without_scheme_to_https(self):
        doc = normalize_document(
            {
                "docId": "SSE-2",
                "docTitle": "问询函",
                "docURL": "www.sse.com.cn/disclosure/letter/test.htm",
            },
            source_type="inquiry",
        )
        self.assertEqual(
            doc["document_url"],
            "https://www.sse.com.cn/disclosure/letter/test.htm",
        )

    def test_normalize_rejects_document_without_official_url(self):
        with self.assertRaises(ValueError):
            normalize_document(
                {"docId": "SSE-3", "docTitle": "无原文链接记录"},
                source_type="regulatory_measure",
            )

    def test_iter_documents_paginates_top_level_result(self):
        class Response:
            def __init__(self, page):
                self.content = (
                    'jsonpCallback({"result":[{"docId":"SSE-%s",'
                    '"docTitle":"监管函","docURL":"/doc/%s.pdf"}],'
                    '"pageHelp":{"pageCount":2}})' % (page, page)
                ).encode()

            def raise_for_status(self):
                return None

        class Session:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, *_args, **_kwargs):
                self.calls += 1
                return Response(self.calls)

        session = Session()
        rows = list(
            iter_documents(
                source_type="inquiry",
                start_date="2026-01-01",
                end_date="2026-12-31",
                page_size=1,
                max_pages=2,
                pause_seconds=0,
                session=session,
            )
        )
        self.assertEqual([row["source_doc_id"] for row in rows], ["sse:SSE-1", "sse:SSE-2"])
        self.assertEqual(session.calls, 2)


class SzseRiskSourceTest(unittest.TestCase):
    def _page(self, rows, page_count=2):
        return (
            '<table class="table"><tbody>'
            + "".join(rows)
            + '</tbody></table><div>\u5f53\u524d\u7b2c 1 \u9875&nbsp;&nbsp; \u5171 '
            + str(page_count)
            + ' \u9875</div>'
        )

    def _row(self, code="001259", name="Example Co", date="2026-05-21",
             category="Annual report inquiry", doc_id="ABC123"):
        return (
            f'<tr><td>{code}</td><td>{name}</td><td>{date}</td>'
            f'<td>{category}</td><td><a href="javascript:void(0)" '
            f'encode-open="/UpFiles/zqjghj/sup_jghj_{doc_id}.pdf">details</a></td>'
            '<td>&nbsp;</td></tr>'
        )

    def test_parse_szse_inquiry_page(self):
        rows, page_count = parse_szse_page(
            self._page([self._row(doc_id="00019E952CF97E3FE2E01CA2FD75F43F")], 370),
            "inquiry",
        )

        self.assertEqual(page_count, 370)
        self.assertEqual(
            rows[0]["source_doc_id"],
            "szse:sup_jghj_00019E952CF97E3FE2E01CA2FD75F43F",
        )
        self.assertEqual(rows[0]["code"], "001259")
        self.assertEqual(rows[0]["publish_date"], "2026-05-21")
        self.assertEqual(rows[0]["source_type"], "inquiry")
        self.assertEqual(
            rows[0]["document_url"],
            "https://reportdocs.static.szse.cn/UpFiles/zqjghj/"
            "sup_jghj_00019E952CF97E3FE2E01CA2FD75F43F.pdf",
        )

    def test_parse_supports_measure_and_disciplinary_rows(self):
        for source_type in ("regulatory_measure", "disciplinary_action"):
            with self.subTest(source_type=source_type):
                rows, _ = parse_szse_page(
                    self._page([self._row(category="Official action", doc_id=source_type)]),
                    source_type,
                )
                self.assertEqual(rows[0]["source_type"], source_type)
                self.assertEqual(rows[0]["source_org"], "SZSE")

    def test_parse_skips_missing_links_invalid_rows_and_duplicate_ids(self):
        missing_link = (
            '<tr><td>000001</td><td>Missing</td><td>2026-05-20</td>'
            '<td>Inquiry</td><td>no document</td><td></td></tr>'
        )
        rows, _ = parse_szse_page(
            self._page([
                missing_link,
                self._row(doc_id="DUPLICATE"),
                self._row(code="000002", doc_id="DUPLICATE"),
                self._row(code="bad", doc_id="INVALID"),
            ]),
            "inquiry",
        )
        self.assertEqual([row["source_doc_id"] for row in rows], ["szse:sup_jghj_DUPLICATE"])

    def test_parse_empty_page_returns_no_documents(self):
        rows, page_count = parse_szse_page(self._page([], 1), "inquiry")
        self.assertEqual(rows, [])
        self.assertEqual(page_count, 1)

    def test_parse_official_api_payload_for_all_source_types(self):
        fixtures = {
            "inquiry": {
                "gsdm": "001259", "gsjc": "Example Inquiry", "fhrq": "2026-05-21",
                "hjlb": "Annual report inquiry",
                "ck": "<a encode-open='/UpFiles/zqjghj/sup_jghj_INQUIRY.pdf'>detail</a>",
            },
            "regulatory_measure": {
                "gkxx_gsdm": "000528", "gkxx_gsjc": "Example Measure",
                "gkxx_gdrq": "2026-08-07", "gkxx_jgcs": "Regulatory letter",
                "hjnr": "<a encode-open='/UpFiles/zqjghj/sup_jghj_MEASURE.pdf'>detail</a>",
                "gkxx_sjdx": "Listed company",
            },
            "disciplinary_action": {
                "xx_gsdm": "300716", "jc_gsjc": "Example Discipline",
                "xx_fwrq": "2026-08-09", "xx_cflb": "Public criticism",
                "xx_bt": "Disciplinary decision title",
                "ck": "<a encode-open='/UpFiles/zqjghj/sup_jghj_DISCIPLINE.pdf'>detail</a>",
            },
        }
        for source_type, data in fixtures.items():
            with self.subTest(source_type=source_type):
                rows, page_count = parse_szse_payload([{
                    "metadata": {"pagecount": 12},
                    "data": [data],
                }], source_type)
                self.assertEqual(page_count, 12)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["source_org"], "SZSE")
                self.assertEqual(rows[0]["source_type"], source_type)
                self.assertTrue(rows[0]["document_url"].startswith("https://reportdocs.static.szse.cn/"))

    def test_iter_documents_paginates_and_stops_after_older_page(self):
        class Response:
            def __init__(self, data):
                self.content = json.dumps(data).encode("utf-8")

            def raise_for_status(self):
                return None

        class Session:
            def __init__(self, pages):
                self.headers = {}
                self.pages = pages
                self.urls = []

            def get(self, url, **_kwargs):
                self.urls.append((url, _kwargs.get("params")))
                return Response(self.pages[len(self.urls) - 1])

        session = Session([
            [{"metadata": {"pagecount": 3}, "data": [{
                "gsdm": "001259", "gsjc": "New Co", "fhrq": "2026-08-01",
                "hjlb": "Inquiry", "ck": "<a encode-open='/UpFiles/zqjghj/sup_jghj_NEW.pdf'>detail</a>",
            }]}],
            [{"metadata": {"pagecount": 3}, "data": [{
                "gsdm": "001259", "gsjc": "Old Co", "fhrq": "2025-12-31",
                "hjlb": "Inquiry", "ck": "<a encode-open='/UpFiles/zqjghj/sup_jghj_OLD.pdf'>detail</a>",
            }]}],
        ])
        rows = list(iter_szse_documents(
            source_type="inquiry",
            start_date="2026-01-01",
            end_date="2026-08-11",
            max_pages=3,
            pause_seconds=0,
            session=session,
        ))

        self.assertEqual([row["source_doc_id"] for row in rows], ["szse:sup_jghj_NEW"])
        self.assertEqual(session.urls[0][1]["PAGENO"], 1)
        self.assertEqual(session.urls[1][1]["PAGENO"], 2)
        self.assertEqual(len(session.urls), 2)


class RiskRelevanceGateTest(unittest.TestCase):
    def test_direct_derivative_risk_cooccurrence_is_candidate(self):
        result = assess_relevance(
            "关于期货套期保值业务内控缺陷的监管工作函",
            "公司未经董事会授权扩大期货交易额度，并发生保证金风险。",
            "inquiry",
        )
        self.assertTrue(result.candidate)
        self.assertTrue(result.relevant)
        self.assertIn("期货", result.matched_derivative_terms)
        self.assertIn("未经授权", result.matched_risk_terms)

    def test_generic_accounting_policy_without_company_event_is_not_candidate(self):
        result = assess_relevance(
            "2025年年度报告",
            "公司根据企业会计准则披露衍生金融工具和套期会计的一般会计政策。",
            "company_announcement",
        )
        self.assertFalse(result.candidate)
        self.assertIn("仅通用政策", result.reason)

    def test_unrelated_inquiry_is_not_candidate(self):
        result = assess_relevance(
            "关于营业收入确认事项的问询函",
            "请说明应收账款坏账准备计提是否充分。",
            "inquiry",
        )
        self.assertFalse(result.candidate)

    def test_securities_futures_integrity_boilerplate_is_not_derivative_activity(self):
        result = assess_relevance(
            "关于对某公司予以纪律处分的决定",
            "相关违规事项记入证券期货市场诚信档案数据库，并要求完成整改。",
            "regulatory_measure",
        )
        self.assertFalse(result.candidate)
        self.assertNotIn("期货", result.matched_derivative_terms)

    def test_shipping_slot_swap_is_not_financial_derivative_swap(self):
        result = assess_relevance(
            "关于对航运公司予以监管警示的决定",
            "公司共同投船和舱位互换业务错用总额法确认收入，构成会计差错。",
            "regulatory_measure",
        )
        self.assertFalse(result.candidate)
        self.assertNotIn("互换", result.matched_derivative_terms)

    def test_non_derivative_uses_of_forward_and_option_terms_are_excluded(self):
        samples = (
            "采用应收款远期结算是否系行业惯例，请会计师发表意见。",
            "说明是否存在远期退换货安排及信息披露风险。",
            "公司股票期权激励计划可能带来流动性风险。",
            "相关标的过渡期权益安排导致亏损扩大。",
        )
        for text in samples:
            with self.subTest(text=text):
                result = assess_relevance("监管问询函", text, "inquiry")
                self.assertFalse(result.candidate)

    def test_far_apart_risk_signal_is_candidate_but_not_rule_confirmed(self):
        result = assess_relevance(
            "关于公司商品期货业务的问询函",
            "商品期货交易情况。" + ("普通经营说明。" * 80) + "公司另有信息披露违规。",
            "inquiry",
        )
        self.assertTrue(result.candidate)
        self.assertFalse(result.relevant)


class RiskDocumentIngestionTest(unittest.TestCase):
    def test_prepare_document_sets_candidate_terms_and_status(self):
        row = {
            "source_doc_id": "sse:abc",
            "source_org": "SSE",
            "source_type": "inquiry",
            "official_doc_id": "abc",
            "code": "600001",
            "company_name": "测试公司",
            "title": "关于公司期货业务的问询函",
            "publish_date": "2026-07-01",
            "document_url": "https://www.sse.com.cn/a.pdf",
            "document_format": "pdf",
            "raw_metadata": {},
        }
        prepared = prepare_document(
            row,
            "公司未经授权开展期货交易并出现保证金不足。",
            fetched=True,
        )
        self.assertEqual(prepared["status"], "candidate")
        self.assertIn("期货", prepared["matched_derivative_terms"])
        self.assertIn("未经授权", prepared["matched_risk_terms"])
        self.assertIn("fetched_at", prepared)
        self.assertIn("未经授权", prepared["raw_metadata"]["gate_excerpt"])
        self.assertTrue(prepared["raw_metadata"]["rule_relevant"])

    def test_fetch_failure_is_persisted_as_failed(self):
        document = {
            "source_doc_id": "szse:broken",
            "source_org": "SZSE",
            "source_type": "inquiry",
            "official_doc_id": "broken",
            "code": "000001",
            "company_name": "Example Co",
            "title": "Example inquiry",
            "publish_date": "2026-08-01",
            "document_url": "https://reportdocs.static.szse.cn/UpFiles/broken.pdf",
            "document_format": "pdf",
            "raw_metadata": {},
        }

        prepared = prepare_document(
            document,
            fetched=False,
            fetch_note="document fetch failed: Timeout",
        )

        self.assertEqual(prepared["status"], "failed")

    def test_source_registry_supports_sse_szse_and_all(self):
        self.assertEqual(resolve_sources("sse"), ["sse"])
        self.assertEqual(resolve_sources("szse"), ["szse"])
        self.assertEqual(resolve_sources("all"), ["sse", "szse"])

    def test_one_source_failure_keeps_other_source_results(self):
        def failing_iterator(**_kwargs):
            raise RuntimeError("SSE unavailable")

        def working_iterator(**_kwargs):
            yield {
                "source_doc_id": "szse:ok",
                "source_org": "SZSE",
                "source_type": "inquiry",
                "official_doc_id": "ok",
                "code": "000001",
                "company_name": "Example Co",
                "title": "Example inquiry",
                "publish_date": "2026-08-01",
                "document_url": "https://reportdocs.static.szse.cn/UpFiles/ok.pdf",
                "document_format": "pdf",
                "raw_metadata": {},
            }

        with patch.dict(
            SOURCE_ITERATORS,
            {"sse": failing_iterator, "szse": working_iterator},
            clear=True,
        ):
            results, errors = collect_requested_sources(
                sources=["sse", "szse"],
                requested_kind="inquiry",
                start_date="2026-07-01",
                end_date="2026-08-11",
                max_pages=1,
                limit=10,
                fetch_body=False,
            )

        self.assertEqual([row["source_doc_id"] for row in results["szse"]], ["szse:ok"])
        self.assertEqual(results["sse"], [])
        self.assertEqual(errors, [{"source": "sse", "error": "RuntimeError: SSE unavailable"}])

    def test_deduplicate_documents_keeps_one_row_per_source_id(self):
        rows = [
            {"source_doc_id": "sse:1", "title": "old"},
            {"source_doc_id": "sse:1", "title": "new"},
            {"source_doc_id": "sse:2", "title": "only"},
        ]
        deduped = deduplicate_documents(rows)
        self.assertEqual([row["source_doc_id"] for row in deduped], ["sse:1", "sse:2"])
        self.assertEqual(deduped[0]["title"], "new")

    def test_unknown_company_code_is_nulled_before_foreign_key_write(self):
        rows = [
            {"source_doc_id": "sse:1", "code": "600001"},
            {"source_doc_id": "sse:2", "code": "900999"},
        ]
        sanitized = sanitize_company_codes(rows, {"600001"})
        self.assertEqual(sanitized[0]["code"], "600001")
        self.assertIsNone(sanitized[1]["code"])

    def test_persistence_uses_idempotent_source_document_upsert(self):
        calls = []

        def fake_upsert(table, rows, *, on_conflict):
            calls.append((table, rows, on_conflict))
            return len(rows)

        count = persist_documents(
            [{"source_doc_id": "sse:1", "code": "900999"}],
            set(),
            fake_upsert,
        )
        self.assertEqual(count, 1)
        self.assertEqual(calls[0][0], "risk_source_documents")
        self.assertIsNone(calls[0][1][0]["code"])
        self.assertEqual(calls[0][2], "source_doc_id")


class RiskWorkflowContractTest(unittest.TestCase):
    def test_official_source_workflow_schedules_all_sources_and_guards_manual_write(self):
        workflow = ROOT / ".github" / "workflows" / "risk-poc.yml"
        self.assertTrue(workflow.exists(), "M6a risk POC workflow is missing")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("cron: '10 2 * * *'", text)
        self.assertIn("options:\n          - all\n          - sse\n          - szse", text)
        self.assertIn("default: 'false'", text)
        self.assertIn("confirm_write", text)
        self.assertIn("I_UNDERSTAND", text)
        self.assertIn("group: risk-sources", text)
        self.assertIn("python scripts/fetch_risk_documents.py", text)
        self.assertIn("default: ''", text)
        self.assertIn('--source "$SOURCE"', text)
        self.assertIn('SOURCE="all"', text)
        self.assertIn('WRITE="true"', text)
        self.assertIn('FETCH_BODY="true"', text)
        self.assertIn("d.timedelta(days=29)", text)
        self.assertIn("risk_documents_*.csv", text)

    def test_official_case_workflow_is_scheduled_and_write_guarded(self):
        workflow = ROOT / ".github" / "workflows" / "risk-official.yml"
        self.assertTrue(workflow.exists(), "official risk publisher workflow is missing")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertRegex(text, r"(?m)^\s*schedule:")
        self.assertIn("cron: '35 1 * * *'", text)
        self.assertIn("default: '3'", text)
        self.assertIn("default: 'false'", text)
        self.assertIn("confirm_write", text)
        self.assertIn("I_UNDERSTAND", text)
        self.assertIn("group: risk-sources", text)
        self.assertIn("SUPABASE_URL", text)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", text)
        self.assertIn("python scripts/publish_official_risk_cases.py", text)
        self.assertIn("official_risk_cases_*.json", text)


if __name__ == "__main__":
    unittest.main()
