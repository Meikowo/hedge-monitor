import unittest
from scripts.extract_periodic_reports import extract_explicit_pnl_metrics, normalize_summary, normalize


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


if __name__=='__main__':
    unittest.main()
