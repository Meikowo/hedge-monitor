import unittest
from scripts.periodic_pdf import merge_derivative_continuation, parse_derivative_investment_table

HEADER=['衍生品投资类型','初始投资金额','期初金额','本期公允价值变动损益','计入权益的累计公允价值变动','报告期内购入金额','报告期内售出金额','期末金额','期末投资金额占公司报告期末净资产比例']

class SplitHeadersTests(unittest.TestCase):
    def test_equal_width_ghost_columns_can_move_between_header_and_data(self):
        header=[]
        for h in HEADER: header.extend([h,None])
        row=['外汇期权',None,None,'0','0','1','2','3','4','5','6%']+[None]*7
        facts=parse_derivative_investment_table([header,row],1,'万元')
        self.assertEqual([m['value'] for m in facts],[1,2,3,4,5,6])

    def test_fragmented_header_preserves_known_cells_in_blank_row(self):
        header=HEADER.copy(); header[1]='初始投资'
        rows=[header,['','金额','','','','','','',''],
              ['外汇远期','0','0','1','2','3','4','5','6%'],
              ['商品期货','0','0',None,'2','3','4','5','6%']]
        facts=parse_derivative_investment_table(rows,1,'万元')
        commodity=[m for m in facts if m['scope']=='商品']
        self.assertEqual(len(commodity),5)
        self.assertTrue(any(m['metric_type']=='ending_balance' and m['value']==5 for m in commodity))

    def test_generic_option_is_not_fx_with_commodity_option_sibling(self):
        rows=[HEADER,*[[label,'0','0','1','2','3','4','5','6%']
                      for label in ['期权组合','外汇期权','黄金期权']]]
        facts=parse_derivative_investment_table(rows,1,'万元')
        self.assertTrue(all(m['scope']!='外汇' for m in facts if m['account_name']=='期权组合'))

    def test_incomplete_commodity_sibling_prevents_fx_override(self):
        header=HEADER.copy(); header[1]='初始投资'
        rows=[header,['','金额','','','','','','',''],
              ['期权组合','0','0','1','2','3','4','5','6%'],
              ['外汇期权','0','0','1','2','3','4','5','6%'],
              ['商品期货','0','0',None,'2','3','4','5','6%']]
        facts=parse_derivative_investment_table(rows,1,'万元')
        self.assertTrue(all(m['scope']!='外汇' for m in facts if m['account_name']=='期权组合'))

    def test_standard_table_keeps_known_cells_in_partially_blank_rows(self):
        rows=[HEADER,['外汇远期','0','0','1','2','3','4','5','6%'],
              ['商品期货','0','0',None,'20','30','40','50','60%']]
        facts=parse_derivative_investment_table(rows,1,'万元')
        self.assertTrue(any(m['scope']=='商品' and m['metric_type']=='ending_balance' and m['value']==50 for m in facts))
    def test_multiline_header_fragments_keep_their_column(self):
        # Vertically fragmented words; null ghost columns must not shift values.
        rows=[['衍生品投资类',None,'初始投资',None,'期初金额',None,'本期公允',None,'计入权益的累计',None,'报告期内',None,'报告期内',None,'期末金额',None,'期末投资金额占公司报告期末净资产'],
              ['型',None,'金额',None,None,None,'价值变动损益',None,'公允价值变动',None,'购入金额',None,'售出金额',None,None,None,'比例'],
              ['外汇期权',None,'0',None,'0',None,'2.34',None,'0',None,'690.01',None,'692.35',None,'0',None,'0.00%']]
        facts=parse_derivative_investment_table(rows,23,'万元')
        self.assertEqual([(m['metric_type'],m['value']) for m in facts],[
            ('derivative_fv_change_pnl',2.34),('oci_amount',0),('period_purchase_amount',690.01),
            ('period_sale_amount',692.35),('ending_balance',0),('net_asset_ratio',0)])

    def test_split_page_header_can_join_different_physical_widths(self):
        prior=[[ *HEADER[:4],HEADER[4][:-1],*HEADER[5:8],'','期末投资',''],
               [None]*9+['金额占公司报告期末净资产',None]]
        data=[['',None,None,'','','','动','','比例'],
              ['远期结汇',None,None,'7868.36','8002.27','281.58','426.93',None,None,'8918.35','15348.19','2280.94','0.35%',None,None]]
        combined=merge_derivative_continuation(data,prior_header_rows=prior,prior_page=16,page=17,table_top=72)
        facts=parse_derivative_investment_table(combined,17,'万元')
        self.assertEqual([m['value'] for m in facts],[281.58,426.93,8918.35,15348.19,2280.94,0.35])
        self.assertTrue(all(m['page']==17 and m['scope']=='外汇' for m in facts))
        data[1][6]=None  # A genuinely blank amount must not shift following columns.
        combined=merge_derivative_continuation(data,prior_header_rows=prior,prior_page=16,page=17,table_top=72)
        self.assertEqual(parse_derivative_investment_table(combined,17,'万元'),[])

    def test_generic_option_uses_unambiguous_sibling_fx_scope(self):
        rows=[HEADER,['期权组合','0','0','2.34','0','690.01','692.35','0','0%'],
              ['外汇掉期、期权组合','0','0','46.58','0','700','4152.25','3405.67','1.07%']]
        facts=parse_derivative_investment_table(rows,23,'万元')
        self.assertEqual({m['scope'] for m in facts},{'外汇'})

    def test_nonadjacent_or_new_table_never_inherits_split_header(self):
        prior=[HEADER]
        data=[['资金来源','初始投资金额','期初金额','本期公允价值变动损益','计入权益的累计公允价值变动','报告期内购入金额','报告期内售出金额','期末金额','比例'],['期货公司借款','1','2','3','4','5','6','7','8']]
        self.assertIs(merge_derivative_continuation(data,prior_header_rows=prior,prior_page=16,page=18,table_top=72),data)

if __name__=='__main__':unittest.main()
