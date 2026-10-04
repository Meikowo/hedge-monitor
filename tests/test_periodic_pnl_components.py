import unittest
from scripts.extract_periodic_reports import normalize, normalize_accounting_items


class PnlComponentTests(unittest.TestCase):
    def test_actual_nonnumeric_business_conflict_is_preserved(self):
        quote='公司报告期已开展远期结售汇业务，以美元远期合约规避汇率风险。'
        body='【P1】公司报告期不存在衍生品投资。\n【P2】'+quote
        raw={'disclosure_status':'提及无数值','scopes':['外汇'],'instruments':['远期结售汇'],
             'evidence':[{'field':'scopes','page':2,'quote':quote}]}
        top,_=normalize(raw,body)
        self.assertEqual(top['disclosure_status'],'需复核')
        self.assertEqual(top['scopes'],['外汇'])
        self.assertEqual(top['evidence'],raw['evidence'])
        self.assertEqual(normalize_accounting_items(raw,body)[0]['application_status'],'需复核')

    def test_coordinated_label_is_not_a_component_suffix(self):
        quote='期货本期投资收益与公允价值变动损益100元，其中公允价值变动损益40元，处置收益60元。'
        _,ms=normalize({'metrics':[self.metric(100,quote)]},'【P1】'+quote)
        self.assertEqual(ms[0]['metric_type'],'reported_derivative_comprehensive_pnl')

    def test_unrelated_expense_total_does_not_override_component(self):
        quote='期货公允价值变动损益100元，处置损益50元；管理费用合计100元。'
        _,ms=normalize({'metrics':[self.metric(100,quote)]},'【P1】'+quote)
        self.assertEqual(ms[0]['metric_type'],'derivative_fv_change_pnl')

    def test_signed_component_spellings(self):
        for value,text in [(-100,'损益（100）'),(-100,'损失100'),(100,'损益+100')]:
            quote=f'期货公允价值变动{text}元，处置损益50元。'
            with self.subTest(text=text):
                _,ms=normalize({'metrics':[self.metric(value,quote)]},'【P1】'+quote)
                self.assertEqual(ms[0]['metric_type'],'derivative_fv_change_pnl')

    def test_non_derivative_or_forecast_component_is_not_promoted(self):
        for quote in ['处置固定资产的处置收益100元。','预计期货公允价值变动损益100元。']:
            with self.subTest(quote=quote):
                _,ms=normalize({'metrics':[self.metric(100,quote)]},'【P1】'+quote)
                self.assertEqual(ms,[])

    def metric(self, value, quote):
        return {'metric_type':'reported_derivative_comprehensive_pnl', 'value':value,
                'unit':'元','currency':'CNY','page':1,'raw':quote,'scope':'商品',
                'fact_level':'scope','source_section':'衍生品投资情况',
                'account_name':'模型声称合计'}

    def test_separately_disclosed_components_are_not_combined_pnl(self):
        quote='期货本期公允价值变动损益8,348,650.00元，处置损益-13,417,074.51元。'
        _, metrics=normalize({'metrics':[self.metric(8348650,quote),self.metric(-13417074.51,quote)]},'【P1】'+quote)
        self.assertEqual([m['metric_type'] for m in metrics],['derivative_fv_change_pnl','derivative_disposal_investment_income'])

    def test_actual_combined_total_stays_combined(self):
        quote='期货公允价值变动损益100元，处置损益-200元，合计-100元。'
        _,metrics=normalize({'metrics':[self.metric(-100,quote)]},'【P1】'+quote)
        self.assertEqual(metrics[0]['metric_type'],'reported_derivative_comprehensive_pnl')

    def test_equal_component_values_are_ambiguous_not_a_combined_total(self):
        quote='期货公允价值变动损益100元，处置损益100元。'
        _,metrics=normalize({'metrics':[self.metric(100,quote)]},'【P1】'+quote)
        self.assertEqual(metrics,[])

    def test_no_current_investment_clears_future_instruments(self):
        body='【P1】公司报告期不存在衍生品投资。公司将根据实际情况开展远期结售汇业务。'
        top,_=normalize({'disclosure_status':'提及无数值','scopes':['外汇'],
            'instruments':['远期结售汇'],'underlyings':['美元'],'purpose':'规避汇率风险'},body)
        self.assertEqual(top['scopes'],[])
        self.assertEqual(top['instruments'],[])
        self.assertEqual(top['underlyings'],[])
        self.assertIsNone(top['purpose'])

    def test_conflicting_numeric_evidence_preserves_review_context(self):
        quote='期货本期公允价值变动损益100元。'
        body='【P1】公司报告期不存在衍生品投资。'+quote
        top,metrics=normalize({'scopes':['商品'],'metrics':[self.metric(100,quote)]},body)
        self.assertEqual(top['disclosure_status'],'需复核')
        self.assertEqual(top['scopes'],['商品'])
        self.assertEqual(len(metrics),1)


if __name__=='__main__': unittest.main()
