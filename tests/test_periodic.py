import csv
import unittest
from pathlib import Path

import yaml

from scripts.extract_periodic_reports import (
    extract_explicit_pnl_metrics,
    merge_verified_note_metrics,
    merge_table_metrics,
    merge_pass_results,
    normalize,
    normalize_accounting_items,
    promote_verified_accounting_evidence,
    should_replace_metric_family,
    should_purge_legacy_metrics,
    verify_raw_value,
)
from scripts.extract_announcements import thinking_extra_body
from scripts.prompt_periodic import (
    METRIC_FAMILIES,
    build_metric_messages,
    build_profile_messages,
)
from scripts.periodic_verification import classify
from scripts.periodic_pdf import (
    MAX_MARKED_CHARS,
    build_marked_text,
    find_parent_company_note_start,
    parse_derivative_investment_table,
    parse_derivative_note_table,
    select_candidate_pages,
    unit_before_table,
)


class PeriodicNormalizationTest(unittest.TestCase):
    def test_thinking_off_is_sent_as_explicitly_disabled(self):
        self.assertEqual(
            thinking_extra_body("off"),
            {"thinking": {"type": "disabled"}},
        )
        self.assertEqual(
            thinking_extra_body("on"),
            {"thinking": {"type": "adaptive"}},
        )

    def test_raw_value_requires_literal_number(self):
        self.assertTrue(verify_raw_value(1234.56, "本期金额为1,234.56万元"))
        self.assertFalse(verify_raw_value(1234.56, "本期金额约一千万元"))

    def test_raw_value_understands_loss_words_and_accounting_parentheses(self):
        self.assertTrue(verify_raw_value(-11897, "公允价值变动损失为11,897千元"))
        self.assertTrue(verify_raw_value(-14838, "套期会计的影响 (14,838)"))

    def test_dash_is_not_normalized_to_zero(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "derivative_disposal_investment_income",
                "fact_level": "report",
                "value": 0,
                "unit": "千元",
                "time_basis": "period",
                "raw": "处置衍生金融资产产生的投资损失 —",
                "page": 10,
            }],
        }, "【P10】处置衍生金融资产产生的投资损失 —")

        self.assertEqual(metrics, [])

    def test_percentage_zero_cannot_verify_a_monetary_zero(self):
        body = "【P48】货币互换合约 - 940,900 5,045 - - - - 0.00%"
        _, monetary = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "ending_balance",
                "fact_level": "underlying",
                "scope": "外汇",
                "underlying": "货币互换合约",
                "value": 0,
                "unit": "千元",
                "time_basis": "period_end",
                "raw": "货币互换合约 - 940,900 5,045 - - - - 0.00%",
                "page": 48,
            }],
        }, body)
        _, ratio = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "net_asset_ratio",
                "fact_level": "underlying",
                "scope": "外汇",
                "underlying": "货币互换合约",
                "value": 0,
                "unit": "%",
                "time_basis": "period_end",
                "raw": "货币互换合约 - 940,900 5,045 - - - - 0.00%",
                "page": 48,
            }],
        }, body)

        self.assertEqual(monetary, [])
        self.assertEqual(len(ratio), 1)

    def test_estimates_cannot_enter_metrics(self):
        top, metrics = normalize({
            "disclosure_status": "有数值", "scopes": ["商品"],
            "metrics": [{"metric_type": "estimated_spot_pnl", "value": 10,
                         "unit": "万元", "time_basis": "period",
                         "raw": "估算现货损益10万元", "page": 2}],
        }, "【P2】估算现货损益10万元")
        self.assertEqual(top["disclosure_status"], "有数值")
        self.assertEqual(metrics, [])

    def test_metric_keeps_original_unit_and_evidence(self):
        _, metrics = normalize({
            "disclosure_status": "有数值", "scopes": ["外汇"],
            "metrics": [{"metric_type": "period_pnl", "value": 321.5,
                         "currency": "CNY", "unit": "万元", "time_basis": "period",
                         "raw": "套期保值业务本期损益为321.5万元", "page": 88}],
        }, "【P88】套期保值业务本期损益为321.5万元")
        self.assertEqual(metrics[0]["unit"], "万元")
        self.assertTrue(metrics[0]["value_verified"])
        self.assertTrue(metrics[0]["quote_verified"])

    def test_metric_with_unlocatable_quote_is_not_persisted(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "margin_end_cash",
                "value": 100,
                "unit": "万元",
                "time_basis": "period_end",
                "raw": "期货保证金100万元",
                "page": 88,
            }],
        }, "【P88】其他应收款明细表")

        self.assertEqual(metrics, [])

    def test_verified_metric_marks_unmentioned_profile_for_review(self):
        top, metrics = normalize({
            "disclosure_status": "未提及",
            "metrics": [{
                "metric_type": "derivative_asset_fv",
                "fact_level": "report",
                "value": 12.5,
                "unit": "万元",
                "time_basis": "period_end",
                "raw": "衍生金融资产期末余额为12.5万元",
                "page": 88,
            }],
        }, "【P88】衍生金融资产期末余额为12.5万元")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(top["disclosure_status"], "需复核")

    def test_verified_business_table_resolves_profile_status_to_has_values(self):
        top, metrics = normalize({
            "disclosure_status": "未提及",
            "metrics": [{
                "metric_type": "ending_balance",
                "fact_level": "scope",
                "scope": "商品",
                "value": 8371222.5,
                "unit": "元",
                "time_basis": "period_end",
                "source_section": "衍生品投资情况",
                "raw": "金属期货 期末账面价值 8,371,222.50",
                "page": 28,
                "table_cell_verified": True,
            }],
        }, "【P28】金属期货 期末账面价值 8,371,222.50")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(top["disclosure_status"], "有数值")

    def test_verified_explicit_derivative_note_resolves_status_to_has_values(self):
        top, metrics = normalize({
            "disclosure_status": "未提及",
            "metrics": [{
                "metric_type": "derivative_fv_change_pnl",
                "fact_level": "report",
                "value": 498580.86,
                "unit": "元",
                "time_basis": "period",
                "source_section": "公允价值变动收益",
                "raw": "其中：衍生金融工具产生的公允价值变动收益 本期发生额 498,580.86",
                "page": 226,
                "table_cell_verified": True,
            }],
        }, "【P226】其中：衍生金融工具产生的公允价值变动收益 本期发生额 498,580.86")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(top["disclosure_status"], "有数值")

    def test_same_page_semantic_metric_is_deduplicated(self):
        metric = {
            "metric_type": "derivative_fv_change_pnl",
            "fact_level": "scope",
            "scope": "商品",
            "value": -7676900,
            "unit": "元",
            "time_basis": "period",
            "account_name": "本期公允价值变动损益",
            "raw": "本期公允价值变动损益-7,676,900.00元",
            "page": 29,
        }
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [
                {**metric, "source_section": "报告期实际损益情况的说明"},
                {**metric, "source_section": "市场价格或公允价值变动情况"},
            ],
        }, "【P29】本期公允价值变动损益-7,676,900.00元")

        self.assertEqual(len(metrics), 1)

    def test_comprehensive_pnl_infers_single_business_scope_from_quote(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "reported_derivative_comprehensive_pnl",
                "fact_level": "report",
                "value": -9875.41,
                "unit": "万元",
                "time_basis": "period",
                "raw": "外汇衍生品交易产生的投资收益与公允价值变动损益合计为-9,875.41万元",
                "page": 44,
            }],
        }, "【P44】外汇衍生品交易产生的投资收益与公允价值变动损益合计为-9,875.41万元")

        self.assertEqual(metrics[0]["fact_level"], "scope")
        self.assertEqual(metrics[0]["scope"], "外汇")

    def test_metric_restores_original_scaled_rmb_unit(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "notional_peak_reported",
                "fact_level": "report",
                "value": 3270000000,
                "currency": "CNY",
                "unit": "元",
                "time_basis": "period_peak",
                "raw": "任一交易日持有的最高合约价值不超过人民币32.70亿元",
                "page": 31,
            }],
        }, "【P31】任一交易日持有的最高合约价值不超过人民币32.70亿元")

        self.assertEqual(metrics[0]["value"], 32.70)
        self.assertEqual(metrics[0]["unit"], "亿元")
        self.assertTrue(metrics[0]["value_verified"])

    def test_metric_restores_original_scaled_foreign_currency_unit(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "notional_peak_reported",
                "fact_level": "scope",
                "scope": "外汇",
                "value": 170000000,
                "currency": "USD",
                "unit": "美元",
                "time_basis": "period_peak",
                "raw": "外汇衍生品业务任一交易日持有的最高合约价值不超过1.7亿美元",
                "page": 31,
            }],
        }, "【P31】外汇衍生品业务任一交易日持有的最高合约价值不超过1.7亿美元")

        self.assertEqual(metrics[0]["value"], 1.7)
        self.assertEqual(metrics[0]["unit"], "亿美元")
        self.assertTrue(metrics[0]["value_verified"])

    def test_peak_margin_is_not_misclassified_as_notional(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "notional_peak_reported",
                "fact_level": "scope",
                "scope": "商品",
                "value": 5450000000,
                "currency": "CNY",
                "unit": "元",
                "time_basis": "period_peak",
                "raw": "商品期货套期保值业务任意时点保证金最高占用额不超过人民币5.45亿元",
                "page": 31,
            }],
        }, "【P31】商品期货套期保值业务任意时点保证金最高占用额不超过人民币5.45亿元")

        self.assertEqual(metrics[0]["metric_type"], "margin_peak_reported")
        self.assertEqual(metrics[0]["value"], 5.45)
        self.assertEqual(metrics[0]["unit"], "亿元")
        self.assertTrue(metrics[0]["value_verified"])

    def test_empty_selective_pass_preserves_existing_family(self):
        self.assertFalse(should_replace_metric_family(False, "operations", []))
        self.assertTrue(should_replace_metric_family(True, "operations", []))
        self.assertTrue(should_replace_metric_family(
            False,
            "operations",
            [{"metric_type": "period_purchase_amount"}],
        ))
        self.assertTrue(should_purge_legacy_metrics(True))
        self.assertFalse(should_purge_legacy_metrics(False))

    def test_pnl_prompt_covers_explicit_actual_pnl_narrative(self):
        messages = build_metric_messages(
            "pnl",
            "2025年年度报告",
            "株洲冶炼集团股份有限公司",
            "600961",
            "2025-12-31",
            "【P30】报告期实际损益情况的说明",
        )
        prompt = "\n".join(message["content"] for message in messages)
        self.assertIn("报告期实际损益情况", prompt)
        self.assertIn("平仓与持仓损益合计", prompt)

    def test_explicit_actual_pnl_has_deterministic_fallback(self):
        body = """【P30】
报告期实际损益情况的说明
计入报告期内的商品衍生品平仓与持仓损益合计为-366,065,852.86 元。
套期保值效果的说明
"""
        metrics = extract_explicit_pnl_metrics(body)

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["metric_type"], "reported_derivative_comprehensive_pnl")
        self.assertEqual(metrics[0]["fact_level"], "scope")
        self.assertEqual(metrics[0]["scope"], "商品")
        self.assertEqual(metrics[0]["value"], -366065852.86)
        self.assertEqual(metrics[0]["unit"], "元")
        self.assertEqual(metrics[0]["page"], 30)

    def test_actual_pnl_fallback_handles_multiple_business_rows(self):
        body = """【P35】
报告期实际损益情况的说明
期货套保合约报告期内实际损益为19,495.74 万元，远期金融合约报告期内实际损益为-3,703.30 万元。
"""
        metrics = extract_explicit_pnl_metrics(body)

        self.assertEqual([
            (item["scope"], item["value"], item["unit"])
            for item in metrics
        ], [
            ("商品", 19495.74, "万元"),
            ("外汇", -3703.30, "万元"),
        ])

    def test_actual_pnl_fallback_handles_unscoped_amount_below_section_heading(self):
        body = """【P35】
报告期实际损益情况的说明
实际损益金额为15,009.45 万元
套期保值效果的说明
"""
        metrics = extract_explicit_pnl_metrics(body)

        self.assertEqual([
            (item["fact_level"], item["scope"], item["value"], item["unit"])
            for item in metrics
        ], [
            ("report", None, 15009.45, "万元"),
        ])

    def test_unverified_model_scaled_value_is_not_persisted(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "reported_derivative_comprehensive_pnl",
                "fact_level": "scope",
                "scope": "商品",
                "value": 194957400,
                "currency": "CNY",
                "unit": "万元",
                "time_basis": "period",
                "raw": "期货套保合约报告期内实际损益为19,495.74万元",
                "page": 35,
            }],
        }, "【P35】期货套保合约报告期内实际损益为19,495.74万元")

        self.assertEqual(metrics, [])

    def test_explicit_no_derivative_business_is_mention_without_value(self):
        top, metrics = normalize({
            "disclosure_status": "未提及",
            "summary": "公司报告期不存在衍生品投资。",
            "metrics": [],
        }, "【P32】公司报告期不存在衍生品投资。")

        self.assertEqual(metrics, [])
        self.assertEqual(top["disclosure_status"], "提及无数值")

    def test_accounting_policy_is_not_evidence_of_actual_application(self):
        messages = build_profile_messages(
            "2025年年度报告",
            "格力电器",
            "000651",
            "2025FY",
            "【P125】本公司的套期包括公允价值套期、现金流量套期以及境外经营净投资套期。",
        )
        prompt = "\n".join(message["content"] for message in messages)

        self.assertIn("会计政策", prompt)
        self.assertIn("不能证明报告期实际应用", prompt)

    def test_group_policy_wording_is_not_actual_application(self):
        top, _ = normalize({
            "disclosure_status": "有数值",
            "hedge_accounting_status": "已应用",
            "hedge_accounting_types": ["现金流量套期"],
            "hedge_accounting_evidence": {
                "page": 185,
                "quote": "本集团的套期主要包括现金流量套期。",
            },
        }, "【P185】本集团的套期主要包括现金流量套期。")

        self.assertEqual(top["hedge_accounting_status"], "未明确披露")
        self.assertEqual(top["hedge_accounting_types"], [])
        self.assertIsNone(top["hedge_accounting_page"])

    def test_policy_only_types_are_replaced_by_actual_cash_flow_hedge_evidence(self):
        top, _ = normalize({
            "disclosure_status": "有数值",
            "hedge_accounting": ["公允价值套期", "现金流量套期", "境外经营净投资套期"],
            "hedge_accounting_status": "混合应用",
            "hedge_accounting_types": ["公允价值套期", "现金流量套期", "境外经营净投资套期"],
            "hedge_accounting_evidence": {
                "page": 125,
                "quote": "本公司的套期包括公允价值套期、现金流量套期以及对境外经营净投资的套期。",
            },
        }, (
            "【P125】本公司的套期包括公允价值套期、现金流量套期以及对境外经营净投资的套期。\n"
            "【P171】现金流量套期储备 291,500.00"
        ))

        self.assertEqual(top["hedge_accounting_status"], "已应用")
        self.assertEqual(top["hedge_accounting_types"], ["现金流量套期"])
        self.assertEqual(top["hedge_accounting"], ["现金流量套期"])
        self.assertEqual(top["hedge_accounting_page"], 171)
        self.assertTrue(top["hedge_accounting_quote_verified"])

    def test_cash_flow_policy_quote_is_replaced_by_actual_reserve_evidence(self):
        top, _ = normalize({
            "disclosure_status": "有数值",
            "hedge_accounting_status": "已应用",
            "hedge_accounting_types": ["现金流量套期"],
            "hedge_accounting_evidence": {
                "page": 126,
                "quote": "预期现金流量影响损益的相同期间，将现金流量套期储备转出。",
            },
        }, (
            "【P126】预期现金流量影响损益的相同期间，将现金流量套期储备转出。\n"
            "【P171】现金流量套期储备 -2,219,839.96 291,500.00"
        ))

        self.assertEqual(top["hedge_accounting_page"], 171)
        self.assertIn("291,500.00", top["hedge_accounting_quote"])

    def test_no_derivative_business_supplies_verified_non_application_evidence(self):
        top, _ = normalize({
            "disclosure_status": "未提及",
            "hedge_accounting_status": "未应用",
            "hedge_accounting_evidence": {
                "page": 132,
                "quote": "套期会计政策包括现金流量套期。",
            },
        }, "【P32】公司报告期不存在衍生品投资。")

        self.assertEqual(top["disclosure_status"], "提及无数值")
        self.assertEqual(top["hedge_accounting_status"], "未应用")
        self.assertEqual(top["non_application_reason"], "报告期不存在衍生品投资")
        self.assertEqual(top["hedge_accounting_page"], 32)
        self.assertTrue(top["hedge_accounting_quote_verified"])

    def test_explicit_not_applicable_hedge_accounting_checkbox_means_not_applied(self):
        top, _ = normalize({
            "disclosure_status": "有数值",
            "hedge_accounting_status": "未明确披露",
        }, (
            "【P259】(2). 公司开展符合条件套期业务并应用套期会计\n"
            "□适用 √不适用"
        ))

        self.assertEqual(top["hedge_accounting_status"], "未应用")
        self.assertEqual(top["hedge_accounting_types"], [])
        self.assertIsNone(top["non_application_reason"])
        self.assertEqual(top["hedge_accounting_page"], 259)
        self.assertTrue(top["hedge_accounting_quote_verified"])

    def test_verified_table_cells_replace_llm_column_guesses(self):
        result = {
            "metrics": [{
                "metric_type": "period_purchase_amount",
                "value": 3544.49,
                "page": 35,
            }]
        }
        table_metrics = [{
            "metric_type": "derivative_fv_change_pnl",
            "value": 3544.49,
            "page": 35,
            "table_cell_verified": True,
        }]

        merged = merge_table_metrics(
            result,
            table_metrics,
            table_pages={35},
            selected_passes=["operations", "pnl"],
        )

        self.assertEqual(merged["metrics"], table_metrics)

    def test_verified_note_cells_replace_same_page_llm_guess(self):
        result = {"metrics": [{
            "metric_type": "margin_end_cash",
            "value": 32_918_039.90,
            "page": 312,
        }]}
        note_metrics = [{
            "metric_type": "margin_end_cash",
            "value": 116_653_692.30,
            "page": 312,
            "table_cell_verified": True,
        }]

        merged = merge_verified_note_metrics(
            result,
            note_metrics,
            selected_passes=["position"],
        )

        self.assertEqual(merged["metrics"], note_metrics)

    def test_nullish_underlying_is_removed(self):
        top, _ = normalize({"disclosure_status": "未提及", "underlyings": ["None", None, "null"]}, "")
        self.assertEqual(top["underlyings"], [])

    def test_verification_levels_keep_period_end_distinct_from_peak(self):
        self.assertEqual(classify("保证金占用", {"margin_peak_reported"}).level, "A")
        self.assertEqual(classify("保证金占用", {"margin_end_cash"}).level, "B")
        self.assertEqual(classify("保证金占用", {"period_pnl"}).level, "C")
        self.assertEqual(classify("保证金占用", set()).level, "D")

    def test_v15_keeps_pnl_components_as_separate_report_facts(self):
        top, metrics = normalize({
            "disclosure_status": "有数值",
            "scopes": ["商品", "外汇"],
            "hedge_accounting_status": "未应用",
            "hedge_accounting_types": [],
            "non_application_reason": None,
            "hedge_accounting_evidence": {
                "page": 259,
                "quote": "公司开展符合条件套期业务并应用套期会计：不适用。",
            },
            "metrics": [
                {
                    "metric_type": "reported_derivative_comprehensive_pnl",
                    "fact_level": "report",
                    "scope": "外汇",
                    "value": -3474.88,
                    "currency": "CNY",
                    "unit": "万元",
                    "time_basis": "period",
                    "raw": "投资收益与公允价值变动损益及浮动损益合计为-3,474.88万元",
                    "page": 44,
                },
                {
                    "metric_type": "derivative_disposal_investment_income",
                    "fact_level": "report",
                    "value": 23929647.46,
                    "currency": "CNY",
                    "unit": "元",
                    "time_basis": "period",
                    "raw": "处置衍生金融工具取得的投资收益23,929,647.46",
                    "page": 235,
                },
                {
                    "metric_type": "derivative_fv_change_pnl",
                    "fact_level": "report",
                    "value": -58678398.34,
                    "currency": "CNY",
                    "unit": "元",
                    "time_basis": "period",
                    "raw": "衍生金融工具产生的公允价值变动损益-58,678,398.34",
                    "page": 236,
                },
            ],
        }, (
            "【P44】投资收益与公允价值变动损益及浮动损益合计为-3,474.88万元\n"
            "【P235】处置衍生金融工具取得的投资收益23,929,647.46\n"
            "【P236】衍生金融工具产生的公允价值变动损益-58,678,398.34\n"
            "【P259】公司开展符合条件套期业务并应用套期会计：不适用。"
        ))

        self.assertEqual(top["hedge_accounting_status"], "未应用")
        self.assertEqual(top["hedge_accounting_types"], [])
        self.assertIsNone(top["non_application_reason"])
        self.assertEqual(top["hedge_accounting_page"], 259)
        self.assertTrue(top["hedge_accounting_quote_verified"])
        self.assertEqual([item["metric_type"] for item in metrics], [
            "reported_derivative_comprehensive_pnl",
            "derivative_disposal_investment_income",
            "derivative_fv_change_pnl",
        ])
        self.assertTrue(all(item["fact_level"] == "report" for item in metrics))
        self.assertTrue(all(item["scope"] is None for item in metrics))
        self.assertTrue(all(item["underlying"] is None for item in metrics))

    def test_generic_trading_asset_disposal_is_not_derivative_income(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "derivative_disposal_investment_income",
                "fact_level": "report",
                "value": -102120.75,
                "unit": "元",
                "time_basis": "period",
                "raw": "处置交易性金融资产取得的投资收益 -102,120.75",
                "page": 225,
            }],
        }, "【P225】处置交易性金融资产取得的投资收益 -102,120.75")

        self.assertEqual(metrics, [])

    def test_v15_margin_fact_keeps_account_context(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "margin_end_cash",
                "fact_level": "scope",
                "scope": "商品",
                "value": 65000,
                "currency": "CNY",
                "unit": "万元",
                "time_basis": "period_end",
                "account_name": "其他货币资金",
                "is_restricted": True,
                "counterparty": "某期货公司",
                "raw": "期末期货保证金65,000万元，列入其他货币资金",
                "page": 188,
            }],
        }, "【P188】期末期货保证金65,000万元，列入其他货币资金")

        self.assertEqual(metrics[0]["fact_level"], "scope")
        self.assertEqual(metrics[0]["scope"], "商品")
        self.assertEqual(metrics[0]["account_name"], "其他货币资金")
        self.assertIs(metrics[0]["is_restricted"], True)
        self.assertEqual(metrics[0]["counterparty"], "某期货公司")

    def test_v15_underlying_fact_requires_an_underlying(self):
        _, metrics = normalize({
            "disclosure_status": "有数值",
            "metrics": [{
                "metric_type": "derivative_asset_fv",
                "fact_level": "underlying",
                "scope": "商品",
                "underlying": None,
                "value": 100,
                "unit": "万元",
                "time_basis": "period_end",
                "raw": "衍生金融资产100万元",
                "page": 20,
            }],
        }, "【P20】衍生金融资产100万元")

        self.assertEqual(metrics[0]["fact_level"], "scope")
        self.assertEqual(metrics[0]["scope"], "商品")

    def test_v15_mixed_accounting_items_keep_business_level_evidence(self):
        body = (
            "【P88】外汇远期采用现金流量套期。\n"
            "【P89】商品期货未应用套期会计，因不符合套期会计指定条件。"
        )
        items = normalize_accounting_items({
            "hedge_accounting_items": [
                {
                    "scope": "外汇",
                    "instrument": "外汇远期",
                    "underlying_asset": "美元",
                    "application_status": "已应用",
                    "accounting_type": "现金流量套期",
                    "non_application_reason": None,
                    "source_section": "套期会计",
                    "page": 88,
                    "quote": "外汇远期采用现金流量套期。",
                    "confidence": 0.98,
                },
                {
                    "scope": "商品",
                    "instrument": "期货",
                    "underlying_asset": "铜",
                    "application_status": "未应用",
                    "accounting_type": None,
                    "non_application_reason": "不符合套期会计指定条件",
                    "source_section": "衍生品投资情况",
                    "page": 89,
                    "quote": "商品期货未应用套期会计，因不符合套期会计指定条件。",
                    "confidence": 0.95,
                },
            ],
        }, body)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["accounting_type"], "现金流量套期")
        self.assertTrue(items[0]["quote_verified"])
        self.assertEqual(items[1]["non_application_reason"], "不符合套期会计指定条件")
        self.assertFalse(items[1]["need_review"])

    def test_uncertain_accounting_item_does_not_keep_a_policy_method(self):
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "外汇",
                "instrument": "外汇远期",
                "application_status": "未明确披露",
                "accounting_type": "现金流量套期",
                "page": 48,
                "quote": "外汇远期合约期末金额516,807千元。",
            }],
        }, "【P48】外汇远期合约期末金额516,807千元。")

        self.assertEqual(items[0]["application_status"], "未明确披露")
        self.assertIsNone(items[0]["accounting_type"])

    def test_policy_only_quote_is_not_duplicated_into_business_items(self):
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "外汇",
                "instrument": "外汇远期",
                "application_status": "未明确披露",
                "accounting_type": "现金流量套期",
                "page": 185,
                "quote": "本集团的套期主要包括现金流量套期。",
            }],
        }, "【P185】本集团的套期主要包括现金流量套期。")

        self.assertEqual(items, [])

    def test_generic_cash_flow_hedge_policy_is_not_a_business_item(self):
        quote = (
            "除现金流量套期中属于套期有效的部分计入其他综合收益并于被套期项目"
            "影响损益时转出计入当期损益之外，衍生工具公允价值变动而产生的利得"
            "或损失，直接计入当期损益"
        )
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "外汇",
                "instrument": "未具体披露",
                "application_status": "需复核",
                "page": 141,
                "quote": quote,
            }],
        }, f"【P141】{quote}")

        self.assertEqual(items, [])

    def test_decisive_accounting_item_removes_same_scope_uncertain_duplicate(self):
        body = (
            "【P35】商品期货是否应用套期会计未明确披露。\n"
            "【P171】现金流量套期储备 291,500.00"
        )
        items = normalize_accounting_items({
            "hedge_accounting_items": [
                {
                    "scope": "商品",
                    "application_status": "未明确披露",
                    "page": 35,
                    "quote": "商品期货是否应用套期会计未明确披露。",
                },
                {
                    "scope": "商品",
                    "application_status": "已应用",
                    "accounting_type": "现金流量套期",
                    "page": 171,
                    "quote": "现金流量套期储备 291,500.00",
                },
            ],
        }, body)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["application_status"], "已应用")

    def test_unverified_decisive_accounting_claim_is_dropped(self):
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "外汇",
                "application_status": "已应用",
                "accounting_type": "公允价值套期",
                "page": 35,
                "quote": "远期金融合约采用公允价值套期。",
            }],
        }, "【P35】远期金融合约 -17,074.07 -6,509.50")

        self.assertEqual(items, [])

    def test_verified_business_table_row_does_not_prove_accounting_application(self):
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "利率",
                "instrument": "利率掉期合约",
                "application_status": "已应用",
                "accounting_type": "现金流量套期",
                "page": 48,
                "quote": "利率掉期合约 - 1,823,850 458 - - - 1,747,850 3.47%",
            }],
        }, "【P48】利率掉期合约 - 1,823,850 458 - - - 1,747,850 3.47%")

        self.assertEqual(items, [])

    def test_cash_flow_reserve_creates_verified_actual_accounting_item(self):
        items = normalize_accounting_items(
            {"hedge_accounting_items": []},
            "【P171】现金流量套期储备 -2,219,839.96 291,500.00",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["application_status"], "已应用")
        self.assertEqual(items[0]["accounting_type"], "现金流量套期")
        self.assertTrue(items[0]["quote_verified"])

    def test_blank_cash_flow_reserve_row_is_not_actual_application(self):
        items = normalize_accounting_items(
            {"hedge_accounting_items": []},
            "【P267】5.现金流量套期储备\n"
            "6.外币财务报表折算差额\n"
            "-42,536.92\n-1,055,622.64",
        )

        self.assertEqual(items, [])

    def test_no_derivative_business_creates_non_application_item(self):
        items = normalize_accounting_items(
            {"hedge_accounting_items": [{
                "application_status": "未明确披露",
                "page": 132,
                "quote": "会计政策包括现金流量套期。",
            }]},
            "【P32】公司报告期不存在衍生品投资。\n"
            "【P132】会计政策包括现金流量套期。",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["application_status"], "未应用")
        self.assertEqual(items[0]["page"], 32)
        self.assertTrue(items[0]["quote_verified"])

    def test_checkbox_keeps_a_verified_specific_non_application_reason(self):
        body = (
            "【P233】公司开展符合条件套期业务并应用套期会计 □适用 √不适用。\n"
            "衍生工具未被指定为套期工具或不符合套期会计准则的要求，未应用套期会计。"
        )
        items = normalize_accounting_items({
            "hedge_accounting_items": [{
                "scope": "商品",
                "instrument": "期货",
                "application_status": "未应用",
                "non_application_reason": "衍生工具未被指定为套期工具或不符合套期会计准则的要求",
                "page": 233,
                "quote": "衍生工具未被指定为套期工具或不符合套期会计准则的要求，未应用套期会计。",
            }],
        }, body)

        self.assertEqual(len(items), 1)
        self.assertIn("未被指定", items[0]["non_application_reason"])

    def test_verified_accounting_item_promotes_top_level_evidence(self):
        top = {
            "hedge_accounting_status": "未应用",
            "hedge_accounting_page": 375,
            "hedge_accounting_quote": "包含省略号……",
            "hedge_accounting_quote_verified": False,
            "non_application_reason": "原文明示原因",
        }
        items = [{
            "application_status": "未应用",
            "page": 375,
            "quote": "考虑交易期限短及处理成本效益，未应用套期会计。",
            "quote_verified": True,
            "non_application_reason": "交易期限短及处理成本效益",
        }]

        promote_verified_accounting_evidence(top, items)

        self.assertTrue(top["hedge_accounting_quote_verified"])
        self.assertNotIn("省略号", top["hedge_accounting_quote"])
        self.assertEqual(top["non_application_reason"], "交易期限短及处理成本效益")

    def test_multipass_metric_families_are_disjoint_and_complete(self):
        members = [metric for family in METRIC_FAMILIES.values() for metric in family]

        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(set(members), {
            "period_purchase_amount", "period_sale_amount", "ending_balance",
            "net_asset_ratio", "notional_end_reported", "notional_peak_reported",
            "contract_quantity_end", "reported_derivative_comprehensive_pnl",
            "derivative_disposal_investment_income", "derivative_fv_change_pnl",
            "oci_amount", "reclassification_amount", "derivative_asset_fv",
            "derivative_liability_fv", "derivative_net_fv", "margin_end_cash",
            "margin_peak_reported", "collateral_end_fair_value",
            "credit_facility_used_end", "option_premium_usage_peak",
        })

    def test_merge_pass_results_rejects_metrics_from_the_wrong_family(self):
        merged = merge_pass_results(
            {"disclosure_status": "有数值", "metrics": [{"metric_type": "period_pnl"}]},
            {
                "operations": {"metrics": [
                    {"metric_type": "period_purchase_amount", "value": 1},
                    {"metric_type": "derivative_asset_fv", "value": 2},
                ]},
                "position": {"metrics": [
                    {"metric_type": "derivative_asset_fv", "value": 3},
                ]},
            },
        )

        self.assertEqual([row["value"] for row in merged["metrics"]], [1, 3])


class PeriodicValidationBatchTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_validation_batch_has_six_unique_cross_scope_companies(self):
        path = self.ROOT / "config" / "annual_validation_2025.csv"
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 6)
        self.assertEqual({row["code"] for row in rows}, {
            "000039", "000651", "002385", "002649", "600961", "688223",
        })
        self.assertEqual({row["scope_group"] for row in rows}, {
            "商品", "外汇", "商品+外汇",
        })
        self.assertTrue(all(row["locator_terms"] for row in rows))

    def test_workflow_defaults_to_validation_batch_and_scopes_all_stages(self):
        path = self.ROOT / ".github" / "workflows" / "periodic-poc.yml"
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        dispatch = (workflow.get("on") or workflow.get(True))["workflow_dispatch"]
        self.assertEqual(dispatch["inputs"]["sample_set"]["default"], "validation6")

        job = workflow["jobs"]["periodic-poc"]
        self.assertEqual(job["env"]["LLM_THINKING"], "off")
        sample_expression = job["env"]["SAMPLE_FILE"]
        self.assertIn("config/annual_validation_2025.csv", sample_expression)
        self.assertIn("config/annual_poc_2025.csv", sample_expression)

        commands = "\n".join(
            step.get("run", "") for step in job["steps"] if isinstance(step, dict)
        )
        self.assertEqual(commands.count('--sample "$SAMPLE_FILE"'), 3)

    def test_locator_reserves_pages_for_each_financial_fact_family(self):
        pages = ["套期保值 衍生品投资 " * 8 for _ in range(20)]
        pages.extend([
            "普通经营内容",
            "其他货币资金中期货保证金为100万元",
            "普通经营内容",
            "公司对外汇远期应用现金流量套期",
            "普通经营内容",
            "衍生工具公允价值变动损益为-20万元",
            "普通经营内容",
            "衍生金融资产100万元，衍生金融负债80万元",
        ])

        selected, _, _ = select_candidate_pages(pages)

        self.assertTrue({22, 24, 26, 28}.issubset(set(selected)))

    def test_locator_keeps_each_pnl_component_and_both_fair_value_sides(self):
        pages = ["套期保值 衍生品投资 " * 8 for _ in range(20)]
        pages.extend([
            "处置衍生金融工具取得的投资收益",
            "衍生工具公允价值变动损益",
            "现金流量套期储备计入其他综合收益",
            "期末衍生金融资产",
            "期末衍生金融负债",
        ])

        selected, _, _ = select_candidate_pages(pages)

        self.assertTrue({21, 22, 23, 24, 25}.issubset(set(selected)))

    def test_locator_reserves_a_company_specific_underlying_page(self):
        pages = ["套期保值 衍生品投资 " * 8 for _ in range(20)]
        pages.extend([
            "普通经营内容",
            "多晶硅期货用于原材料价格风险管理",
        ])

        selected, matched, _ = select_candidate_pages(pages, ["多晶硅"])

        self.assertIn(22, selected)
        self.assertIn("多晶硅", matched)

    def test_locator_reserves_actual_accounting_and_specific_financial_notes(self):
        pages = ["套期保值 衍生品投资 " * 8 for _ in range(20)]
        pages.extend([
            "公司未应用套期会计的原因是交易期限较短",
            "衍生金融工具资产期末余额8,305,380元",
            "衍生金融工具负债期末余额11,453,070元",
            "衍生金融工具产生的公允价值变动收益为-14,780,760元",
            "期货合约保证金期末余额116,653,692.30元",
        ])

        selected, _, _ = select_candidate_pages(pages)

        self.assertTrue({21, 22, 23, 24, 25}.issubset(set(selected)))

    def test_locator_reserves_cash_flow_hedge_reserve_page(self):
        pages = ["套期保值 衍生品投资 " * 8 for _ in range(20)]
        pages.extend([
            "会计政策 现金流量套期储备 " * 5,
            "普通经营内容",
            "现金流量套期储备\n本期所得税前\n发生额291,500元",
        ])

        selected, _, _ = select_candidate_pages(pages)

        self.assertIn(23, selected)

    def test_standard_derivative_table_keeps_gree_column_meaning(self):
        rows = [
            [
                "衍生品投资类型", "初始投资金额", "期初金额", "本期公允价值\n变动损益",
                "计入权益的累计\n公允价值变动", "报告期内购\n入金额", "报告期内售\n出金额",
                "期末金额", "期末投资金额占\n公司报告期末净\n资产比例",
            ],
            ["期货套保合约", "2,471.02", "2,471.02", "3,544.49", "29.15", "", "", "6,015.51", "0.04%"],
            ["远期金融合约", "-17,074.07", "-17,074.07", "10,386.41", "", "", "", "-6,509.50", "-0.04%"],
            ["合计", "-14,603.05", "-14,603.05", "13,930.90", "29.15", "", "", "-493.99", "0.00%"],
        ]

        metrics = parse_derivative_investment_table(rows, page=35, unit="万元")

        self.assertEqual([
            (item["metric_type"], item["scope"], item["value"])
            for item in metrics
        ], [
            ("derivative_fv_change_pnl", "商品", 3544.49),
            ("oci_amount", "商品", 29.15),
            ("ending_balance", "商品", 6015.51),
            ("net_asset_ratio", "商品", 0.04),
            ("derivative_fv_change_pnl", "外汇", 10386.41),
            ("ending_balance", "外汇", -6509.50),
            ("net_asset_ratio", "外汇", -0.04),
        ])
        self.assertNotIn("period_purchase_amount", {
            item["metric_type"] for item in metrics
        })
        self.assertTrue(all(item["table_cell_verified"] for item in metrics))

    def test_standard_derivative_table_extracts_dbn_transactions(self):
        rows = [
            [
                "衍生品投资类型", "初始投资金额", "期初金额", "本期公允价值变动损益",
                "计入权益的累计公允价值变动", "报告期内购入金额", "报告期内售出金额",
                "期末金额", "期末投资金额占公司报告期末净资产比例",
            ],
            ["期货", "", "4,455.11", "-1,478.08", "", "92,099.81", "84,878.89", "11,350.6", "1.17%"],
        ]

        metrics = parse_derivative_investment_table(rows, page=35, unit="万元")

        self.assertEqual({
            item["metric_type"]: item["value"] for item in metrics
        }, {
            "derivative_fv_change_pnl": -1478.08,
            "period_purchase_amount": 92099.81,
            "period_sale_amount": 84878.89,
            "ending_balance": 11350.6,
            "net_asset_ratio": 1.17,
        })

    def test_standard_derivative_table_keeps_hedging_business_rows(self):
        rows = [
            [
                "衍生品投资类型", "初始投资金额", "期初金额", "本期公允价值变动损益",
                "计入权益的累计公允价值变动", "报告期内购入金额", "报告期内售出金额",
                "期末金额", "期末投资金额占公司报告期末净资产比例",
            ],
            [
                "商品期货套期保值", "", "865.83", "-287.36", "",
                "118,567.87", "111,110.40", "756.61", "0.20%",
            ],
        ]

        metrics = parse_derivative_investment_table(rows, page=49, unit="万元")

        self.assertEqual({
            item["metric_type"]: item["value"] for item in metrics
        }, {
            "derivative_fv_change_pnl": -287.36,
            "period_purchase_amount": 118567.87,
            "period_sale_amount": 111110.40,
            "ending_balance": 756.61,
            "net_asset_ratio": 0.20,
        })

    def test_standard_derivative_table_handles_sparse_multiline_headers(self):
        rows = [
            [
                "", None, None, "", None, None, "", None, "", "本期公",
                "", "计入权", "", None, "报告期内购", None,
                "报告期内售", None, None, "期末金额", "期末投资", None,
            ],
            [
                "", "衍生品投资类", None, "", "初始投资金", None,
                "期初金额", None, "", "允价值变动损益", None,
                "益的累计公允价值变动", None, None, "入金额", None,
                "出金额", None, None, None, "金额占公司报告期末净资产比例", None,
            ],
            [
                "商品套期保值", None, None, "865.83", None, None,
                "865.83", None, "-287.36", None, None, "0", None,
                None, "118,567.87", None, "111,110.4", None, None,
                "756.61", "0.20%", None,
            ],
        ]

        metrics = parse_derivative_investment_table(rows, page=49, unit="万元")

        self.assertEqual({
            item["metric_type"]: item["value"] for item in metrics
        }, {
            "derivative_fv_change_pnl": -287.36,
            "oci_amount": 0.0,
            "period_purchase_amount": 118567.87,
            "period_sale_amount": 111110.40,
            "ending_balance": 756.61,
            "net_asset_ratio": 0.20,
        })

    def test_standard_derivative_table_accepts_book_value_header_variant(self):
        metrics = parse_derivative_investment_table([
            [
                "衍生品投资类型", "初始投资金额", "期初账面价值", "本期公允价值变动损益",
                "计入权益的累计公允价值变动", "报告期内购入金额", "报告期内售出金额",
                "期末账面价值", "期末账面价值占公司报告期末净资产比例（%）",
            ],
            ["普通远期", "", "9,825.65", "-9,875.41", "", "23,025.19", "25,141.68", "-2,166.24", "-0.09"],
        ], page=43, unit="万元")

        self.assertEqual({
            item["metric_type"]: item["value"] for item in metrics
        }, {
            "derivative_fv_change_pnl": -9875.41,
            "period_purchase_amount": 23025.19,
            "period_sale_amount": 25141.68,
            "ending_balance": -2166.24,
            "net_asset_ratio": -0.09,
        })

    def test_note_tables_extract_margin_positions_and_pnl_components(self):
        margin = parse_derivative_note_table([
            ["款项性质", "年末账面余额", "年初账面余额"],
            ["期货合约保证金", "116,653,692.30", "32,918,039.90"],
        ], page=312, unit="元")
        fair_value = parse_derivative_note_table([
            ["项目", "年末公允价值", None, None, None],
            [None, "第一层次", "第二层次", "第三层次", "合计"],
            ["（一）交易性金融资产", "182,227,655.19", "", "186,776,727.57", "369,004,382.76"],
            ["（5）衍生金融工具", "8,305,380.00", "", "", "8,305,380.00"],
            ["（五）交易性金融负债", "11,453,070.00", "", "12,072,387.97", "23,525,457.97"],
            ["（2）衍生金融工具", "11,453,070.00", "", "", "11,453,070.00"],
        ], page=376, unit="元")
        pnl = parse_derivative_note_table([
            ["产生公允价值变动收益的来源", "本年发生额", "上年发生额"],
            ["衍生金融工具产生的公允价值变动", "-14,780,760.00", "9,669,520.00"],
        ], page=353, unit="元")

        self.assertEqual(
            [(item["metric_type"], item["value"]) for item in margin],
            [("margin_end_cash", 116653692.30)],
        )
        self.assertEqual(
            [(item["metric_type"], item["value"]) for item in fair_value],
            [
                ("derivative_asset_fv", 8305380.00),
                ("derivative_liability_fv", 11453070.00),
            ],
        )
        self.assertEqual(
            [(item["metric_type"], item["value"]) for item in pnl],
            [("derivative_fv_change_pnl", -14780760.00)],
        )

    def test_note_table_extracts_named_derivative_investment_income(self):
        metrics = parse_derivative_note_table([
            ["黄金T+D、白银T+D 交易投资收益", "-124,564,900.58", "-52,753,894.76"],
            ["理财产品投资收益", "11,761,438.05", "17,220,536.22"],
            ["合计", "-112,393,163.93", "-36,721,157.06"],
        ], page=143, unit="元")

        self.assertEqual(
            [(item["metric_type"], item["value"], item["account_name"]) for item in metrics],
            [(
                "derivative_disposal_investment_income",
                -124564900.58,
                "黄金T+D、白银T+D交易投资收益",
            )],
        )

    def test_note_table_extracts_cash_flow_hedge_reserve_columns(self):
        metrics = parse_derivative_note_table([
            ["项目", "期初余额", "本期发生额", None, None, None, None, None, "期末余额"],
            [None, None, "本期所得税前发生额", "减：前期计入其他综合收益当期转入损益",
             None, "减：所得税费用", "税后归属于母公司", None, None],
            ["现金流量套期储备", "-2,219,839.96", "291,500.00", "-2,646,800.00",
             "", "445,535.00", "2,492,765.00", "", "272,925.04"],
        ], page=171, unit="元")

        self.assertEqual(
            [(item["metric_type"], item["value"]) for item in metrics],
            [("oci_amount", 291500.00), ("reclassification_amount", -2646800.00)],
        )

    def test_fair_value_continuation_extracts_derivative_liability_total(self):
        metrics = parse_derivative_note_table([
            ["项目", "期末公允价值", None, None, None],
            [None, "第一层次", "第二层次", "第三层次", "合计"],
            ["持续以公允价值计量的资产总额", "24,456,135.00", "1,336,477,688.59", "", "1,863,590,284.88"],
            ["（五）衍生金融负债", "", "", "", ""],
            ["1.期货及期权衍生工具", "27,564,486.13", "", "", "27,564,486.13"],
            ["2.外汇衍生工具", "", "28,564,260.48", "", "28,564,260.48"],
            ["持续以公允价值计量的负债总额", "27,564,486.13", "28,564,260.48", "", "56,128,746.61"],
        ], page=261, unit="元")

        self.assertEqual(
            [(item["metric_type"], item["value"]) for item in metrics],
            [("derivative_liability_fv", 56128746.61)],
        )

    def test_each_table_uses_the_nearest_preceding_unit(self):
        blocks = [
            (0, 10, 100, 20, "单位：元 币种：人民币", 0, 0),
            (0, 200, 100, 210, "单位：万元 币种：人民币", 0, 0),
        ]

        self.assertEqual(unit_before_table(blocks, table_top=100, page_text=""), "元")
        self.assertEqual(unit_before_table(blocks, table_top=250, page_text=""), "万元")

    def test_parent_company_note_start_is_detected(self):
        self.assertEqual(find_parent_company_note_start([
            "合并财务报表项目注释",
            "十九、母公司财务报表主要项目注释",
            "投资收益",
        ]), 2)

    def test_marked_text_keeps_every_candidate_page_and_late_focus_term(self):
        pages = [
            ("普通内容" * 1500) + term
            for term in ("套期保值", "公允价值变动损益", "衍生金融负债", "保证金")
        ]

        marked = build_marked_text(
            pages,
            [1, 2, 3, 4],
            ["套期保值", "公允价值变动损益", "衍生金融负债", "保证金"],
        )

        self.assertLessEqual(len(marked), MAX_MARKED_CHARS)
        self.assertTrue(all(f"【P{page}】" in marked for page in range(1, 5)))
        self.assertTrue(all(term in marked for term in (
            "套期保值", "公允价值变动损益", "衍生金融负债", "保证金",
        )))


if __name__ == "__main__":
    unittest.main()
