import unittest
from unittest.mock import patch
from types import SimpleNamespace
from scripts.periodic_pdf import parse_derivative_note_table, extract_derivative_note_metrics
from scripts.extract_periodic_reports import merge_verified_note_metrics
from scripts import extract_periodic_reports as extraction

class NoteAlignmentTests(unittest.TestCase):
    def test_extraction_pipeline_does_not_reintroduce_rejected_prior_amount(self):
        label='其中：衍生金融工具产生的公允价值变动收益'
        body=f'【P105】产生公允价值变动收益的来源 本期发生额 上期发生额\n{label} -81,668.91'
        candidate=dict(metric_type='derivative_fv_change_pnl',page=105,account_name=None,
                       raw=f'{label} -81,668.91',value=-81668.91,unit='元',currency='CNY')
        def notes(content,pages,*,rejected_keys):
            return parse_derivative_note_table([['产生公允价值变动收益的来源','本期发生额','上期发生额'],
                [label,'','-81,668.91']],105,'元',rejected_keys=rejected_keys)
        report=dict(report_id='r',code='600987',name='航民',title='半年报',report_period='2026H1',pdf_url='unused')
        with patch.object(extraction.cninfo,'download_pdf',return_value=b'pdf'), \
             patch.object(extraction,'locate_pdf',return_value=SimpleNamespace(marked_text=body,candidate_pages=[105])), \
             patch.object(extraction,'call_periodic_llm',return_value={'metrics':[candidate]}), \
             patch.object(extraction,'extract_derivative_table_metrics',return_value=([],set())), \
             patch.object(extraction,'extract_derivative_note_metrics',side_effect=notes):
            result=extraction.extract_one_report(report,['pnl'],False,True)
        self.assertEqual(result['metrics'],[])

    def test_missing_model_account_still_rejects_source_row_prior_value(self):
        rejected=[]
        label='其中：衍生金融工具产生的公允价值变动收益'
        facts=parse_derivative_note_table([['产生公允价值变动收益的来源','本期发生额','上期发生额'],
                                          [label,'','-81668.91']],105,'元',rejected_keys=rejected)
        for account in [None,'衍生金融工具']:
            candidate=dict(metric_type='derivative_fv_change_pnl',page=105,account_name=account,
                           raw=f'{label} -81668.91',value=-81668.91)
            self.assertEqual(merge_verified_note_metrics({'metrics':[candidate]},facts,['pnl'],rejected_keys=rejected)['metrics'],[])

    def test_spacer_column_does_not_blacklist_current_amount(self):
        rejected=[]
        facts=parse_derivative_note_table([['产生公允价值变动收益的来源',None,'本期发生额','上期发生额'],
            ['其中：衍生金融工具产生的公允价值变动收益',None,'100','90']],1,'元',rejected_keys=rejected)
        self.assertEqual([(x['metric_type'],x['value']) for x in facts],[('derivative_fv_change_pnl',100)])
        self.assertEqual(rejected,[])

    def test_three_row_oci_header_is_assembled_by_column(self):
        rejected=[]
        rows=[['项目','期初余额','本期发生额',None,'期末余额'],
              [None,None,'本期所得税前','减：前期计入其他综合收益',None],
              [None,None,'发生额','当期转入损益',None],
              ['现金流量套期储备','10','30','40','50']]
        facts=parse_derivative_note_table(rows,1,'元',rejected_keys=rejected)
        self.assertEqual([(x['metric_type'],x['value']) for x in facts],[('oci_amount',30),('reclassification_amount',40)])
        self.assertEqual(rejected,[])

    def test_independent_table_is_not_a_fair_value_continuation(self):
        class Page:
            def __init__(self,unit,rows):self.unit,self.rows=unit,rows
            def get_text(self,kind=None):return [(0,50,500,60,'单位：'+self.unit)] if kind=='blocks' else '单位：'+self.unit
            def find_tables(self):return SimpleNamespace(tables=[SimpleNamespace(bbox=(0,100,500,200),extract=lambda:self.rows)])
        class Doc(list):
            def close(self):pass
        pages=[Page('元',[['项目','期末公允价值',None,None,'合计'],[None,'第一层次','第二层次','第三层次','合计']]),
               Page('万元',[['项目','期初余额','本期增加','本期减少','期末余额'],['衍生金融负债','1','2','1','2']])]
        with patch('scripts.periodic_pdf.fitz.open',return_value=Doc(pages)):
            facts=extract_derivative_note_metrics(b'pdf',[1,2])
        # This is not a fair-value hierarchy table. Do not reinterpret it.
        self.assertEqual(facts,[])

    def test_tax_after_column_is_not_reclassification(self):
        rows=[['项目','期初余额','本期发生金额',None,'期末余额'],
              [None,None,'本期所得税前发生额','税后归属于母公司',None],
              ['现金流量套期储备','-515600','-834330','-834330','-1349930']]
        facts=parse_derivative_note_table(rows,118,'元')
        self.assertEqual([(x['metric_type'],x['value']) for x in facts],[('oci_amount',-834330)])

    def test_reordered_oci_columns_follow_headers(self):
        rows=[['项目','期初余额','税后归属于母公司','本期所得税前发生额','减：前期计入其他综合收益当期转入损益','期末余额'],
              ['现金流量套期储备','10','20','30','40','50']]
        self.assertEqual([(x['metric_type'],x['value']) for x in parse_derivative_note_table(rows,1,'元')],
                         [('oci_amount',30),('reclassification_amount',40)])

    def test_generic_liability_total_does_not_fill_blank_derivative_row(self):
        rows=[['项目','期末公允价值',None,None,'合计'],
              ['交易性金融负债','','','',''],
              ['1.以公允价值计量且其变动计入当期损益的金融负债','1991058960','','','1991058960'],
              ['衍生金融负债','','','',''],['其他','','','',''],
              ['持续以公允价值计量的负债总额','1991058960','','','1991058960']]
        self.assertEqual(parse_derivative_note_table(rows,121,'元'),[])

    def test_continuation_keeps_unit_from_its_header_page(self):
        class Page:
            def __init__(self,text,blocks,rows):self.text,self.blocks,self.rows=text,blocks,rows
            def get_text(self,kind=None):return self.blocks if kind=='blocks' else self.text
            def find_tables(self):return SimpleNamespace(tables=[SimpleNamespace(bbox=(0,100,500,200),extract=lambda:self.rows)])
        pages=[Page('单位：元',[ (0,50,500,60,'单位：元') ],[['项目','期末公允价值',None,None,'合计'],[None,'第一层次','第二层次','第三层次','合计']]),
               Page('衍生金融负债\n1,431,930.00\n关联方注册资本\n单位：万元',[(0,400,500,420,'单位：万元')],
                    [['（三）衍生金融负债','1,431,930.00','','','1,431,930.00']])]
        class Doc(list):
            def close(self):pass
        with patch('scripts.periodic_pdf.fitz.open',return_value=Doc(pages)):
            facts=extract_derivative_note_metrics(b'pdf',[1,2])
        self.assertEqual([(x['value'],x['unit']) for x in facts],[(1431930,'元')])

    def test_blank_current_cell_blocks_model_prior_value(self):
        rejected=[]
        facts=parse_derivative_note_table([
            ['产生公允价值变动收益的来源','本期发生额','上期发生额'],
            ['其中：衍生金融工具产生的公允价值变动收益','','-81668.91'],
        ],105,'元',rejected_keys=rejected)
        candidate={'metric_type':'derivative_fv_change_pnl','page':105,'account_name':'其中：衍生金融工具产生的公允价值变动收益','value':-81668.91}
        other={**candidate,'page':106}
        merged=merge_verified_note_metrics({'metrics':[candidate,other]},facts,['pnl'],rejected_keys=rejected)
        self.assertEqual(merged['metrics'],[other])
