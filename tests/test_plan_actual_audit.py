import importlib
import unittest


def audit():
    try:
        return importlib.import_module('scripts.audit_plan_actual')
    except ModuleNotFoundError as exc:
        raise AssertionError('M5 real-data audit adapter is missing') from exc


class AuditAdapterTest(unittest.TestCase):
    def payload(self):
        return {'reports':[{'report_id':'r1','code':'000001','name':'甲公司',
                 'report_type':'annual','fiscal_year':2025,'period_end':'2025-12-31','status':'extracted'}],
                'profiles':[{'report_id':'r1','scopes':['商品','外汇'],
                             'underlyings':['铜','美元'],'instruments':['期货','远期']}],
                'metrics':[], 'plans':[]}

    def test_multiscope_profile_not_copied_and_no_venue_guess(self):
        rows = audit().build_audit(self.payload())
        self.assertEqual(len(rows),2)
        self.assertTrue(all(row['underlyings']['actual_raw']==[] for row in rows))
        self.assertTrue(all(row['venue']['status']=='insufficient_evidence' for row in rows))
        self.assertTrue(all(row['status']=='needs_review' for row in rows))

    def test_missing_unprocessed_and_future_plan_not_misrepresented(self):
        data=self.payload()
        data['reports'][0]['status']='failed'
        rows=audit().build_audit(data)
        self.assertEqual(rows[0]['status'],'unprocessed')
        data=self.payload()
        data['plans']=[{'code':'000001','ann_id':'future','ann_date':'2026-04-01','scope':'商品',
                        'ann_role':'计划-董事会','underlyings':['铜']}]
        self.assertTrue(all(not row['plans'] for row in audit().build_audit(data)))

    def test_html_escapes_source_text(self):
        data=self.payload()
        data['reports'][0]['name']='<script>alert(1)</script>'
        html=audit().render_audit(audit().build_audit(data))
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)


if __name__ == '__main__':
    unittest.main()
