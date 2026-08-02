import unittest
from unittest.mock import patch

from scripts import build_events


def plan_announcement(ann_id, ann_date, role, scopes):
    return {
        "ann_id": ann_id,
        "code": "300438",
        "name": "鹏辉能源",
        "ann_date": ann_date,
        "ext": {
            "is_hedge_related": True,
            "ann_role": role,
            "scope": scopes,
            "instruments": ["期货"] if scopes else [],
            "underlyings": ["铜"] if scopes else [],
            "venue": "境内外" if scopes else "未披露",
            "approval_level": "股东大会" if role == "计划-股东大会" else "董事会及股东大会",
            "plan_label": "2026年套期保值计划",
            "period_text": "至2026年年度股东会召开之日",
            "is_revolving": True,
            "use_own_funds": True,
        },
    }


class EventQuotaSourceTest(unittest.TestCase):
    def test_approved_resolution_without_amount_uses_latest_quota_bearing_plan(self):
        board = plan_announcement("board-adjustment", "2026-07-09", "计划-董事会", ["商品", "外汇"])
        shareholder = plan_announcement("shareholder-resolution", "2026-07-24", "计划-股东大会", [])
        shareholder["ext"]["period_text"] = None
        events = build_events.group([board, shareholder])
        quota = {
            "scope": "商品",
            "basis": "保证金占用",
            "amount": 300000000,
            "currency": "CNY",
            "raw_text": "商品套期保值保证金上限调整为人民币3亿元",
            "page": 1,
            "amount_verified": True,
            "quote_verified": True,
        }

        def fake_fetch_quotas(ann_ids):
            rows = {"board-adjustment": [quota], "shareholder-resolution": []}
            return {ann_id: rows[ann_id] for ann_id in ann_ids if rows.get(ann_id)}

        with patch.object(build_events, "fetch_quotas", side_effect=fake_fetch_quotas):
            event_rows, _ = build_events.build_rows(events)

        self.assertEqual(len(event_rows), 1)
        self.assertEqual(event_rows[0]["stage"], "股东大会通过")
        self.assertEqual(event_rows[0]["quota_source_ann_id"], "board-adjustment")
        self.assertEqual(event_rows[0]["quota"], [quota])
        self.assertEqual(event_rows[0]["period_text"], "至2026年年度股东会召开之日")

    def test_quota_projection_keeps_page_and_quote_verification(self):
        database_row = {
            "ann_id": "board-adjustment",
            "scope": "外汇",
            "basis": "合约价值",
            "amount": 3000000000,
            "currency": "CNY",
            "raw_text": "外汇最高合约价值不超过人民币30亿元",
            "page": 2,
            "amount_verified": True,
            "quote_verified": True,
        }

        def fake_select(table, params, paginate=False):
            self.assertEqual(table, "quota_items")
            selected = params["select"].split(",")
            return [{key: database_row[key] for key in selected}]

        with patch.object(build_events, "sb_select", side_effect=fake_select):
            result = build_events.fetch_quotas(["board-adjustment"])

        self.assertEqual(result["board-adjustment"][0]["page"], 2)
        self.assertTrue(result["board-adjustment"][0]["quote_verified"])

    def test_empty_amount_row_does_not_hide_an_earlier_verified_amount(self):
        board = plan_announcement("board-with-amount", "2026-06-01", "计划-董事会", ["外汇"])
        shareholder = plan_announcement("shareholder-with-empty-row", "2026-06-20", "计划-股东大会", [])
        events = build_events.group([board, shareholder])
        rows = {
            "board-with-amount": [{
                "scope": "外汇", "basis": "合约价值", "amount": 100000000,
                "currency": "CNY", "raw_text": "外汇合约价值上限1亿元", "page": 1,
                "amount_verified": True, "quote_verified": True,
            }],
            "shareholder-with-empty-row": [{
                "scope": "综合", "basis": "未披露", "amount": None,
                "currency": "未披露", "raw_text": "审议通过套期保值议案", "page": 1,
                "amount_verified": False, "quote_verified": True,
            }],
        }

        with patch.object(build_events, "fetch_quotas", return_value=rows):
            event_rows, _ = build_events.build_rows(events)

        self.assertEqual(event_rows[0]["quota_source_ann_id"], "board-with-amount")
        self.assertEqual(event_rows[0]["quota"][0]["amount"], 100000000)


if __name__ == "__main__":
    unittest.main()
