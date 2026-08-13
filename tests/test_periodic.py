import csv
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import scripts.extract_periodic_reports as periodic_extract
import scripts.fetch_periodic_reports as periodic_fetch
import scripts.locate_periodic_pages as periodic_locator
import scripts.select_periodic_poc as periodic_select
import scripts.extract_announcements as announcement_extract
from scripts.extract_periodic_reports import (
    extract_explicit_pnl_metrics,
    merge_verified_note_metrics,
    merge_table_metrics,
    merge_pass_results,
    normalize,
    normalize_accounting_items,
    promote_verified_accounting_evidence,
    should_replace_metric_family,
    should_purge_legacy_metrics,
    verify_raw_value,
)
from scripts.extract_announcements import thinking_extra_body
from scripts.prompt_periodic import (
    METRIC_FAMILIES,
    build_metric_messages,
    build_profile_messages,
)
from scripts.periodic_verification import classify
from scripts.periodic_pdf import (
    MAX_MARKED_CHARS,
    build_marked_text,
    find_parent_company_note_start,
    merge_derivative_continuation,
    parse_derivative_investment_table,
    parse_derivative_note_table,
    select_candidate_pages,
    unit_before_table,
)


class PeriodicNormalizationTest(unittest.TestCase):
    def test_derivative_table_carries_header_to_next_page(self):
        header = [[
            "è¡ç”Ÿå“æŠ•èµ„ç±»å‹", "åˆå§‹æŠ•èµ„é‡‘é¢", "æœŸåˆé‡‘é¢",
            "æœ¬æœŸå…¬å…ä»·å€¼å˜åŠ¨æŸç›Š", "è®¡å…¥æƒç›Šçš„ç´¯è®¡å…¬å…ä»·å€¼å˜åŠ¨",
            "æŠ¥å‘ŠæœŸå†…è´­å…¥é‡‘é¢", "æŠ¥å‘ŠæœŸå†…å”®å‡ºé‡‘é¢", "æœŸæœ«é‡‘é¢",
            "æœŸæœ«æŠ•èµ„é‡‘é¢å å…¬å¸æŠ¥å‘ŠæœŸæœ«å‡€èµ„äº§æ¯”ä¾‹",
        ]]
        continuation = [
            ["åˆ©ç‡æ‰æœŸ", "0", "0", "-204.14", "0", "0", "0", "0", "0.00%"],
            ["åˆè®¡", "0", "0", "-204.14", "0", "0", "0", "0", "0.00%"],
        ]

        rows = merge_derivative_continuation(
            continuation,
            prior_header_rows=header,
            prior_page=33,
            page=34,
            table_top=72,
        )
        metrics = parse_derivative_investment_table(rows, page=34, unit="ä¸‡å…ƒ")

        self.assertEqual({
            item["metric_type"]: item["value"] for item in metrics
        }, {
            "derivative_fv_change_pnl": -204.14,
            "oci_amount": 0.0,
            "period_purchase_amount": 0.0,
            "period_sale_amount": 0.0,
            "ending_balance": 0.0,
            "net_asset_ratio": 0.0,
        })
        self.assertTrue(all(item["scope"] == "åˆ©ç‡" for item in metrics))

    def test_explicit_report_ids_are_not_truncated_by_default_limit(self):
        params = periodic_extract.build_report_query(
            sample="config/annual_priority_2025.csv",
            limit=1,
            report_ids=["1225000001", "1225000002", "1225000003"],
        )

        self.assertEqual(params["report_id"], "in.(1225000001,1225000002,1225000003)")
        self.assertNotIn("limit", params)
        self.assertNotIn("status", params)

    def test_periodic_locator_default_excludes_failed(self):
        params = periodic_locator.build_report_query(
            terms={"000001": []},
            limit=12,
        )

        self.assertEqual(params["status"], "eq.discovered")
        self.assertEqual(params["code"], "in.(000001)")
        self.assertEqual(params["limit"], "12")
        self.assertEqual(params["fiscal_year"], "eq.2025")
        self.assertEqual(params["report_type"], "eq.annual")

    def test_periodic_locator_can_explicitly_retry_failed(self):
        params = periodic_locator.build_report_query(
            terms={"000001": []},
            limit=2,
            retry_failed=True,
        )

        self.assertEqual(params["status"], "in.(discovered,failed)")

    def test_periodic_locator_report_ids_bypass_status_filter(self):
        params = periodic_locator.build_report_query(
            terms={"000001": []},
            limit=2,
            report_ids=["1225000001", "1225000002"],
        )

        self.assertEqual(params["report_id"], "in.(1225000001,1225000002)")
        self.assertNotIn("status", params)
        self.assertNotIn("code", params)

    def test_periodic_queries_can_target_a_different_reporting_period(self):
        locator_params = periodic_locator.build_report_query(
            terms={"000001": []},
            limit=2,
            fiscal_year=2024,
            report_type="semiannual",
        )
        extract_params = periodic_extract.build_report_query(
            sample="config/annual_priority_2025.csv",
            limit=2,
            fiscal_year=2024,
            report_type="semiannual",
        )

        for params in (locator_params, extract_params):
            self.assertEqual(params["fiscal_year"], "eq.2024")
            self.assertEqual(params["report_type"], "eq.semiannual")

    def test_periodic_extraction_is_claimed_before_model_work(self):
        with patch.object(periodic_extract, "sb_update") as mocked:
            periodic_extract.claim_report("r1", dry_run=False)

        mocked.assert_called_once_with(
            "periodic_reports",
            {"report_id": "eq.r1"},
            {
                "status": "failed",
                "note": "æŠ½å–å¤„ç†ä¸­ï¼›å¼‚å¸¸ä¸­æ–­æ—¶éœ€äººå·¥é‡è¯•",
            },
        )

    def test_periodic_selective_run_restores_original_report_state(self):
        with patch.object(periodic_extract, "sb_update") as mocked:
            periodic_extract.restore_report_state(
                {
                    "report_id": "r1",
                    "status": "extracted",
                    "note": "äººå·¥å¤‡æ³¨",
                },
                dry_run=False,
            )

        mocked.assert_called_once_with(
            "periodic_reports",
            {"report_id": "eq.r1"},
            {"status": "extracted", "note": "äººå·¥å¤‡æ³¨"},
        )

    def test_periodic_failure_snapshot_survives_quarantine_note_failure(self):
        report = {"report_id": "r1", "name": "æµ‹è¯•å…¬å¸"}
        with (
            patch.object(periodic_extract, "snapshot_json") as snapshot,
            patch.object(
                periodic_extract,
                "quarantine_report",
                side_effect=RuntimeError("database unavailable"),
            ),
            patch.object(periodic_extract, "warn") as warned,
        ):
            periodic_extract.record_report_failure(
                report,
                [],
                ValueError("model response invalid"),
                dry_run=False,
            )

        snapshot.assert_called_once()
        warned.assert_called_once()

    def test_periodic_locator_is_claimed_before_pdf_work(self):
        with patch.object(periodic_locator, "sb_update") as mocked:
            periodic_locator.claim_report("r1", write=True)

        mocked.assert_called_once_with(
            "periodic_reports",
            {"report_id": "eq.r1"},
            {
                "status": "failed",
                "note": "å®šä½å¤„ç†ä¸­ï¼›å¼‚å¸¸ä¸­æ–­æ—¶éœ€äººå·¥é‡è¯•",
            },
        )

    def test_periodic_extraction_failure_is_quarantined(self):
        with patch.object(periodic_extract, "sb_update") as mocked:
            periodic_extract.quarantine_report(
                "r1",
                RuntimeError("boom"),
                dry_run=False,
            )

        mocked.assert_called_once_with(
            "periodic_reports",
            {"report_id": "eq.r1"},
            {
                "status": "failed",
                "note": "æŠ½å–å¤±è´¥: RuntimeError: boom",
            },
        )

    def test_periodic_dry_run_failure_is_not_written(self):
        with patch.object(periodic_extract, "sb_update") as mocked:
            periodic_extract.quarantine_report(
                "r1",
                RuntimeError("boom"),
                dry_run=True,
            )

        mocked.assert_not_called()

    def test_thinking_off_is_sent_as_explicitly_disabled(self):
        self.assertEqual(
            thinking_extra_body("off"),
            {"thinking": {"type": "disabled"}},
        )
        self.assertEqual(
            thinking_extra_body("on"),
            {"thinking": {"type": "adaptive"}},
        )

    def test_thinking_only_output_is_retryable_but_truncated_json_is_not(self):
        self.assertTrue(hasattr(announcement_extract, "NoJsonObjectError"))
        self.assertTrue(hasattr(announcement_extract, "IncompleteJsonError"))
        with self.assertRaises(announcement_extract.NoJsonObjectError):
            announcement_extract.extract_json_obj("<think>åªæœ‰æ€è€ƒï¼Œæ²¡æœ‰æ­£æ–‡</think>")
        with self.assertRaises(announcement_extract.IncompleteJsonError):
            announcement_extract.extract_json_obj('{"metrics": [')

    def test_periodic_llm_calls_explicitly_disable_thinking(self):
        self.assertTrue(hasattr(periodic_extract, "call_periodic_llm"))
        with patch.object(periodic_extract, "call_llm", return_value={}) as mocked:
            self.assertEqual(periodic_extract.call_periodic_llm([]), {})
        mocked.assert_called_once_with([], thinking_setting="off")

    def test_raw_value_requires_literal_number(self):
        self.assertTrue(verify_raw_value(1234.56, "æœ¬æœŸé‡‘é¢ä¸º1,234.56ä¸‡å…ƒ"))
        self.assertFalse(verify_raw_value(1234.56, "æœ¬æœŸé‡‘é¢çº¦ä¸€åƒä¸‡å…ƒ"))

    def test_raw_value_understands_loss_words_and_accounting_parentheses(self):
        self.assertTrue(verify_raw_value(-11897, "å…¬å…ä»·å€¼å˜åŠ¨æŸå¤±ä¸º11,897åƒå…ƒ"))
        self.assertTrue(verify_raw_value(-14838, "å¥—æœŸä¼šè®¡çš„å½±å“ (14,838)"))

    def test_dash_is_not_normalized_to_zero(self):
        _, metrics = normalize({
            "disclosure_status": "æœ‰æ•°å€¼",
            "metrics": [{
                "metric_type": "derivative_disposal_investment_income",
                "fact_level": "report",
                "value": 0,
                "unit": "åƒå…ƒ",
                "time_basis": "period",
                "raw": "å¤„ç½®è¡ç”Ÿé‡‘èèµ„äº§äº§ç”Ÿçš„æŠ•èµ„æŸå¤± â€”",
                "page": 10,
            }],
        }, "ã€P10ã€‘å¤„ç½®è¡ç”Ÿé‡‘èèµ„äº§äº§ç”Ÿçš„æŠ•èµ„æŸå¤± â€”")

        self.assertEqual(metrics, [])

    def test_percentage_zero_cannot_verify_a_monetary_zero(self):
        body = "ã€P48ã€‘è´§å¸äº’æ¢åˆçº¦ - 940,900 5,045 - - - - 0.00%"
        _, monetary = normalize({
            "disclosure_status": "æœ‰æ•°å€¼",
            "metrics": [{
                "metric_type": "ending_balance",
                "fact_level": "underlying",
                "scope": "å¤–æ±‡",
                "underlying": "è´§å¸äº’æ¢åˆçº¦",
                "value": 0,
                "unit": "åƒå…ƒ",
                "time_basis": "period_end",
                "raw": "è´§å¸äº’æ¢åˆçº¦ - 940,900 5,045 - - - - 0.00%",
                "page": 48,
            }],
        }, body)
        _, ratio = normalize({
            "disclosure_status": "æœ‰æ•°å€¼",
            "metrics": [{
                "metric_type": "net_asset_ratio",
                "fact_level": "underlying",
                "scope": "å¤–æ±‡",
                "underlying": "è´§å¸äº’æ¢åˆçº¦",
                "value": 0,
                "unit": "%",
                "time_basis": "period_end",
                "raw": "è´§å¸äº’æ¢åˆçº¦ - 940,900 5,045 - - - - 0.00%",
                "page": 48,
            }],
        }, body)

        self.assertEqual(monetary, [])
        self.assertEqual(len(ratio), 1)

    def test_estimates_cannot_enter_metrics(self):
        top, metrics = normalize({
            "disclosure_status": "æœ‰æ•°å€¼", "scopes": ["å•†å“"],
            "metrics": [{"metric_type": "estimated_spot_pnl", "value": 10,
                         "unit": "ä¸‡å…ƒ", "time_basis": "period",
                         "raw": "ä¼°ç®—ç°è´§æŸç›Š10ä¸‡å…ƒ", "page": 2}],
        }, "ã€P2ã€‘ä¼°ç®—ç°è´§æŸç›Š10ä¸‡å…ƒ")
        self.assertEqual(top["disclosure_status"], "æœ‰æ•°å€¼")
        self.assertEqual(metrics, [])

    def test_metric_keeps_original_unit_and_evidence(self):
        _, metrics = normalize({
            "disclosure_status": "æœ‰æ•°å€¼", "scopes": ["å¤–æ±‡"],
            "metrics": [{"metric_type": "period_pnl", "value": 321.5,
                         "currency": "CNY", "unit": "ä¸‡å…ƒ", "time_basis": "period",
                         "raw": "å¥—æœŸä¿å€¼ä¸šåŠ¡æœ¬æœŸæŸç›Šä¸º321.5ä¸‡å…ƒ", "page": 88}],
        }, "ã€P88ã€‘å¥—æœŸä¿å€¼ä¸šåŠ¡æœ¬æœŸæŸç›Šä¸º321.5ä¸‡å…ƒ")
        self.assertEqual(metrics[0]["unit"], "ä¸‡å…ƒ")
        self.assertTrue(metrics[0]["value_verified"])
        self.assertTrue(metrics[0]["quote_verified"])

    def test_metric_with_unlocatable_quote_is_not_persisted(self):
        _, metrics = normalize({
            "disclosure_status": "æœ‰æ•°å€¼",
            "metrics": [{
                "metric_type": "margin_end_cash",
                "value": 100,
                "unit": "ä¸‡å…ƒ",
                "time_basis": "period_end",
                "raw": "æœŸè´§ä¿è¯é‡‘100ä¸‡å…ƒ",
                "page": 88,
            }],
        }, "ã€P88ã€‘å…¶ä»–åº”æ”¶æ¬¾æ˜ç»†è¡¨")

        self.assertEqual(metrics, [])

    def test_verified_metric_marks_unmentioned_profile_for_review(self):
        top, metrics = normalize({
            "disclosure_status": "æœªæåŠ",
            "metrics": [{
                "metric_type": "derivative_asset_fv",
                "fact_level": "report",
                "value": 12.5,
                "unit": "ä¸‡å…ƒ",
                "time_basis": "period_end",
                "raw": "è¡ç”Ÿé‡‘èèµ„äº§æœŸæœ«ä½™é¢ä¸º12.5ä¸‡å…ƒ",
                "page": 88,
            }],
        }, "ã€P88ã€‘è¡ç”Ÿé‡‘èèµ„äº§æœŸæœ«ä½™é¢ä¸º12.5ä¸‡å…ƒ")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(top["disclosure_status"], "éœ€å¤æ ¸")

    def test_verified_business_table_resolves_profile_status_to_has_values(self):
        top, metrics = normalize({
            "disclosure_status": "æœªæåŠ",
            "metrics": [{
                "metric_type": "ending_balance",
                "fact_level": "scope",
                "scope": "å•†å“",
                "value": 8371222.5,
                "unit": "å…ƒ",
                "time_basis": "period_end",
                "source_section": "è¡ç”Ÿå“æŠ•èµ„æƒ…å†µ",
                "raw": "é‡‘å±æœŸè´§ æœŸæœ«è´¦é¢ä»·å€¼ 8,371,222.50",
                "page": 28,
                "table_cell_verified": True,
            }],
        }, "ã€P28ã€‘é‡‘å±æœŸè´§ æœŸæœ«è´¦é¢ä»·å€¼ 8,371,222.50")

        self.assertEqual(len(metrics), 1)
        self.assertEqual(top["disclosure_status"], "æœ‰æ•°å€¼")

    def test_verified_explicit_derivative_note_without_hedge_context_needs_review(self):
        top, metrics = normalize({
            "disclosure_status": "æœªæåŠ",
            "metrics": [{
                "metric_type": "derivative_fv_change_pnl",
                "fact_lev×®=òÚ$z{-®éÜj×¢FVbFW7EöÆö6F÷%÷&W6W'fW5ö7GVÅö66÷VçF–æuöæE÷7V6–f–5öf–ææ6–Åöæ÷FW2‡6VÆb“ ¢vW2Ò².ZY~iÉşKùŞXÂŠŞyIşY8h©^‹XB"¢‚f÷"ò–â&ævRƒ#•Ğ¢vW2æW‡FVæB…°¢.XZÎXûiÊ®[©NyJZY~iÉşKÉ®Šêy¨NXéşYºiŠşKªNi‰>iÉş™™‹è>yúÒ"À¢.ŠŞyIş˜y‰èŞ[z^X[~‹XNKª~iÉşiÊ¾KÙš)Ó‚Ã3RÃ3ƒXX2"À¢.ŠŞyIş˜y‰èŞ[z^X[~‹IşX®iÉşiÊ¾KÙš)ÓÃCS2ÃsXX2"À¢.ŠŞyIş˜y‰èŞ[z^X[~Kª~yIşy¨NXZÎXXK»~XÎXùXªiKny¸®K‹¢ÓBÃsƒÃscXX2"À¢.iÉş‹J~Y{ªnKùŞŠø˜yiÉşiÊ¾KÙš)ÓbÃcS2Ãc“"ã3XX2"À¢Ò ¢6VÆV7FVBÂòÂòÒ6VÆV7Eö6æF–FFU÷vW2‡vW2 ¢6VÆbæ76W'EG'VR‡³#Â#"Â#2Â#BÂ#WÒæ—77V'6WB‡6WB‡6VÆV7FVB’’ ¢FVbFW7EöÆö6F÷%÷&W6W'fW5ö66…öfÆ÷uö†VFvU÷&W6W'fU÷vR‡6VÆb“ ¢vW2Ò².ZY~iÉşKùŞXÂŠŞyIşY8h©^‹XB"¢‚f÷"ò–â&ævRƒ#•Ğ¢vW2æW‡FVæB…°¢.KÉ®ŠêiKşzÙbxë˜ykX˜xşZY~iÉşX*ZHr"¢RÀ¢.išî˜	®{¸ş‰
^Xh^Zë’"À¢.xë˜ykX˜xşZY~iÉşX*ZHuÆîiÊÎiÉşh˜[é~zˆîX˜ÕÆîXùyIşš)Ó#“ÃSXX2"À¢Ò ¢6VÆV7FVBÂòÂòÒ6VÆV7Eö6æF–FFU÷vW2‡vW2 ¢6VÆbæ76W'D–âƒ#2Â6VÆV7FVB ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUö¶VW5öw&VUö6öÇVÖåöÖVæ–ær‡6VÆb“ ¢&÷w2Ò°¢°¢.ŠŞyIşY8h©^‹XN{¾Yè²"Â.X‰ŞZx¾h©^‹XN˜yš)Ò"Â.iÉşX‰Ş˜yš)Ò"Â.iÊÎiÉşXZÎXXK»~XÅÆîXùXªhÙşy¸¢"À¢.ŠêXZ^iØ>y¸®y¨N{JşŠêÆîXZÎXXK»~XÎXùXª‚"Â.hª^Y®iÉşXh^‹JÕÆîXZ^˜yš)Ò"Â.hª^Y®iÉşXh^YJåÆîX{®˜yš)Ò"À¢.iÉşiÊ¾˜yš)Ò"Â.iÉşiÊ¾h©^‹XN˜yš)ŞXÚÆîXZÎXûhª^Y®iÉşiÊ¾XxÆî‹XNKª~jùNKè²"À¢ÒÀ¢².iÉş‹J~ZY~KùŞY{ªb"Â#"ÃCsã""Â#"ÃCsã""Â#2ÃSCBãC’"Â##’ãR"Â""Â""Â#bÃRãS"Â#ãBR%ÒÀ¢².‹ùÎiÉş˜y‰èŞY{ªb"Â"ÓrÃsBãr"Â"ÓrÃsBãr"Â#Ã3ƒbãC"Â""Â""Â""Â"ÓbÃS’ãS"Â"ÓãBR%ÒÀ¢².YŠê"Â"ÓBÃc2ãR"Â"ÓBÃc2ãR"Â#2Ã“3ã“"Â##’ãR"Â""Â""Â"ÓC“2ã“’"Â#ãR%ÒÀ¢Ğ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR‡&÷w2ÂvSÓ3RÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ…°¢†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'66÷R%ÒÂ—FVÕ²'fÇVR%Ò¢f÷"—FVÒ–âÖWG&–70¢ÒÂ°¢‚&FW&—fF—fUögeö6†ævU÷æÂ"Â.YXnY8"Â3SCBãC’’À¢‚&ö6•öÖ÷VçB"Â.YXnY8"Â#’ãR’À¢‚&VæF–æuö&Ææ6R"Â.YXnY8"ÂcRãS’À¢‚&æWEö76WE÷&F–ò"Â.YXnY8"ÂãB’À¢‚&FW&—fF—fUögeö6†ævU÷æÂ"Â.ZInkr"Â3ƒbãC’À¢‚&VæF–æuö&Ææ6R"Â.ZInkr"ÂÓcS’ãS’À¢‚&æWEö76WE÷&F–ò"Â.ZInkr"ÂÓãB’À¢Ò¢6VÆbæ76W'Dæ÷D–â‚'W&–öE÷W&6†6UöÖ÷VçB"Â°¢—FVÕ²&ÖWG&–5÷G—R%Òf÷"—FVÒ–âÖWG&–70¢Ò¢6VÆbæ76W'EG'VR†ÆÂ†—FVÕ²'F&ÆUö6VÆÅ÷fW&–f–VB%Òf÷"—FVÒ–âÖWG&–72’ ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUöW‡G&7G5öF&å÷G&ç67F–öç2‡6VÆb“ ¢&÷w2Ò°¢°¢.ŠŞyIşY8h©^‹XN{¾Yè²"Â.X‰ŞZx¾h©^‹XN˜yš)Ò"Â.iÉşX‰Ş˜yš)Ò"Â.iÊÎiÉşXZÎXXK»~XÎXùXªhÙşy¸¢"À¢.ŠêXZ^iØ>y¸®y¨N{JşŠêXZÎXXK»~XÎXùXª‚"Â.hª^Y®iÉşXh^‹JŞXZ^˜yš)Ò"Â.hª^Y®iÉşXh^YJîX{®˜yš)Ò"À¢.iÉşiÊ¾˜yš)Ò"Â.iÉşiÊ¾h©^‹XN˜yš)ŞXÚXZÎXûhª^Y®iÉşiÊ¾Xx‹XNKª~jùNKè²"À¢ÒÀ¢².iÉş‹Jr"Â""Â#BÃCSRã"Â"ÓÃCs‚ã‚"Â""Â#“"Ã“’ãƒ"Â#ƒBÃƒs‚ãƒ’"Â#Ã3Sãb"Â#ãrR%ÒÀ¢Ğ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR‡&÷w2ÂvSÓ3RÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ‡°¢—FVÕ²&ÖWG&–5÷G—R%Ó¢—FVÕ²'fÇVR%Òf÷"—FVÒ–âÖWG&–70¢ÒÂ°¢&FW&—fF—fUögeö6†ævU÷æÂ#¢ÓCs‚ã‚À¢'W&–öE÷W&6†6UöÖ÷VçB#¢“#“’ãƒÀ¢'W&–öE÷6ÆUöÖ÷VçB#¢ƒCƒs‚ãƒ’À¢&VæF–æuö&Ææ6R#¢3SãbÀ¢&æWEö76WE÷&F–ò#¢ãrÀ¢Ò ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUöW‡G&7G5öW‡Æ–6—Eö–çfW7FÖVçEö–æ6öÖR‡6VÆb“ ¢&÷w2Ò°¢°¢.ŠŞyIşY8h©^‹XN{¾Yè²"Â.iÉşX‰Şh©^‹XN˜yš)Ò"Â.iÊÎiÉşXZÎXXK»~XÎXùXªhÙşy¸¢"À¢.h©^‹XNiKny¸¢"Â.iÉşiÊ¾˜yš)Ò"Â.iÉşiÊ¾h©^‹XN˜yš)ŞXÚXZÎXûhª^Y®iÉşiÊ¾Xx‹XNKª~jùNKè²"À¢ÒÀ¢².YXnY8ŠŞyIşY8"Â#3"ÃRãc"Â"Ó2ÃSC"ãCB"Â#bÃSƒrãC""Â#crÃc“"ã3""Â#ãsrR%ÒÀ¢².ZInk~ŠŞyIşY8"Â#ã"Â#ã"Â#cBã#B"Â#ã"Â#ãR%ÒÀ¢Ğ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR‡&÷w2ÂvSÓ32ÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ…°¢†—FVÕ²'66÷R%ÒÂ—FVÕ²'fÇVR%ÒÂ—FVÕ²'Væ—B%Ò¢f÷"—FVÒ–âÖWG&–70¢–b—FVÕ²&ÖWG&–5÷G—R%ÒÓÒ&FW&—fF—fUöF—7÷6Åö–çfW7FÖVçEö–æ6öÖR ¢ÒÂ°¢‚.YXnY8"ÂcSƒrãC"Â.Kˆ~XX2"’À¢‚.ZInkr"ÂcBã#BÂ.Kˆ~XX2"’À¢Ò ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUö¶VW5ö†VFv–æuö'W6–æW75÷&÷w2‡6VÆb“ ¢&÷w2Ò°¢°¢.ŠŞyIşY8h©^‹XN{¾Yè²"Â.X‰ŞZx¾h©^‹XN˜yš)Ò"Â.iÉşX‰Ş˜yš)Ò"Â.iÊÎiÉşXZÎXXK»~XÎXùXªhÙşy¸¢"À¢.ŠêXZ^iØ>y¸®y¨N{JşŠêXZÎXXK»~XÎXùXª‚"Â.hª^Y®iÉşXh^‹JŞXZ^˜yš)Ò"Â.hª^Y®iÉşXh^YJîX{®˜yš)Ò"À¢.iÉşiÊ¾˜yš)Ò"Â.iÉşiÊ¾h©^‹XN˜yš)ŞXÚXZÎXûhª^Y®iÉşiÊ¾Xx‹XNKª~jùNKè²"À¢ÒÀ¢°¢.YXnY8iÉş‹J~ZY~iÉşKùŞXÂ"Â""Â#ƒcRãƒ2"Â"Ó#ƒrã3b"Â""À¢#‚ÃScrãƒr"Â#ÃãC"Â#sSbãc"Â#ã#R"À¢ÒÀ¢Ğ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR‡&÷w2ÂvSÓC’ÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ‡°¢—FVÕ²&ÖWG&–5÷G—R%Ó¢—FVÕ²'fÇVR%Òf÷"—FVÒ–âÖWG&–70¢ÒÂ°¢&FW&—fF—fUögeö6†ævU÷æÂ#¢Ó#ƒrã3bÀ¢'W&–öE÷W&6†6UöÖ÷VçB#¢ƒScrãƒrÀ¢'W&–öE÷6ÆUöÖ÷VçB#¢ãCÀ¢&VæF–æuö&Ææ6R#¢sSbãcÀ¢&æWEö76WE÷&F–ò#¢ã#À¢Ò ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUö†æFÆW5÷7'6Uö×VÇF–Æ–æUö†VFW'2‡6VÆb“ ¢&÷w2Ò°¢°¢""ÂæöæRÂæöæRÂ""ÂæöæRÂæöæRÂ""ÂæöæRÂ""Â.iÊÎiÉşXZÂ"À¢""Â.ŠêXZ^iØ2"Â""ÂæöæRÂ.hª^Y®iÉşXh^‹JÒ"ÂæöæRÀ¢.hª^Y®iÉşXh^YJâ"ÂæöæRÂæöæRÂ.iÉşiÊ¾˜yš)Ò"Â.iÉşiÊ¾h©^‹XB"ÂæöæRÀ¢ÒÀ¢°¢""Â.ŠŞyIşY8h©^‹XN{²"ÂæöæRÂ""Â.X‰ŞZx¾h©^‹XN˜y"ÂæöæRÀ¢.iÉşX‰Ş˜yš)Ò"ÂæöæRÂ""Â.XXK»~XÎXùXªhÙşy¸¢"ÂæöæRÀ¢.y¸®y¨N{JşŠêXZÎXXK»~XÎXùXª‚"ÂæöæRÂæöæRÂ.XZ^˜yš)Ò"ÂæöæRÀ¢.X{®˜yš)Ò"ÂæöæRÂæöæRÂæöæRÂ.˜yš)ŞXÚXZÎXûhª^Y®iÉşiÊ¾Xx‹XNKª~jùNKè²"ÂæöæRÀ¢ÒÀ¢°¢.YXnY8ZY~iÉşKùŞXÂ"ÂæöæRÂæöæRÂ#ƒcRãƒ2"ÂæöæRÂæöæRÀ¢#ƒcRãƒ2"ÂæöæRÂ"Ó#ƒrã3b"ÂæöæRÂæöæRÂ#"ÂæöæRÀ¢æöæRÂ#‚ÃScrãƒr"ÂæöæRÂ#ÃãB"ÂæöæRÂæöæRÀ¢#sSbãc"Â#ã#R"ÂæöæRÀ¢ÒÀ¢Ğ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR‡&÷w2ÂvSÓC’ÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ‡°¢—FVÕ²&ÖWG&–5÷G—R%Ó¢—FVÕ²'fÇVR%Òf÷"—FVÒ–âÖWG&–70¢ÒÂ°¢&FW&—fF—fUögeö6†ævU÷æÂ#¢Ó#ƒrã3bÀ¢&ö6•öÖ÷VçB#¢ãÀ¢'W&–öE÷W&6†6UöÖ÷VçB#¢ƒScrãƒrÀ¢'W&–öE÷6ÆUöÖ÷VçB#¢ãCÀ¢&VæF–æuö&Ææ6R#¢sSbãcÀ¢&æWEö76WE÷&F–ò#¢ã#À¢Ò ¢FVbFW7E÷7FæF&EöFW&—fF—fU÷F&ÆUö66WG5ö&ööµ÷fÇVUö†VFW%÷f&–çB‡6VÆb“ ¢ÖWG&–72Ò'6UöFW&—fF—fUö–çfW7FÖVçE÷F&ÆR…°¢°¢.ŠŞyIşY8h©^‹XN{¾Yè²"Â.X‰ŞZx¾h©^‹XN˜yš)Ò"Â.iÉşX‰Ş‹Jn™Ú.K»~XÂ"Â.iÊÎiÉşXZÎXXK»~XÎXùXªhÙşy¸¢"À¢.ŠêXZ^iØ>y¸®y¨N{JşŠêXZÎXXK»~XÎXùXª‚"Â.hª^Y®iÉşXh^‹JŞXZ^˜yš)Ò"Â.hª^Y®iÉşXh^YJîX{®˜yš)Ò"À¢.iÉşiÊ¾‹Jn™Ú.K»~XÂ"Â.iÉşiÊ¾‹Jn™Ú.K»~XÎXÚXZÎXûhª^Y®iÉşiÊ¾Xx‹XNKª~jùNKè¾ûÈ‚^ûÈ’"À¢ÒÀ¢².išî˜	®‹ùÎiÉò"Â""Â#’Ãƒ#RãcR"Â"Ó’ÃƒsRãC"Â""Â##2Ã#Rã’"Â##RÃCãc‚"Â"Ó"Ãcbã#B"Â"Óã’%ÒÀ¢ÒÂvSÓC2ÂVæ—CÒ.Kˆ~XX2" ¢6VÆbæ76W'DWVÂ‡°¢—FVÕ²&ÖWG&–5÷G—R%Ó¢—FVÕ²'fÇVR%Òf÷"—FVÒ–âÖWG&–70¢ÒÂ°¢&FW&—fF—fUögeö6†ævU÷æÂ#¢Ó“ƒsRãCÀ¢'W&–öE÷W&6†6UöÖ÷VçB#¢#3#Rã’À¢'W&–öE÷6ÆUöÖ÷VçB#¢#SCãc‚À¢&VæF–æuö&Ææ6R#¢Ó#cbã#BÀ¢&æWEö76WE÷&F–ò#¢Óã’À¢Ò ¢FVbFW7Eöæ÷FU÷F&ÆW5öW‡G&7EöÖ&v–å÷÷6—F–öç5öæE÷æÅö6ö×öæVçG2‡6VÆb“ ¢Ö&v–âÒ'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².jËîšh
~‹J‚"Â.[›NiÊ¾‹Jn™Ú.KÙš)Ò"Â.[›NX‰Ş‹Jn™Ú.KÙš)Ò%ÒÀ¢².iÉş‹J~Y{ªnKùŞŠø˜y"Â#bÃcS2Ãc“"ã3"Â#3"Ã“‚Ã3’ã“%ÒÀ¢ÒÂvSÓ3"ÂVæ—CÒ.XX2"¢f—%÷fÇVRÒ'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².šyºâ"Â.[›NiÊ¾XZÎXXK»~XÂ"ÂæöæRÂæöæRÂæöæUÒÀ¢´æöæRÂ.zÊÎKˆ[.jÊ"Â.zÊÎK¨Î[.jÊ"Â.zÊÎKˆ[.jÊ"Â.YŠê%ÒÀ¢².ûÈKˆûÈKªNi‰>h
~˜y‰èŞ‹XNKªr"Â#ƒ"Ã##rÃcSRã’"Â""Â#ƒbÃssbÃs#rãSr"Â#3c’ÃBÃ3ƒ"ãsb%ÒÀ¢².ûÈƒ^ûÈŠŞyIş˜y‰èŞ[z^X[r"Â#‚Ã3RÃ3ƒã"Â""Â""Â#‚Ã3RÃ3ƒã%ÒÀ¢².ûÈK©NûÈKªNi‰>h
~˜y‰èŞ‹IşX¢"Â#ÃCS2Ãsã"Â""Â#"Ãs"Ã3ƒrã“r"Â##2ÃS#RÃCSrã“r%ÒÀ¢².ûÈƒ.ûÈŠŞyIş˜y‰èŞ[z^X[r"Â#ÃCS2Ãsã"Â""Â""Â#ÃCS2Ãsã%ÒÀ¢ÒÂvSÓ3sbÂVæ—CÒ.XX2"¢æÂÒ'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².Kª~yIşXZÎXXK»~XÎXùXªiKny¸®y¨NiÚ^k©"Â.iÊÎ[›NXùyIşš)Ò"Â.Kˆ®[›NXùyIşš)Ò%ÒÀ¢².ŠŞyIş˜y‰èŞ[z^X[~Kª~yIşy¨NXZÎXXK»~XÎXùXª‚"Â"ÓBÃsƒÃscã"Â#’Ãcc’ÃS#ã%ÒÀ¢ÒÂvSÓ3S2ÂVæ—CÒ.XX2" ¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%Ò’f÷"—FVÒ–âÖ&v–åÒÀ¢²‚&Ö&v–åöVæEö66‚"ÂccS3c“"ã3•ÒÀ¢¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%Ò’f÷"—FVÒ–âf—%÷fÇVUÒÀ¢°¢‚&FW&—fF—fUö76WEögb"Âƒ3S3ƒã’À¢‚&FW&—fF—fUöÆ–&–Æ—G•ögb"ÂCS3sã’À¢ÒÀ¢¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%Ò’f÷"—FVÒ–âæÅÒÀ¢²‚&FW&—fF—fUögeö6†ævU÷æÂ"ÂÓCsƒscã•ÒÀ¢ ¢FVbFW7Eöæ÷FU÷F&ÆUöW‡G&7G5öæÖVEöFW&—fF—fUö–çfW7FÖVçEö–æ6öÖR‡6VÆb“ ¢ÖWG&–72Ò'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².›¸N˜yB´N8y›Ş™;eB´BKªNi‰>h©^‹XNiKny¸¢"Â"Ó#BÃScBÃ“ãS‚"Â"ÓS"ÃsS2Ãƒ“Bãsb%ÒÀ¢².yn‹J.Kª~Y8h©^‹XNiKny¸¢"Â#ÃscÃC3‚ãR"Â#rÃ##ÃS3bã#"%ÒÀ¢².YŠê"Â"Ó"Ã3“2Ãc2ã“2"Â"Ó3bÃs#ÃSrãb%ÒÀ¢ÒÂvSÓC2ÂVæ—CÒ.XX2" ¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%ÒÂ—FVÕ²&66÷VçEöæÖR%Ò’f÷"—FVÒ–âÖWG&–75ÒÀ¢²€¢&FW&—fF—fUöF—7÷6Åö–çfW7FÖVçEö–æ6öÖR"À¢Ó#CScC“ãS‚À¢.›¸N˜yB´N8y›Ş™;eB´NKªNi‰>h©^‹XNiKny¸¢"À¢•ÒÀ¢ ¢FVbFW7E÷&ö×E÷7FFW5öÖ&v–åöæEöæöåö†VFvUöFW&—fF—fUö&÷VæF&–W2‡6VÆb“ ¢ÖW76vW2Ò'V–ÆEöÖWG&–5öÖW76vW2€¢'÷6—F–öâ"À¢.iùXZÎXûƒ##^[›N[›N[ªnhª^Y¢"À¢.iùXZÎXû‚"À¢#c"À¢###Te’"À¢.8	8	›¸N˜yzyş‹XKùŞŠø˜yKˆ~XX2"À¢¢&ö×E÷FW‡BÒ%Æâ"æ¦ö–â‡7G"†—FVÒævWB‚&6öçFVçB"’÷"""’f÷"—FVÒ–âÖW76vW2 ¢6VÆbæ76W'D–â‚.›¸N˜yzyş‹XKùŞŠø˜y"Â&ö×E÷FW‡B¢6VÆbæ76W'D–â‚.KˆŞ[é~KÙÎK‹®ŠŞyIşY8KùŞŠø˜y"Â&ö×E÷FW‡B ¢æÅöÖW76vW2Ò'V–ÆEöÖWG&–5öÖW76vW2€¢'æÂ"À¢.iùXZÎXûƒ##^[›N[›N[ªnhª^Y¢"À¢.iùXZÎXû‚"À¢#c"À¢###Te’"À¢.8	#8	ŠŞyIş˜y‰èŞ[z^X[~XZÎXXK»~XÎXùXªiKny¸£Kˆ~XX2"À¢¢æÅ÷FW‡BÒ%Æâ"æ¦ö–â‡7G"†—FVÒævWB‚&6öçFVçB"’÷"""’f÷"—FVÒ–âæÅöÖW76vW2¢6VÆbæ76W'D–â‚.KˆŞˆ;ŞXÙ^xºÎŠøiˆî[îK¨îZY~iÉşKùŞXÎZéî™˜^hÙşy¸¢"ÂæÅ÷FW‡B¢6VÆbæ76W'D–â‚%B´B"ÂæÅ÷FW‡B ¢FVbFW7Eöæ÷FU÷F&ÆUöW‡G&7G5ö66…öfÆ÷uö†VFvU÷&W6W'fUö6öÇVÖç2‡6VÆb“ ¢ÖWG&–72Ò'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².šyºâ"Â.iÉşX‰ŞKÙš)Ò"Â.iÊÎiÉşXùyIşš)Ò"ÂæöæRÂæöæRÂæöæRÂæöæRÂæöæRÂ.iÉşiÊ¾KÙš)Ò%ÒÀ¢´æöæRÂæöæRÂ.iÊÎiÉşh˜[é~zˆîX˜ŞXùyIşš)Ò"Â.XxşûÉ®X˜ŞiÉşŠêXZ^X[nK¹n{»ÎYiKny¸®[Ù>iÉş‹ÚÎXZ^hÙşy¸¢"À¢æöæRÂ.XxşûÉ®h˜[é~zˆî‹KyJ‚"Â.zˆîYî[Ù.[îK¨îjøŞXZÎXû‚"ÂæöæRÂæöæUÒÀ¢².xë˜ykX˜xşZY~iÉşX*ZHr"Â"Ó"Ã#’Ãƒ3’ã“b"Â##“ÃSã"Â"Ó"ÃcCbÃƒã"À¢""Â#CCRÃS3Rã"Â#"ÃC“"ÃscRã"Â""Â##s"Ã“#RãB%ÒÀ¢ÒÂvSÓsÂVæ—CÒ.XX2" ¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%Ò’f÷"—FVÒ–âÖWG&–75ÒÀ¢²‚&ö6•öÖ÷VçB"Â#“Sã’Â‚'&V6Æ76–f–6F–öåöÖ÷VçB"ÂÓ#cCcƒã•ÒÀ¢ ¢FVbFW7Eöf—%÷fÇVUö6öçF–çVF–öåöW‡G&7G5öFW&—fF—fUöÆ–&–Æ—G•÷F÷FÂ‡6VÆb“ ¢ÖWG&–72Ò'6UöFW&—fF—fUöæ÷FU÷F&ÆR…°¢².šyºâ"Â.iÉşiÊ¾XZÎXXK»~XÂ"ÂæöæRÂæöæRÂæöæUÒÀ¢´æöæRÂ.zÊÎKˆ[.jÊ"Â.zÊÎK¨Î[.jÊ"Â.zÊÎKˆ[.jÊ"Â.YŠê%ÒÀ¢².hÈ{ºŞKº^XZÎXXK»~XÎŠê˜xşy¨N‹XNKª~h¾š)Ò"Â##BÃCSbÃ3Rã"Â#Ã33bÃCsrÃcƒ‚ãS’"Â""Â#Ãƒc2ÃS“Ã#ƒBãƒ‚%ÒÀ¢².ûÈK©NûÈŠŞyIş˜y‰èŞ‹IşX¢"Â""Â""Â""Â"%ÒÀ¢²#îiÉş‹J~Xø®iÉşiØ>ŠŞyIş[z^X[r"Â##rÃScBÃCƒbã2"Â""Â""Â##rÃScBÃCƒbã2%ÒÀ¢²#"îZInk~ŠŞyIş[z^X[r"Â""Â##‚ÃScBÃ#cãC‚"Â""Â##‚ÃScBÃ#cãC‚%ÒÀ¢².hÈ{ºŞKº^XZÎXXK»~XÎŠê˜xşy¨N‹IşX®h¾š)Ò"Â##rÃScBÃCƒbã2"Â##‚ÃScBÃ#cãC‚"Â""Â#SbÃ#‚ÃsCbãc%ÒÀ¢ÒÂvSÓ#cÂVæ—CÒ.XX2" ¢6VÆbæ76W'DWVÂ€¢²†—FVÕ²&ÖWG&–5÷G—R%ÒÂ—FVÕ²'fÇVR%Ò’f÷"—FVÒ–âÖWG&–75ÒÀ¢²‚&FW&—fF—fUöÆ–&–Æ—G•ögb"ÂSc#ƒsCbãc•ÒÀ¢ ¢FVbFW7EöV6…÷F&ÆU÷W6W5÷F†UöæV&W7E÷&V6VF–æu÷Væ—B‡6VÆb“ ¢&Æö6·2Ò°¢ƒÂÂÂ#Â.XÙ^KØŞûÉ®XX2[ˆzxŞûÉ®K«®k	[ˆ"ÂÂ’À¢ƒÂ#ÂÂ#Â.XÙ^KØŞûÉ®Kˆ~XX2[ˆzxŞûÉ®K«®k	[ˆ"ÂÂ’À¢Ğ ¢6VÆbæ76W'DWVÂ‡Væ—Eö&Vf÷&U÷F&ÆR†&Æö6·2ÂF&ÆU÷F÷ÓÂvU÷FW‡CÒ""’Â.XX2"¢6VÆbæ76W'DWVÂ‡Væ—Eö&Vf÷&U÷F&ÆR†&Æö6·2ÂF&ÆU÷F÷Ó#SÂvU÷FW‡CÒ""’Â.Kˆ~XX2" ¢FVbFW7E÷F&ÆU÷Væ—E÷7W÷'G5öÖ–ÆÆ–öå÷—Vâ‡6VÆb“ ¢&Æö6·2Ò°¢ƒÂÂÂ#Â.XÙ^KØŞûÉ®y›îKˆ~XX2[ˆzxŞûÉ®K«®k	[ˆ"ÂÂ’À¢Ğ ¢6VÆbæ76W'DWVÂ€¢Væ—Eö&Vf÷&U÷F&ÆR†&Æö6·2ÂF&ÆU÷F÷ÓÂvU÷FW‡CÒ""’À¢.y›îKˆ~XX2"À¢ ¢FVbFW7E÷&VçEö6ö×ç•öæ÷FU÷7F'Eö—5öFWFV7FVB‡6VÆb“ ¢6VÆbæ76W'DWVÂ†f–æE÷&VçEö6ö×ç•öæ÷FU÷7F'B…°¢.Y[›n‹J.Xªhª^Ššyºîk:˜x¢"À¢.XØK™Ş8jøŞXZÎXû‹J.Xªhª^ŠK‹¾Šhšyºîk:˜x¢"À¢.h©^‹XNiKny¸¢"À¢Ò’Â" ¢FVbFW7EöÖ&¶VE÷FW‡Eö¶VW5öWfW'•ö6æF–FFU÷vUöæEöÆFUöfö7W5÷FW&Ò‡6VÆb“ ¢vW2Ò°¢‚.išî˜	®Xh^Zë’"¢S’²FW&Ğ¢f÷"FW&Ò–â‚.ZY~iÉşKùŞXÂ"Â.XZÎXXK»~XÎXùXªhÙşy¸¢"Â.ŠŞyIş˜y‰èŞ‹IşX¢"Â.KùŞŠø˜y"¢Ğ ¢Ö&¶VBÒ'V–ÆEöÖ&¶VE÷FW‡B€¢vW2À¢³Â"Â2ÂEÒÀ¢².ZY~iÉşKùŞXÂ"Â.XZÎXXK»~XÎXùXªhÙşy¸¢"Â.ŠŞyIş˜y‰èŞ‹IşX¢"Â.KùŞŠø˜y%ÒÀ¢ ¢6VÆbæ76W'DÆW74WVÂ†ÆVâ†Ö&¶VB’ÂÔ…ôÔ$´TEô4„%2¢6VÆbæ76W'EG'VR†ÆÂ†b.8	·vWŞ8	"–âÖ&¶VBf÷"vR–â&ævRƒÂR’’¢6VÆbæ76W'EG'VR†ÆÂ‡FW&Ò–âÖ&¶VBf÷"FW&Ò–â€¢.ZY~iÉşKùŞXÂ"Â.XZÎXXK»~XÎXùXªhÙşy¸¢"Â.ŠŞyIş˜y‰èŞ‹IşX¢"Â.KùŞŠø˜y"À¢’’  ¦–bõöæÖUõòÓÒ%õöÖ–åõò# ¢Væ—GFW7BæÖ–â‚ 