import unittest
from scripts.periodic_pdf import (merge_derivative_continuation, parse_derivative_investment_table,
                                  select_candidate_pages, COVERAGE_TERM_GROUPS)
from scripts.extract_periodic_reports import normalize


class PilotGuardTest(unittest.TestCase):
    def test_fundraising_table_is_not_derivative_continuation(self):
        header = [['衍生品投资类型','初始投资金额','期初金额','本期公允价值变动损益',
                   '计入权益的累计公允价值变动','报告期内购入金额','报告期内售出金额',
                   '期末金额','期末投资金额占公司报告期末净资产比例']]
        funding = [['募集年份','募集方式','上市日期','募集资金总额','募集资金净额',
                    '本期已使用募集资金','累计使用金额','使用比例','变更用途资金'],
                   ['2024','定向增发','2024-08-15','70000','69260.55','1665.19','63111.14','91.12%','5078.48']]
        combined = merge_derivative_continuation(funding, prior_header_rows=header,
                         prior_page=29,page=30,table_top=60)
        self.assertEqual(parse_derivative_investment_table(combined,30,'万元'), [])

    def test_cap_not_actual_peak_and_translation_not_hedge_oci(self):
        for kind, quote in [
            ('margin_peak_reported','商品期货套期保值业务任意时点保证金最高占用额不超过人民币5.45亿元'),
            ('notional_peak_reported','拟开展外汇业务，最高合约价值不超过5.45亿元'),
            ('oci_amount','外币财务报表折算差额 5.45'),
        ]:
            _, metrics = normalize({'disclosure_status':'有数值', 'metrics':[
                {'metric_type':kind,'value':5.45,'unit':'亿元','currency':'CNY',
                 'page':21,'raw':quote,'time_basis':'period_peak'}]}, '【P21】'+quote)
            self.assertEqual(metrics, [], kind)

    def test_actual_peak_is_retained(self):
        quote='报告期商品期货实际保证金最高占用额为5.45亿元'
        _, metrics=normalize({'disclosure_status':'有数值','metrics':[
            {'metric_type':'margin_peak_reported','value':5.45,'unit':'亿元','currency':'CNY',
             'page':21,'raw':quote,'scope':'商品','time_basis':'period_peak'}]},'【P21】'+quote)
        self.assertEqual(len(metrics),1)

    def test_actual_peak_with_authorization_comment_is_retained(self):
        quote='报告期商品期货实际保证金最高占用额为5.45亿元，未超过授权额度'
        _, metrics=normalize({'disclosure_status':'有数值','metrics':[
            {'metric_type':'margin_peak_reported','value':5.45,'unit':'亿元','currency':'CNY',
             'page':21,'raw':quote,'scope':'商品','time_basis':'period_peak'}]},'【P21】'+quote)
        self.assertEqual(len(metrics),1)

    def test_scaled_actual_peak_with_comment_is_retained(self):
        quote='报告期商品期货实际保证金最高占用额为5.45亿元，未超过授权额度'
        _, metrics=normalize({'disclosure_status':'有数值','metrics':[
            {'metric_type':'margin_peak_reported','value':545000000,'unit':'元','currency':'CNY',
             'page':21,'raw':quote,'scope':'商品','time_basis':'period_peak'}]},'【P21】'+quote)
        self.assertEqual(len(metrics),1)
        self.assertEqual((metrics[0]['value'],metrics[0]['unit']),(5.45,'亿元'))

    def test_cash_table_is_not_currency_derivative_continuation(self):
        header=[['衍生品投资类型','初始投资金额','期初金额','本期公允价值变动损益',
                 '计入权益的累计公允价值变动','报告期内购入金额','报告期内售出金额',
                 '期末金额','期末投资金额占公司报告期末净资产比例']]
        rows=[['货币资金','-','100','20','3','50','40','110','1%']]
        combined=merge_derivative_continuation(rows,prior_header_rows=header,
                                              prior_page=29,page=30,table_top=60)
        self.assertEqual(parse_derivative_investment_table(combined,30,'万元'),[])

    def test_fx_contract_continuation_is_retained(self):
        header=[['衍生品投资类型','初始投资金额','期初金额','本期公允价值变动损益',
                 '计入权益的累计公允价值变动','报告期内购入金额','报告期内售出金额',
                 '期末金额','期末投资金额占公司报告期末净资产比例']]
        rows=[['外汇合约','-','100','20','3','50','40','110','1%']]
        combined=merge_derivative_continuation(rows,prior_header_rows=header,
                                              prior_page=29,page=30,table_top=60)
        self.assertEqual(len(parse_derivative_investment_table(combined,30,'万元')),6)

    def test_derivative_table_page_survives_high_score_narrative(self):
        pages=['衍生品投资类型 初始投资金额 本期公允价值变动损益 期末账面价值',
               '报告期实际损益情况的说明 投资收益与公允价值变动损益合计为-40万元']
        for terms in COVERAGE_TERM_GROUPS.values():
            pages.extend(['背景', ' '.join(terms)*10, '其他'])
        picked, _, _=select_candidate_pages(pages)
        self.assertIn(1,picked)
        self.assertIn(2,picked)
        self.assertLessEqual(len(picked),15)


if __name__ == '__main__':
    unittest.main()
