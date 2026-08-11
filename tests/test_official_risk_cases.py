import unittest

from scripts.publish_official_risk_cases import (
    assess_official_candidate,
    build_official_bundle,
    extract_loss_amount,
    find_verified_quote,
    normalized_quote_in_text,
    persist_bundles,
    select_publishable,
)


def candidate_row(**overrides):
    row = {
        "ann_id": "1224896476",
        "code": "002176",
        "name": "江特电机",
        "title": "关于开展商品期货和衍生品业务的进展公告",
        "ann_date": "2025-12-25",
        "pdf_url": "https://static.cninfo.com.cn/finalpage/2025-12-25/1224896476.PDF",
        "ann_role": "进展",
        "is_hedge_related": True,
        "instruments": ["期货"],
        "underlyings": ["碳酸锂", "纯碱", "铜"],
        "summary": "因碳酸锂期货价格上涨致期货账户出现亏损",
        "confidence": 0.88,
        "evidence": [{
            "page": 1,
            "field": "progress_loss_threshold",
            "quote": "已确认损益及浮动亏损金额已达到公司最近一年经审计归母净利润的10%且绝对金额超过一千万元人民币",
        }],
    }
    row.update(overrides)
    return row


class OfficialRiskGateTest(unittest.TestCase):
    def test_accepts_actual_derivatives_loss(self):
        decision = assess_official_candidate(candidate_row())
        self.assertTrue(decision.accepted)
        self.assertIn("浮动亏损", decision.loss_quote)

    def test_rejects_management_policy_threshold(self):
        row = candidate_row(
            ann_role="管理制度",
            title="外汇套期保值业务管理制度",
            evidence=[{
                "page": 4,
                "field": "loss_disclosure_threshold",
                "quote": "亏损金额每达到净利润的10%且超过1000万元时应及时披露",
            }],
        )
        self.assertFalse(assess_official_candidate(row).accepted)

    def test_rejects_explicit_no_loss(self):
        row = candidate_row(evidence=[{
            "page": 19,
            "field": "progress",
            "quote": "本期套期保值业务未产生浮动亏损",
        }])
        self.assertFalse(assess_official_candidate(row).accepted)

    def test_rejects_ordinary_fx_loss_without_derivative_fact(self):
        row = candidate_row(
            title="季度报告",
            instruments=[],
            underlyings=[],
            summary="财务费用增加主要系汇兑损失增加",
            evidence=[{
                "page": 8,
                "field": "loss",
                "quote": "财务费用增加主要系汇兑损失增加所致",
            }],
        )
        self.assertFalse(assess_official_candidate(row).accepted)

    def test_normalized_quote_verification_ignores_pdf_spacing(self):
        quote = "累计亏损人民币1,268.39万元，占归母净利润14.43%"
        pdf_text = "累计亏损 人民币 1,268.39 万元，\n占归母净利润 14.43%。"
        self.assertTrue(normalized_quote_in_text(quote, pdf_text))

    def test_locates_actual_pdf_sentence_when_model_shortens_wording(self):
        model_quote = "已确认损益及浮动亏损金额已达到公司最近一年经审计归母净利润的10%且绝对金额超过一千万元人民币"
        pdf_text = (
            "近日，经公司初步测算，公司商品期货和衍生品交易已确认损益及浮动亏损\n"
            "金额已达到公司最近一年经审计的归属于上市公司股东净利润的10%且绝对金\n"
            "额超过一千万元人民币，具体以会计师事务所的审计结果为准。\n"
            "二、形成亏损的主要原因"
        )
        located = find_verified_quote(model_quote, pdf_text)
        self.assertIn("归属于上市公司股东净利润", located)
        self.assertNotIn("归母净利润", located)
        self.assertTrue(normalized_quote_in_text(located, pdf_text))

    def test_locates_actual_pdf_sentence_by_loss_phrase_and_amount(self):
        model_quote = "2024年1-2月累计浮动亏损约1,549.80万元"
        pdf_text = (
            "根据公司财务管理中心初步统计，截止2024年2月29日，公司2024年1-2月开展的"
            "外汇套期保值业务产生的投资收益与公允价值变动损益及汇兑收益累计浮动亏损约"
            "1,549.80万元，其中尚未完成交割业务公允价值变动亏损约276.03万元。"
        )
        located = find_verified_quote(model_quote, pdf_text)
        self.assertIn("1,549.80万元", located)
        self.assertIn("外汇套期保值业务", located)


