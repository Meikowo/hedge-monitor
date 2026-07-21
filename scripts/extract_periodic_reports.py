#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4a POC：对已定位年报做小批量 LLM 抽取。必须显式 --confirm-llm。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cninfo
import prompt_periodic as pp
from common import env, log, sb_delete, sb_insert, sb_select, sb_update, sb_upsert, snapshot_json
from extract_announcements import call_llm, verify_quote
from periodic_pdf import locate_pdf

DISCLOSURE = {"有数值", "提及无数值", "未提及", "需复核"}
SCOPES = {"商品", "外汇", "利率", "其他"}
TIME_BASIS = {"period", "period_end", "period_peak"}
METRICS = {
    "period_purchase_amount", "period_sale_amount", "period_pnl", "ending_balance",
    "net_asset_ratio", "derivative_asset_fv", "derivative_liability_fv",
    "margin_end_cash", "margin_peak_reported", "collateral_end_fair_value", "credit_facility_used_end",
    "option_premium_usage_peak", "notional_end_reported", "notional_peak_reported",
    "contract_quantity_end", "oci_amount", "reclassification_amount",
}


def _list(value) -> list[str]:
    nullish = {"none", "null", "n/a", "未提及", "无"}
    return list(dict.fromkeys(str(x).strip() for x in (value or [])
                              if str(x).strip() and str(x).strip().lower() not in nullish))


def verify_raw_value(value: float, raw: str) -> bool:
    """只确认模型输出数字可在原文摘录直接找到；不做单位换算或推导。"""
    target = float(value)
    for match in re.finditer(r"[-+]?[0-9][0-9,，]*(?:\.[0-9]+)?", raw or ""):
        try:
            candidate = float(match.group(0).replace(",", "").replace("，", ""))
        except ValueError:
            continue
        if abs(candidate - target) <= max(1e-8, abs(target) * 1e-8):
            return True
    return False


def normalize(result: dict, body: str) -> tuple[dict, list[dict]]:
    status = result.get("disclosure_status")
    status = status if status in DISCLOSURE else "需复核"
    top = {
        "disclosure_status": status,
        "scopes": [x for x in _list(result.get("scopes")) if x in SCOPES],
        "instruments": _list(result.get("instruments")),
        "underlyings": _list(result.get("underlyings")),
        "purpose": (result.get("purpose") or None),
        "hedge_accounting": _list(result.get("hedge_accounting")),
        "summary": (result.get("summary") or "")[:300] or None,
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "confidence": float(result["confidence"]) if isinstance(result.get("confidence"), (int, float)) else None,
        "model": env("LLM_MODEL", "MiniMax-M3"), "prompt_version": pp.PROMPT_VERSION,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    metrics: list[dict] = []
    for raw_item in result.get("metrics") or []:
        if not isinstance(raw_item, dict) or raw_item.get("metric_type") not in METRICS:
            continue
        value = raw_item.get("value")
        page = raw_item.get("page")
        quote = str(raw_item.get("raw") or "")[:240]
        if not isinstance(value, (int, float)) or not isinstance(page, int) or page <= 0 or not quote:
            continue
        metrics.append({
            "metric_type": raw_item["metric_type"],
            "scope": raw_item.get("scope") if raw_item.get("scope") in SCOPES else None,
            "underlying": raw_item.get("underlying") or None,
            "value": float(value), "currency": raw_item.get("currency") or None,
            "unit": raw_item.get("unit") or "其他",
            "time_basis": raw_item.get("time_basis") if raw_item.get("time_basis") in TIME_BASIS else "period",
            "source_section": raw_item.get("source_section") or None,
            "raw_text": quote, "page": page,
            "value_verified": verify_raw_value(value, quote),
            "quote_verified": verify_quote(quote, body), "value_origin": "reported",
        })
    if metrics and top["disclosure_status"] == "提及无数值":
        top["disclosure_status"] = "需复核"
    return top, metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="小批量抽取定期报告")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--report-id", action="append")
    ap.add_argument("--confirm-llm", action="store_true", help="确认本次会产生模型调用")
    ap.add_argument("--dry-run", action="store_true", help="调用模型但不写数据库")
    args = ap.parse_args()
    if not args.confirm_llm:
        raise SystemExit("为防止意外消耗额度，必须显式添加 --confirm-llm")
    params = {"select": "report_id,code,name,title,report_period,pdf_url,candidate_pages",
              "status": "eq.located", "order": "publish_date.desc", "limit": str(args.limit)}
    if args.report_id:
        params.pop("status")
        params["report_id"] = f"in.({','.join(args.report_id)})"
    reports = sb_select("periodic_reports", params)
    run = []
    for i, report in enumerate(reports, 1):
        log(f"[{i}/{len(reports)}] LLM抽取 {report.get('name')} {report.get('report_period')}")
        content = cninfo.download_pdf(report["pdf_url"])
        if not content:
            raise RuntimeError(f"PDF下载失败: {report['report_id']}")
        located = locate_pdf(content)
        result = call_llm(pp.build_messages(
            report["title"], report.get("name"), report["code"],
            report["report_period"], located.marked_text))
        top, metrics = normalize(result, located.marked_text)
        top["report_id"] = report["report_id"]
        if not args.dry_run:
            sb_upsert("periodic_derivatives", [top], on_conflict="report_id")
            sb_delete("periodic_metric_items", {"report_id": f"eq.{report['report_id']}"})
            if metrics:
                sb_insert("periodic_metric_items", [
                    {**item, "report_id": report["report_id"]} for item in metrics])
            sb_update("periodic_reports", {"report_id": f"eq.{report['report_id']}"},
                      {"status": "extracted", "note": None})
        run.append({"report": report, "extraction": top, "metrics": metrics, "raw": result})
        log(f"披露状态={top['disclosure_status']}；数值事实={len(metrics)} 条")
    snapshot_json("periodic_extract_run", run)


if __name__ == "__main__":
    main()
