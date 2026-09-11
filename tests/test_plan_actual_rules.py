"""M5 guards: never turn incompatible or missing facts into compliance conclusions."""
import importlib
import unittest


def rules():
    try:
        return importlib.import_module('scripts.plan_actual_rules')
    except ModuleNotFoundError as exc:
        raise AssertionError('M5 deterministic comparison rules are not implemented') from exc


def report(**changes):
    return dict(report_id='r1', code='000001', fiscal_year=2025,
                report_type='annual', status='extracted', period_end='2025-12-31',
                **changes)


def metric(**changes):
    data = dict(id=1, report_id='r1', metric_type='margin_end_cash',
                scope='商品', fact_level='scope', value=2000, unit='万元',
                currency='CNY', time_basis='period_end', value_verified=True,
                quote_verified=True, raw_text='期末期货保证金2000万元', page=30)
    return {**data, **changes}


def plan(**changes):
    data = dict(id=2, ann_id='a1', code='000001', scope='商品',
                ann_role='计划-董事会', basis='保证金占用', amount=30000000,
                currency='CNY', amount_verified=True, quote_verified=True,
                raw_text='期货保证金最高占用额不超过3000万元', page=2,
                period_text='自2025年1月1日起至2025年12月31日',
                period_quote='自2025年1月1日起至2025年12月31日',
                period_quote_verified=True, period_page=3)
    return {**data, **changes}