class OfficialRiskMappingTest(unittest.TestCase):
    def test_extracts_exact_wan_amount_but_not_threshold(self):
        self.assertEqual(
            extract_loss_amount("累计亏损人民币1,268.39万元"),
            1268.39,
        )
        self.assertIsNone(
            extract_loss_amount("绝对金额超过一千万元人民币"),
        )

    def test_builds_four_table_bundle_with_verified_evidence(self):
        bundle = build_official_bundle(candidate_row(), verified_text="原文 已确认损益及浮动亏损金额已达到公司最近一年经审计归母净利润的10%且绝对金额超过一千万元人民币 完")
        self.assertEqual(bundle.source["source_doc_id"], "cninfo:1224896476")
        self.assertEqual(bundle.case["case_key"], "002176|2025-12-25|重大衍生品损失|official")
        self.assertEqual(bundle.relation["relation_type"], "supporting")
        self.assertTrue(bundle.evidence[0]["quote_verified"])
        self.assertTrue(bundle.evidence[0]["value_verified"])
        self.assertIsNone(bundle.case["amount"])

    def test_selects_latest_three_verified_candidates(self):
        rows = [
            candidate_row(ann_id="1", ann_date="2024-03-07", code="300702", name="天宇股份"),
            candidate_row(ann_id="2", ann_date="2025-10-31", code="688529", name="豪森智能"),
            candidate_row(ann_id="3", ann_date="2025-12-25"),
            candidate_row(ann_id="4", ann_date="2023-08-22", code="603055", name="台华新材"),
        ]
        selected = select_publishable(rows, limit=3)
        self.assertEqual([row["ann_id"] for row in selected], ["3", "2", "1"])

    def test_selects_unpublished_candidates_before_applying_limit(self):
        rows = [
            candidate_row(ann_id="1", ann_date="2024-03-07", code="300702"),
            candidate_row(ann_id="2", ann_date="2025-10-31", code="688529"),
            candidate_row(ann_id="3", ann_date="2025-12-25"),
            candidate_row(ann_id="4", ann_date="2023-08-22", code="603055"),
            candidate_row(ann_id="5", ann_date="2021-08-25", code="000612"),
        ]

        selected = select_publishable(
            rows,
            limit=2,
            existing_source_doc_ids={"cninfo:1", "cninfo:2", "cninfo:3"},
        )

        self.assertEqual([row["ann_id"] for row in selected], ["4", "5"])

    def test_empty_unpublished_batch_is_a_normal_noop(self):
        selected = select_publishable(
            [candidate_row(ann_id="3")],
            limit=3,
            existing_source_doc_ids={"cninfo:3"},
        )

        self.assertEqual(selected, [])


class OfficialRiskPersistenceTest(unittest.TestCase):
    def test_persistence_is_idempotent_and_links_matching_media(self):
        bundle = build_official_bundle(candidate_row(), verified_text="已确认损益及浮动亏损金额已达到公司最近一年经审计归母净利润的10%且绝对金额超过一千万元人民币")
        upserts = []
        inserts = []
        updates = []

        def fake_upsert(table, rows, on_conflict, **_kwargs):
            upserts.append((table, rows, on_conflict))
            return len(rows)

        def fake_insert(table, rows, **_kwargs):
            inserts.append((table, rows))
            return len(rows)

        def fake_update(table, filters, patch):
            updates.append((table, filters, patch))

        result = persist_bundles(
            [bundle],
            existing_evidence=[],
            media_reports=[{
                "media_key": "media:jiangte",
                "code": "002176",
                "event_date": "2025-12-28",
                "risk_type": "loss",
                "publish_status": "published",
            }],
            upsert_fn=fake_upsert,
            insert_fn=fake_insert,
            update_fn=fake_update,
        )
        self.assertEqual([item[0] for item in upserts], [
            "risk_source_documents", "derivative_risk_cases", "risk_case_documents",
        ])
        self.assertEqual(inserts[0][0], "risk_case_evidence")
        self.assertEqual(updates[0][2]["verification_status"], "officially_corroborated")
        self.assertEqual(updates[0][2]["publish_status"], "corroborated")
        self.assertEqual(result["evidence_inserted"], 1)


if __name__ == "__main__":
    unittest.main()
