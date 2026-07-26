import csv
import unittest
from pathlib import Path

import yaml

from scripts.extract_periodic_reports import (
    merge_pass_results,
    normalize,
    normalize_accounting_items,
    verify_raw_value,
)
from scripts.extract_announcements import thinking_extra_body
from scripts.prompt_periodic import METRIC_FAMILIES
from scripts.periodic_verification import classify
from scripts.periodic_pdf import (
    MAX_MARKED_CHARS,
    build_marked_text,
    select_candidate_pages,
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
