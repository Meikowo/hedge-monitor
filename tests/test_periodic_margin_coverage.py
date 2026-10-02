import unittest

from scripts.periodic_pdf import build_marked_text, parse_derivative_note_table, select_candidate_pages
from scripts.extract_periodic_reports import normalize, normalize_accounting_items, promote_verified_accounting_evidence
import scripts.periodic_pdf as pdf


class MarginCoverageTests(unittest.TestCase):
    def test_policy_reference_is_not_actual_accounting_application(self):
        quote = '公司根据企业会计准则第24号—套期会计，对拟开展的外汇套期保值业务进行相应的核算处理。'
        raw = {'hedge_accounting_status':'已应用','hedge_accounting_types':['现金流量套期'],
               'hedge_accounting_evidence':{'page':24,'quote':quote},
               'hedge_accounting_items':[{'application_status':'已应用','accounting_type':'现金流量套期','page':24,'quote':quote}]}
        top,_=normalize(raw,'【P24】'+quote)
        self.assertEqual(top['hedge_accounting_status'],'未明确披露')
        self.assertEqual(top['hedge_accounting_types'],[])
        self.assertEqual(normalize_accounting_items(raw,'【P24】'+quote),[])

    def test_placeholder_text_and_uncertain_types_are_not_published(self):
        top,_=normalize({'purpose':'原文明确目的','non_application_reason':'原文明示原因',
                         'hedge_accounting_status':'需复核','hedge_accounting_types':['现金流量套期']},'')
        self.assertIsNone(top['purpose'])
        self.assertIsNone(top['non_application_reason'])
        self.assertEqual(top['hedge_accounting_types'],[])

    def test_scope_accounting_reason_does_not_overwrite_report_evidence(self):
        top={'hedge_accounting_status':'未应用','hedge_accounting_quote':'公司全部未应用',
             'hedge_accounting_page':210,'non_application_reason':None}
        promote_verified_accounting_evidence(top,[{'application_status':'未应用','scope':'外汇',
             'quote_verified':True,'quote':'外汇业务期限较短未应用','page':211,'non_application_reason':'期限较短'}])
        self.assertIsNone(top['non_application_reason'])
        self.assertEqual(top['hedge_accounting_page'],210)

    def test_mixed_asset_liability_quote_does_not_verify_column(self):
        quote='衍生金融资产和衍生金融负债 资产小计 100 负债小计 200'
        _,metrics=normalize({'metrics':[{'metric_type':'derivative_liability_fv','value':100,
                                  'unit':'元','page':1,'raw':quote}]},'【P1】'+quote)
        self.assertEqual(metrics,[])

    def test_unruled_blank_current_and_footer_are_not_values(self):
        text = ('衍生金融资产和衍生金融负债\n2026年6月30日\n2025年12月31日\n'
                '衍生金融资产-\n小计\n100\n80\n'
                '衍生金融负债-\n小计\n\n160\n130')
        self.assertFalse(any(m['metric_type'] == 'derivative_liability_fv'
                             for m in pdf.parse_unruled_derivative_balances(text,130,'千元')))

    def test_unruled_local_unit_overrides_global_and_additive_layout_is_rejected(self):
        text = ('衍生金融资产和衍生金融负债\n单位：万元\n2026年6月30日\n2025年12月31日\n'
                '衍生金融资产-\n小计\n100\n80\n减：一年以上到期的衍生金融资产\n20\n10\n合计\n80\n70\n'
                '衍生金融负债-\n小计\n200\n160\n减：一年以上到期的衍生金融负债\n20\n10\n合计\n180\n150')
        self.assertEqual([m['unit'] for m in pdf.parse_unruled_derivative_balances(text,130,'千元')],['万元','万元'])
        self.assertEqual(pdf.parse_unruled_derivative_balances(text.replace('减：','加：'),130,'千元'),[])

    def test_counterparty_header_variants_are_not_margin_totals(self):
        for header in ('债务人名称','往来单位','公司名称','单位名称'):
            rows = [[header,'款项性质','期末余额','账龄'],['银河期货有限公司','期货合约保证金','49727436.80','一年以内']]
            self.assertEqual(parse_derivative_note_table(rows,201,'元'),[],header)

    def test_margin_repetition_does_not_evict_investment_and_pnl(self):
        pages = ['期货合约保证金 期末余额 100'] * 15 + ['衍生品投资类型 本期公允价值变动损益', '报告期实际损益情况']
        selected = select_candidate_pages(pages)[0]
        self.assertTrue({16,17}.issubset(selected))

    def test_selected_unit_page_keeps_declaration_after_focusing(self):
        declaration = '(除特别注明外，金额单位为人民币千元)'
        pages = ['财务报表附注\n'+declaration+'\n公司基本情况'*2000+'\n衍生金融资产'] + ['衍生金融资产']*14
        self.assertIn(declaration,build_marked_text(pages,list(range(1,16)),['衍生金融资产']))

    def test_unruled_notes_use_subtotal_including_noncurrent_liability(self):
        text = ('衍生金融资产和衍生金融负债\n2026 年\n6 月30 日\n2025 年\n12 月31 日\n'
                '衍生金融资产-\n外汇远期合约\n22,240\n1,849\n小计\n23,676\n1,872\n'
                '减：一年以上到期的衍生金融资产\n-\n(23)\n合计\n23,676\n1,849\n'
                '衍生金融负债-\n外汇远期合约\n53,617\n4,325\n小计\n71,663\n6,805\n'
                '减：一年以上到期的衍生金融负债\n(3,254)\n(20)\n合计\n68,409\n6,785')
        parse = getattr(pdf, 'parse_unruled_derivative_balances', lambda *a: [])
        facts = parse(text, 130, '千元')
        self.assertEqual([(m['metric_type'],m['value'],m['unit']) for m in facts],
                         [('derivative_asset_fv',23676.0,'千元'),('derivative_liability_fv',71663.0,'千元')])
        self.assertEqual(parse(text,130,None), [])
        self.assertEqual(parse(text.replace('2026 年','2024 年'),130,'千元'), [])

    def test_unrelated_top_five_section_does_not_hide_margin_total(self):
        pages = ['套期保值 衍生品投资 投资收益 公允价值变动收益' * 8] * 20
        pages[16] = ('预付款期末余额前五名 其他应收款按款项性质分类 '
                     '款项性质 期末账面余额 年初账面余额 期货合约保证金 152,715,068.10 116,653,692.30')
        pages[7] = '其他应收款 保证金 ' * 20
        self.assertIn(17, select_candidate_pages(pages)[0])

    def test_counterparty_margin_does_not_become_report_total(self):
        rows = [['单位名称', '款项性质', '期末余额', '账龄'],
                ['银河期货有限公司', '期货合约保证金', '49,727,436.80', '一年以内']]
        self.assertEqual(parse_derivative_note_table(rows, 201, '元'), [])

    def test_investment_balance_is_not_classified_as_derivative_liability(self):
        raw = {'metrics': [{'metric_type':'derivative_liability_fv', 'value':24456135,
                            'unit':'元', 'page':27, 'raw':'期货 24,456,135.00',
                            'source_section':'以公允价值计量的金融资产'}]}
        self.assertEqual(normalize(raw, '【P27】期货 24,456,135.00')[1], [])

    def test_selected_notes_retain_report_wide_unit_declaration(self):
        pages = ['财务报表附注\n2026年1-6月\n(除特别注明外，金额单位为人民币千元)',
                 '公司基本情况',
                 '衍生金融资产和衍生金融负债\n衍生金融资产 小计 23,676 1,872']
        marked = build_marked_text(pages, [3], ['衍生金融资产'])
        self.assertIn('【P1】', marked)
        self.assertIn('除特别注明外，金额单位为人民币千元', marked)
        self.assertIn('【P3】', marked)

    def test_actual_margin_note_beats_repeated_counterparty_mentions(self):
        pages = ['套期保值 衍生品投资 投资收益 公允价值变动收益' * 8] * 20
        pages[4] = '款项性质 期末账面余额 年初账面余额 期货合约保证金 152,715,068.10 116,653,692.30'
        pages[15] = '其他应收款 前五名 ' + '期货合约保证金 ' * 20
        selected, _, _ = select_candidate_pages(pages)
        self.assertIn(5, selected)

    def test_narrative_period_end_margin_is_selected(self):
        pages = ['套期保值 衍生品投资 投资收益 公允价值变动收益' * 8] * 20
        pages[16] = '截至报告期末主要资产受限情况 其他应收款中期货保证金占用157,839,376.89元。'
        pages[7] = '其他应收款 保证金 ' * 20
        selected, _, _ = select_candidate_pages(pages)
        self.assertIn(17, selected)

    def test_margin_cash_flow_is_not_a_period_end_balance(self):
        rows = [['项目', '本期发生额', '上期发生额'], ['期货合约保证金', '36,061,375.80', '9,768,503.77']]
        self.assertEqual(parse_derivative_note_table(rows, 234, '元'), [])

    def test_margin_balance_uses_current_column_not_fixed_column(self):
        rows = [['款项性质', '年初账面余额', '期末账面余额'], ['期货合约保证金', '116,653,692.30', '152,715,068.10']]
        facts = parse_derivative_note_table(rows, 198, '元')
        self.assertEqual([m['value'] for m in facts], [152715068.10])

    def test_restricted_futures_margin_blank_does_not_take_other_margin(self):
        rows = [['项目', '期末余额', '期初余额', '理由'],
                ['其他货币资金', '', '81,544,987.42', '使用权受限的期货保证金'],
                [None, '98,148,585.71', '22,783,295.44', '使用权受限的其他保证金']]
        self.assertEqual(parse_derivative_note_table(rows, 175, '元'), [])

    def test_restricted_futures_margin_reads_reason_column(self):
        rows = [['项目', '期末余额', '期初余额', '理由'],
                ['其他货币资金', '100.00', '81.00', '使用权受限的期货保证金']]
        facts = parse_derivative_note_table(rows, 175, '元')
        self.assertEqual([(m['metric_type'], m['value']) for m in facts], [('margin_end_cash', 100.0)])


if __name__ == '__main__':
    unittest.main()
