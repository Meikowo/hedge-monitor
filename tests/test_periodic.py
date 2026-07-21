import unittest

from scripts.extract_periodic_reports import normalize, verify_raw_value
from scripts.periodic_verification import classify


class PeriodicNormalizationTest(unittest.TestCase):
    def test_raw_value_requires_literal_number(self):
        self.assertTrue(verify_raw_value(1234.56, "本期金额为1,234.56万元"))
        self.assertFalse(verify_raw_value(1234.56, "本期金额约一千万元"))

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


if __name__ == "__main__":
    unittest.main()
