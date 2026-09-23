import unittest
from unittest.mock import patch
from scripts.fetch_periodic_reports import is_target_title
import scripts.fetch_periodic_reports as fetch
from scripts.locate_periodic_pages import build_report_query


class PeriodicTitleGuardTest(unittest.TestCase):
    def test_english_and_short_reports_cannot_replace_chinese_full_report(self):
        for title in ['2025年年度报告（英文）', '公司2025年年度报告(英文)',
                      '关于2025年年度报告（英文简版）的自愿性披露公告',
                      '2025年年度报告（简版）', '2025年年度报告（English Version）']:
            with self.subTest(title=title):
                self.assertFalse(is_target_title(title, 2025, 'annual'))

    def test_full_chinese_revisions_still_qualify(self):
        for title in ['2025年年度报告', '公司2025年度报告（修订版）',
                      '公司2025年年度报告（更正后）']:
            self.assertTrue(is_target_title(title, 2025, 'annual'))
        self.assertTrue(is_target_title('2026年半年度报告（修订版）', 2026, 'semiannual'))
        self.assertFalse(is_target_title('2026年半年度报告（英文）', 2026, 'semiannual'))

    def test_separator_titles_are_full_reports_not_summaries(self):
        for title in ['600498_2025年_年度报告', '688205_德科立_2025_年度报告', '2025 年 年度报告']:
            self.assertTrue(is_target_title(title, 2025, 'annual'))
        self.assertFalse(is_target_title('600498_2025年_年度报告摘要', 2025, 'annual'))

    def test_bse_alias_requires_same_official_org_and_unique_old_pool_code(self):
        mapping = {'831627':'org1','920627':'org1','832000':'org2',
                   '920000':'org3','000550':'org4','200550':'org4'}
        build = getattr(fetch, 'build_report_code_aliases', None)
        self.assertIsNotNone(build, 'Verified old/new code mapping is missing')
        self.assertEqual(build({'831627':{},'832000':{},'200550':{}}, mapping), {'920627':'831627'})
        self.assertEqual(build({'831627':{},'920627':{}}, mapping), {})
        mapping['831999'] = 'org1'
        self.assertEqual(build({'831627':{},'831999':{}}, mapping), {})

    def test_explicit_locator_ids_not_silently_limited(self):
        query = build_report_query({}, 2, ['1225026136','1225066678','1225265197'])
        self.assertNotIn('limit', query)
        self.assertIn('1225026136', query['report_id'])

    def test_only_code_cannot_change_pool_identity_or_hide_alias_ambiguity(self):
        raw = {'announcementId':'1225093703','secCode':'920627','secName':'力王股份',
               'announcementTitle':'2025年年度报告','announcementTime':1775779200000,
               'adjunctUrl':'finalpage/2026-04-10/1225093703.PDF'}
        for pool in ({'831627':{},'920627':{}}, {'831627':{},'831999':{}}):
            for strategy in ('full', 'targeted'):
                with self.subTest(pool=pool,strategy=strategy), \
                     patch.object(fetch, 'load_sample', return_value=pool), \
                     patch.object(fetch.cninfo, 'stock_org_map', return_value={
                         '831627':'same-org','831999':'same-org','920627':'same-org'}), \
                     patch.object(fetch.cninfo, 'iter_query', return_value=iter([raw])), \
                     patch.object(fetch, 'iter_full_market_reports', return_value=iter([raw])), \
                     patch.object(fetch.cninfo, 'polite_sleep'), \
                     patch.object(fetch, 'snapshot_csv') as snapshot, \
                     patch('sys.argv', ['fetch','--only-code','831627','--strategy',strategy]):
                    fetch.main()
                    self.assertEqual(snapshot.call_args.args[1], [])
