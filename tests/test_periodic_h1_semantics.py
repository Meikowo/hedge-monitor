import unittest
from scripts.extract_periodic_reports import extract_explicit_pnl_metrics, normalize_summary, normalize, normalize_accounting_items


class H1SemanticsTest(unittest.TestCase):
    def test_mixed_derivative_total_keeps_report_scope(self):
        text=('【P28】报告期实际损益情况的说明\n报告期末，因外汇衍生品和期货交易产生的'
              '投资收益与公允价值变动损益及浮动损益合计为-40,313.15 万\n元。')
        metrics=extract_explicit_pnl_metrics(text)
        self.assertEqual(len(metrics),1)
        self.assertEqual((metrics[0]['value'],metrics[0]['unit'],metrics[0]['scope']),(-40313.15,'万元',None))
        _, checked=normalize({'disclosure_status':'有数值','metrics':metrics},text)
        self.assertEqual(len(checked),1)

    def test_commodity_total_is_not_lost(self):
        text='【P20】报告期实际损益\n情况的说明\n计入报告期内的商品衍生品损益合计为-26,058,614.68 元。'
        metrics=extract_explicit_pnl_metrics(text)
        self.assertEqual(len(metrics),1)
        self.assertEqual((metrics[0]['value'],metrics[0]['scope'],metrics[0]['page']),(-26058614.68,'商品',20))

    def test_non_derivative_or_forecast_totals_do_not_become_actual_pnl(self):
        for text in ('预计商品衍生品损益合计为300万元','公司投资收益与公允价值变动损益合计为300万元'):
            self.assertEqual(extract_explicit_pnl_metrics('【P20】'+text),[])

    def test_uncertain_accounting_does_not_claim_application_in_summary(self):
        text=normalize_summary('持有外汇远期，附注披露采用现金流量套期会计。',['外汇'],'有数值','未明确披露',None)
        self.assertNotIn('采用现金流量套期会计',text)
        self.assertIn('未明确披露',text)

    def test_no_activity_summary_takes_precedence_over_accounting(self):
        for state in ('未明确披露','需复核'):
            text=normalize_summary('仅列示套期会计政策。',[],'未提及',state,None)
            self.assertIn('未发现衍生品业务披露',text)

    def test_forecast_prefix_and_non_derivative_label_are_rejected(self):
        for raw in ('预计计入报告期内的商品衍生品损益合计为300万元。',
                    '计入报告期内的非衍生品损益合计为300万元。'):
            self.assertEqual(extract_explicit_pnl_metrics('【P20】'+raw),[])

    def test_named_hedge_method_claim_is_synchronized(self):
        text=normalize_summary('公司对外汇远期已采用现金流量套期核算。',['外汇'],'有数值','未明确披露',None)
        self.assertNotIn('已采用',text)
        self.assertIn('未明确披露',text)

    def test_explicit_no_investment_does_not_claim_derivative_activity(self):
        top, _ = normalize({
            'disclosure_status': '提及无数值',
            'hedge_accounting_status': '未应用',
            'summary': '报告期未开展衍生品投资，未应用套期会计。',
        }, '【P22】博彦科技股份有限公司2026年半年度报告全文\n21\n（2）衍生品投资情况\n□适用 不适用\n公司报告期不存在衍生品投资。')
        self.assertIn('不存在衍生品投资', top['summary'])
        self.assertNotIn('披露衍生品业务', top['summary'])

    def test_total_oci_is_not_a_derivative_fact_even_with_model_context(self):
        raw = '六、其他综合收益的税后净额 -5,599,959.47 22,702,921.81'
        for kind in ('oci_amount', 'reclassification_amount'):
            _, metrics = normalize({'disclosure_status': '有数值', 'metrics': [{
                'metric_type': kind, 'value': -5599959.47, 'unit': '元',
                'page': 158, 'raw': raw, 'source_section': '套期会计',
                'account_name': '现金流量套期储备',
            }]}, '【P158】' + raw)
            self.assertEqual(metrics, [])

    def test_explicit_derivative_oci_and_table_row_remain_available(self):
        for raw, value, unit in (
            ('现金流量套期储备 本期所得税前发生额 -3,838,025.00', -3838025, '元'),
            ('期货套保合约 计入权益的累计公允价值变动 -383.80', -383.80, '万元'),
        ):
            _, metrics = normalize({'disclosure_status': '有数值', 'metrics': [{
                'metric_type': 'oci_amount', 'value': value, 'unit': unit,
                'page': 144, 'raw': raw,
            }]}, '【P144】' + raw)
            self.assertEqual(len(metrics), 1)

    def test_reported_derivative_loss_total_does_not_include_fx_translation(self):
        text = ('【P30】与上一报告期相比是否发生重大变化的说明 否\n报告期实际损益情况的说明\n'
                '报告期内，本集团衍生金融工具公允价值变动损失为24,343千元人民币，'
                '投资收益为14,576千元人民币，两者合计损失为9,767千元人民币。'
                '其中，报告期内本集团外汇相关的衍生品投资活动净损失为9,766千元人民币，'
                '是衍生金融工具合计损失的主要构成。此外，本期汇兑损失为802,510千元人民币。')
        candidates = extract_explicit_pnl_metrics(text)
        _, metrics = normalize({'disclosure_status': '有数值', 'metrics': candidates}, text)
        self.assertEqual([(m['value'], m['scope'], m['unit']) for m in metrics],
                         [(-9767, None, '千元'), (-9766, '外汇', '千元')])

    def test_forecast_loss_and_non_derivative_totals_are_not_promoted(self):
        for text in (
            '预计报告期内，本集团衍生金融工具公允价值变动损失为20千元人民币，投资收益为10千元人民币，两者合计损失为10千元人民币。',
            '报告期内，本集团非衍生金融工具公允价值变动损失为20千元人民币，投资收益为10千元人民币，两者合计损失为10千元人民币。',
            '预计报告期内本集团外汇相关的衍生品投资活动净损失为10千元人民币。',
        ):
            self.assertEqual(extract_explicit_pnl_metrics('【P30】' + text), [])

    def test_comparative_and_postfixed_forecast_are_not_current_actuals(self):
        for text in (
            '上年同期，本集团外汇相关的衍生品投资活动净损失为9,766千元人民币。',
            '报告期内本集团外汇相关的衍生品投资活动净损失为9,766千元人民币，为预测值。',
            '上年同期，本集团衍生金融工具公允价值变动损失为20千元人民币，投资收益为10千元人民币，两者合计损失为10千元人民币。',
        ):
            self.assertEqual(extract_explicit_pnl_metrics('【P30】' + text), [])

    def test_previous_period_no_investment_is_not_a_current_denial(self):
        body = '【P22】上一报告期不存在衍生品投资。本报告期外汇相关的衍生品投资活动净收益为100万元人民币。'
        result = {'disclosure_status': '有数值', 'scopes': ['外汇'],
                  'summary': '本报告期外汇衍生品收益100万元。',
                  'metrics': extract_explicit_pnl_metrics(body)}
        top, metrics = normalize(result, body)
        self.assertEqual(len(metrics), 1)
        self.assertNotIn('不存在衍生品投资', top['summary'])
        self.assertNotEqual(top['hedge_accounting_status'], '未应用')
        self.assertEqual(normalize_accounting_items(result, body), [])

    def test_conflicting_no_activity_and_current_facts_require_review(self):
        body = '【P22】公司报告期不存在衍生品投资。本报告期外汇相关的衍生品投资活动净收益为100万元人民币。'
        result = {'disclosure_status': '有数值', 'scopes': ['外汇'],
                  'metrics': extract_explicit_pnl_metrics(body)}
        top, metrics = normalize(result, body)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(top['disclosure_status'], '需复核')
        self.assertEqual(top['hedge_accounting_status'], '需复核')

    def test_attributed_oci_survives_total_wording_and_other_clause(self):
        for raw in (
            '现金流量套期产生的其他综合收益的税后净额为100万元。',
            '现金流量套期储备为100万元；外币财务报表折算差额为200万元。',
        ):
            _, metrics = normalize({'disclosure_status': '有数值', 'metrics': [{
                'metric_type': 'oci_amount', 'value': 100, 'unit': '万元',
                'page': 144, 'raw': raw,
            }]}, '【P144】' + raw)
            self.assertEqual(len(metrics), 1)

    def test_unrelated_clause_cannot_authorize_an_oci_amount(self):
        raw = '现金流量套期储备为100万元；其他综合收益的税后净额为200万元。'
        _, metrics = normalize({'disclosure_status': '有数值', 'metrics': [{
            'metric_type': 'oci_amount', 'value': 200, 'unit': '万元',
            'page': 144, 'raw': raw,
        }]}, '【P144】' + raw)
        self.assertEqual(metrics, [])


if __name__=='__main__':
    unittest.main()
