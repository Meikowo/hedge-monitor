"""FV income rows need both derivative attribution and the current-period column."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from periodic_pdf import parse_derivative_note_table


class FairValueNoteLabelsTest(unittest.TestCase):
    def test_asset_label_under_fv_income_header_is_current_pnl(self):
        rows = [
            ['产生公允价值变动收益的来源', '本期发生额', '上期发生额'],
            ['衍生金融资产', '-3,066,341.04', '108,980.70'],
            ['合计', '-3,066,341.04', '108,980.70'],
        ]
        facts = parse_derivative_note_table(rows, page=161, unit='元')
        self.assertEqual([(x['metric_type'], x['value']) for x in facts],
                         [('derivative_fv_change_pnl', -3066341.04)])

    def test_liability_label_uses_reordered_current_column(self):
        rows = [
            ['产生公允价值变动收益的来源', '上期发生额', '本期发生额'],
            ['衍生金融负债', '12.00', '-3.00'],
        ]
        facts = parse_derivative_note_table(rows, page=2, unit='万元')
        self.assertEqual([(x['metric_type'], x['value']) for x in facts],
                         [('derivative_fv_change_pnl', -3.0)])

    def test_generic_trading_asset_is_not_derivative_pnl(self):
        rows = [
            ['产生公允价值变动收益的来源', '本期发生额', '上期发生额'],
            ['交易性金融资产', '100.00', '20.00'],
        ]
        self.assertEqual(parse_derivative_note_table(rows, page=2, unit='元'), [])

    def test_position_header_does_not_become_pnl(self):
        rows = [['项目', '期末余额', '期初余额'],
                ['衍生金融资产', '100.00', '20.00']]
        self.assertEqual(parse_derivative_note_table(rows, page=2, unit='元'), [])

    def test_blank_current_is_rejected_not_filled_from_prior(self):
        rejected = []
        rows = [
            ['产生公允价值变动收益的来源', '本期发生额', '上期发生额'],
            ['衍生金融资产', None, '108,980.70'],
        ]
        self.assertEqual(parse_derivative_note_table(rows, page=161, unit='元',
                                                    rejected_keys=rejected), [])
        self.assertIn(('derivative_fv_change_pnl', 161, '衍生金融资产'), rejected)


if __name__ == '__main__':
    unittest.main()