class NumericRulesTest(unittest.TestCase):
    def check(self, item=None, plans=None, scopes=None):
        return rules().compare_numeric(report(), item or metric(),
                                       [plan()] if plans is None else plans,
                                       scopes or ['商品'])

    def test_units_and_point_in_time_not_full_period(self):
        result = self.check()
        self.assertEqual(result['status'], 'within_snapshot')
        self.assertEqual(result['grade'], 'B')
        self.assertEqual(result['actual_base'], '20000000')
        self.assertEqual(result['quota_base'], '30000000')
        self.assertEqual(result['source_quota_ids'], [2])
        self.assertTrue(result['requires_review'])

    def test_peak_needs_full_period_coverage(self):
        item = metric(metric_type='margin_peak_reported', time_basis='period_peak')
        self.assertEqual(self.check(item)['grade'], 'A')
        period = '自2025年7月1日起至2025年12月31日'
        self.assertEqual(self.check(item, [plan(period_text=period, period_quote=period)])['status'], 'period_uncovered')

    def test_zero_is_valid_missing_is_not(self):
        self.assertEqual(self.check(metric(value=0))['status'], 'within_snapshot')
        for value in (None, '', 'NaN', 'Infinity'):
            self.assertEqual(self.check(metric(value=value))['status'], 'missing_value')

    def test_exceeding_quota_is_review_not_violation(self):
        self.assertEqual(self.check(metric(value=4000))['status'], 'exceeds_disclosed_cap')
        self.assertTrue(self.check(metric(value=4000))['requires_review'])

    def test_legacy_extracted_authorization_is_not_actual_usage(self):
        item = metric(metric_type='margin_peak_reported', time_basis='period_peak',
                      raw_text='商品期货保证金最高占用额度不超过2000万元')
        self.assertEqual(self.check(item)['status'], 'actual_is_authorization')

    def test_actual_peak_with_cap_comment_is_not_authorization(self):
        item=metric(metric_type='margin_peak_reported',time_basis='period_peak',
                    raw_text='报告期实际保证金峰值为2000万元，未超过授权额度3000万元')
        self.assertEqual(self.check(item)['status'],'within_period')
        item['raw_text']='实际保证金峰值为1000万元，授权额度上限为2000万元'
        self.assertEqual(self.check(item)['status'],'actual_is_authorization')

    def test_never_compare_pnl_assets_or_purchase_flows_to_caps(self):
        for kind in ('derivative_asset_fv', 'period_purchase_amount', 'derivative_fv_change_pnl'):
            self.assertEqual(self.check(metric(metric_type=kind))['status'], 'basis_incomparable')

    def test_currency_units_and_credit_must_match(self):
        self.assertEqual(self.check(metric(currency='USD'))['status'], 'currency_mismatch')
        self.assertEqual(self.check(metric(unit='其他'))['status'], 'unit_unknown')
        self.assertEqual(self.check(metric(raw_text='保证金包括占用银行授信'))['status'], 'coverage_uncertain')
        self.assertEqual(self.check(plans=[plan(raw_text='保证金（含银行授信）不超过3000万元')])['status'], 'coverage_uncertain')

    def test_report_totals_cannot_be_split_into_scopes(self):
        item = metric(fact_level='report', scope=None)
        self.assertEqual(self.check(item, scopes=['商品', '外汇'])['status'], 'scope_uncertain')
        self.assertEqual(self.check(item, scopes=['商品'])['status'], 'within_snapshot')
        self.assertEqual(self.check(plans=[plan(scope='综合')])['status'], 'scope_uncertain')

    def test_evidence_and_actual_plan_roles_are_required(self):
        self.assertEqual(self.check(metric(value_verified=False))['status'], 'evidence_unverified')
        self.assertEqual(self.check(plans=[plan(quote_verified=False)])['status'], 'evidence_unverified')
        self.assertEqual(self.check(plans=[plan(ann_role='可行性分析')])['status'], 'no_plan')
        self.assertEqual(self.check(plans=[plan(code='000002')])['status'], 'no_plan')

    def test_relative_period_or_year_label_is_not_a_date(self):
        for period in ('2025年度', '自股东大会通过之日起12个月', '自2024年年度股东大会至2025年年度股东大会'):
            self.assertEqual(self.check(plans=[plan(period_text=period, period_quote=period)])['status'], 'period_unknown')
        self.assertEqual(self.check(plans=[plan(period_quote_verified=False)])['status'], 'period_unknown')

    def test_cross_year_period_and_conflicts_are_not_latest_or_max(self):
        period = '自2024年12月1日起至2026年1月31日'
        self.assertEqual(self.check(plans=[plan(period_text=period, period_quote=period)])['status'], 'within_snapshot')
        for items in ([plan(), plan(id=3, amount=50000000)], [plan(id=3, amount=50000000), plan()]):
            self.assertEqual(self.check(plans=items)['status'], 'quota_conflict')
        duplicate = self.check(plans=[plan(), plan(id=3, ann_id='a2')])
        self.assertEqual(duplicate['source_quota_ids'], [2, 3])

    def test_unresolved_amendment_blocks_old_numeric_conclusion(self):
        extra = plan(id=3, amount=50000000, period_text='股东大会通过起十二个月', period_quote='股东大会通过起十二个月')
        self.assertEqual(self.check(plans=[plan(), extra])['status'], 'period_unknown')


class DimensionalRulesTest(unittest.TestCase):
    def test_deterministic_aliases_and_missing_evidence(self):
        result = rules().compare_names(['美金', '欧元'], ['美元', '日元'])
        self.assertEqual(result['intersection'], ['美元'])
        self.assertEqual(result['actual_only'], ['日元'])
        self.assertEqual(result['plan_only'], ['欧元'])
        self.assertEqual(rules().compare_names(['铜'], [])['status'], 'insufficient_evidence')
        self.assertEqual(rules().compare_names(['铜'], ['铜'], open_ended=True)['status'], 'open_authorization')

    def test_missing_dimension_prevents_overall_match(self):
        self.assertEqual(rules().overall_status(['consistent', 'insufficient_evidence', 'within_snapshot']), 'needs_review')

    def test_canonical_report_keeps_periods_separate_and_processed_version(self):
        rows = [report(), {**report(), 'report_id':'r2', 'is_revised':True, 'status':'located'},
                {**report(), 'report_id':'h1', 'report_type':'semiannual'}]
        self.assertEqual(sorted(x['report_id'] for x in rules().canonical_reports(rows)), ['h1', 'r1'])


if __name__ == '__main__':
    unittest.main()
