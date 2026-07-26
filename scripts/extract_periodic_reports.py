#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4a POC：对已定位年报做小批量 LLM 抽取。必须显式 --confirm-llm。"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cninfo
import prompt_periodic as pp
from common import ROOT, env, log, sb_delete, sb_insert, sb_select, sb_update, sb_upsert, snapshot_json
from extract_announcements import call_llm, verify_quote
from periodic_pdf import locate_pdf

DISCLOSURE = {"有数值", "提及无数值", "未提及", "需复核"}
SCOPES = {"商品", "外汇", "利率", "其他"}
TIME_BASIS = {"period", "period_end", "period_peak"}
METRICS = {
    "period_purchase_amount", "period_sale_amount", "period_pnl", "ending_balance",
    "reported_derivative_comprehensive_pnl", "derivative_disposal_investment_income",
    "derivative_fv_change_pnl", "derivative_net_fv",
    "net_asset_ratio", "derivative_asset_fv", "derivative_liability_fv",
    "margin_end_cash", "margin_peak_reported", "collateral_end_fair_value", "credit_facility_used_end",
    "option_premium_usage_peak", "notional_end_reported", "notional_peak_reported",
    "contract_quantity_end", "oci_amount", "reclassification_amount",
}
HEDGE_ACCOUNTING_STATUS = {"已应用", "未应用", "混合应用", "未明确披露", "需复核"}
HEDGE_ACCOUNTING_TYPES = {"公允价值套期", "现金流量套期", "境外经营净投资套期", "其他"}
ACCOUNTING_ITEM_STATUS = {"已应用", "未应用", "未明确披露", "需复核"}
FACT_LEVELS = {"report", "scope", "underlying"}


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
        tolerance = max(1e-8, abs(target) * 1e-8)
        if abs(candidate - target) <= tolerance:
            return True
        if target < 0 and abs(abs(candidate) - abs(target)) <= tolerance:
            before = (raw or "")[max(0, match.start() - 16):match.start()]
            after = (raw or "")[match.end():min(len(raw or ""), match.end() + 4)]
            parenthesized = (
                before.rstrip().endswith(("(", "（"))
                and after.lstrip().startswith((")", "）"))
            )
            loss_word = any(word in before for word in ("损失", "亏损", "减少"))
            if parenthesized or loss_word:
                return True
    return False


def zero_literal_matches_unit(unit: str, raw: str) -> bool:
    """防止把同一行的 0.00% 错配为金额 0。"""
    matches = list(re.finditer(
        r"(?<![0-9.,])[-+]?0(?:\.0+)?(?![0-9.,])",
        raw or "",
    ))
    if not matches:
        return False
    percentage_matches = [
        match for match in matches
        if (raw or "")[match.end():].lstrip().startswith("%")
    ]
    if unit == "%":
        return bool(percentage_matches)
    return len(percentage_matches) < len(matches)


SCALED_UNITS = {
    "千元": ("元", 1_000),
    "万元": ("元", 10_000),
    "亿元": ("元", 100_000_000),
    "万美元": ("美元", 10_000),
    "亿美元": ("美元", 100_000_000),
}


def restore_literal_scale(value: float, unit: str | None, raw: str) -> tuple[float, str]:
    """模型若擅自换算为基础单位，则恢复原文数值及原文单位。"""
    current_value = float(value)
    current_unit = unit or "其他"
    matches = [
        match for match in re.finditer(
        r"([-+]?[0-9][0-9,]*(?:\.[0-9]+)?)\s*(千元|万元|亿元|万美元|亿美元)",
        raw or "",
        )
        if SCALED_UNITS[match.group(2)][0] == current_unit
    ]
    for match in matches:
        literal = float(match.group(1).replace(",", ""))
        literal_unit = match.group(2)
        base_unit, scale = SCALED_UNITS[literal_unit]
        converted = literal * scale
        tolerance = max(1e-8, abs(current_value) * 1e-8)
        if abs(abs(converted) - abs(current_value)) <= tolerance:
            restored = -abs(literal) if current_value < 0 else literal
            return restored, literal_unit
    if len(matches) == 1:
        match = matches[0]
        literal = float(match.group(1).replace(",", ""))
        restored = -abs(literal) if current_value < 0 else literal
        return restored, match.group(2)
    return current_value, current_unit


def normalize_metric_type(metric_type: str, quote: str) -> str:
    """用原文纠正容易混淆的峰值口径。"""
    if (
        metric_type == "notional_peak_reported"
        and "保证金" in quote
        and any(term in quote for term in ("最高", "最大", "任意时点"))
    ):
        return "margin_peak_reported"
    return metric_type


def extract_explicit_pnl_metrics(body: str) -> list[dict]:
    """兜底提取“报告期实际损益情况”中的明确平仓与持仓损益合计。"""
    metrics: list[dict] = []
    page_blocks = re.finditer(
        r"【P(?P<page>\d+)】(?P<body>.*?)(?=【P\d+】|\Z)",
        body or "",
        flags=re.S,
    )
    pnl_pattern = re.compile(
        r"(?P<raw>(?:计入报告期内的)?"
        r"(?P<label>[^。\n]{0,60}?(?:平仓与持仓损益|持仓与平仓损益))"
        r"(?:合计)?(?:为|：|:)\s*"
        r"(?P<value>[-−]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)\s*"
        r"(?P<unit>亿美元|万美元|美元|亿元|万元|千元|元))"
    )
    for page_match in page_blocks:
        page = int(page_match.group("page"))
        for match in pnl_pattern.finditer(page_match.group("body")):
            value = float(
                match.group("value").replace("−", "-").replace(" ", "").replace(",", "")
            )
            unit = match.group("unit")
            label = match.group("label")
            if "商品" in label:
                scope = "商品"
            elif "外汇" in label or "汇率" in label:
                scope = "外汇"
            elif "利率" in label:
                scope = "利率"
            else:
                scope = None
            metrics.append({
                "metric_type": "reported_derivative_comprehensive_pnl",
                "fact_level": "scope" if scope else "report",
                "scope": scope,
                "underlying": None,
                "value": value,
                "currency": "USD" if "美元" in unit else "CNY",
                "unit": unit,
                "time_basis": "period",
                "source_section": "报告期实际损益情况",
                "account_name": None,
                "is_restricted": None,
                "counterparty": None,
                "raw": match.group("raw"),
                "page": page,
            })
    return metrics


def should_replace_metric_family(
    is_full_run: bool,
    family: str,
    metrics: list[dict],
) -> bool:
    """完整运行可确认空结果；选择性短批次空结果默认保留旧事实。"""
    if is_full_run:
        return True
    allowed = set(pp.METRIC_FAMILIES[family])
    return any(item.get("metric_type") in allowed for item in metrics)


def load_sample_codes(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [row["code"].zfill(6) for row in csv.DictReader(f)]


def merge_pass_results(profile: dict, metric_results: dict[str, dict]) -> dict:
    """合并短输出批次，并拒绝模型越过当前批次的 metric_type。"""
    merged = dict(profile)
    metrics: list[dict] = []
    for family, result in metric_results.items():
        allowed = set(pp.METRIC_FAMILIES.get(family, ()))
        for item in result.get("metrics") or []:
            if isinstance(item, dict) and item.get("metric_type") in allowed:
                metrics.append(item)
    merged["metrics"] = metrics
    return merged


def normalize_accounting_items(result: dict, body: str) -> list[dict]:
    items: list[dict] = []
    for raw_item in result.get("hedge_accounting_items") or []:
        if not isinstance(raw_item, dict):
            continue
        status = raw_item.get("application_status")
        status = status if status in ACCOUNTING_ITEM_STATUS else "需复核"
        accounting_type = raw_item.get("accounting_type")
        accounting_type = accounting_type if accounting_type in HEDGE_ACCOUNTING_TYPES else None
        page = raw_item.get("page")
        page = page if isinstance(page, int) and page > 0 else None
        quote = str(raw_item.get("quote") or "")[:240] or None
        quote_verified = verify_quote(quote, body) if quote else None
        confidence = raw_item.get("confidence")
        confidence = (
            float(confidence)
            if isinstance(confidence, (int, float)) and 0 <= confidence <= 1 else None
        )
        need_review = (
            status == "需复核"
            or (status == "已应用" and accounting_type is None)
            or quote_verified is False
        )
        items.append({
            "scope": raw_item.get("scope") if raw_item.get("scope") in SCOPES else None,
            "instrument": raw_item.get("instrument") or None,
            "underlying_asset": raw_item.get("underlying_asset") or None,
            "application_status": status,
            "accounting_type": accounting_type,
            "non_application_reason": raw_item.get("non_application_reason") or None,
            "source_section": raw_item.get("source_section") or None,
            "page": page,
            "quote": quote,
            "quote_verified": quote_verified,
            "confidence": confidence,
            "need_review": need_review,
        })
    return items


def normalize(result: dict, body: str) -> tuple[dict, list[dict]]:
    status = result.get("disclosure_status")
    status = status if status in DISCLOSURE else "需复核"
    legacy_accounting = _list(result.get("hedge_accounting"))
    accounting_types = [
        x for x in _list(result.get("hedge_accounting_types") or legacy_accounting)
        if x in HEDGE_ACCOUNTING_TYPES
    ]
    accounting_status = result.get("hedge_accounting_status")
    if accounting_status not in HEDGE_ACCOUNTING_STATUS:
        accounting_status = "已应用" if accounting_types else "未明确披露"
    accounting_evidence = result.get("hedge_accounting_evidence")
    accounting_evidence = accounting_evidence if isinstance(accounting_evidence, dict) else {}
    accounting_page = accounting_evidence.get("page")
    accounting_page = accounting_page if isinstance(accounting_page, int) and accounting_page > 0 else None
    accounting_quote = str(accounting_evidence.get("quote") or "")[:240] or None
    top = {
        "disclosure_status": status,
        "scopes": [x for x in _list(result.get("scopes")) if x in SCOPES],
        "instruments": _list(result.get("instruments")),
        "underlyings": _list(result.get("underlyings")),
        "purpose": (result.get("purpose") or None),
        "hedge_accounting": legacy_accounting or accounting_types,
        "hedge_accounting_status": accounting_status,
        "hedge_accounting_types": accounting_types,
        "non_application_reason": (result.get("non_application_reason") or None),
        "hedge_accounting_page": accounting_page,
        "hedge_accounting_quote": accounting_quote,
        "hedge_accounting_quote_verified": (
            verify_quote(accounting_quote, body) if accounting_quote else None
        ),
        "summary": (result.get("summary") or "")[:300] or None,
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "confidence": float(result["confidence"]) if isinstance(result.get("confidence"), (int, float)) else None,
        "model": env("LLM_MODEL", "MiniMax-M3"), "prompt_version": pp.PROMPT_VERSION,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    metrics: list[dict] = []
    for raw_item in result.get("metrics") or []:
        if not isinstance(raw_item, dict):
            continue
        value = raw_item.get("value")
        page = raw_item.get("page")
        quote = str(raw_item.get("raw") or "")[:240]
        if not isinstance(value, (int, float)) or not isinstance(page, int) or page <= 0 or not quote:
            continue
        metric_type = normalize_metric_type(str(raw_item.get("metric_type") or ""), quote)
        if metric_type not in METRICS:
            continue
        value, unit = restore_literal_scale(value, raw_item.get("unit"), quote)
        value_verified = verify_raw_value(value, quote)
        if float(value) == 0 and not zero_literal_matches_unit(unit, quote):
            value_verified = False
        if float(value) == 0 and not value_verified:
            continue
        scope = raw_item.get("scope") if raw_item.get("scope") in SCOPES else None
        underlying = raw_item.get("underlying") or None
        fact_level = raw_item.get("fact_level")
        if fact_level not in FACT_LEVELS:
            fact_level = "underlying" if scope and underlying else ("scope" if scope else "report")
        if fact_level == "report":
            scope = None
            underlying = None
        elif fact_level == "underlying" and not underlying:
            fact_level = "scope" if scope else "report"
        if fact_level == "scope":
            underlying = None
        if fact_level in {"scope", "underlying"} and not scope:
            fact_level = "report"
            underlying = None
        metrics.append({
            "metric_type": metric_type,
            "fact_level": fact_level,
            "scope": scope,
            "underlying": underlying,
            "value": float(value), "currency": raw_item.get("currency") or None,
            "unit": unit,
            "time_basis": raw_item.get("time_basis") if raw_item.get("time_basis") in TIME_BASIS else "period",
            "source_section": raw_item.get("source_section") or None,
            "account_name": raw_item.get("account_name") or None,
            "is_restricted": (
                raw_item.get("is_restricted")
                if isinstance(raw_item.get("is_restricted"), bool) else None
            ),
            "counterparty": raw_item.get("counterparty") or None,
            "raw_text": quote, "page": page,
            "value_verified": value_verified,
            "quote_verified": verify_quote(quote, body), "value_origin": "reported",
        })
    if metrics and top["disclosure_status"] == "提及无数值":
        top["disclosure_status"] = "需复核"
    return top, metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="小批量抽取定期报告")
    ap.add_argument("--sample", default=str(ROOT / "config" / "annual_validation_2025.csv"))
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--report-id", action="append")
    ap.add_argument(
        "--pass",
        dest="pass_names",
        action="append",
        choices=["profile", *pp.METRIC_FAMILIES],
        help="只执行指定短批次；可重复传入。默认执行全部。",
    )
    ap.add_argument("--confirm-llm", action="store_true", help="确认本次会产生模型调用")
    ap.add_argument("--dry-run", action="store_true", help="调用模型但不写数据库")
    args = ap.parse_args()
    if not args.confirm_llm:
        raise SystemExit("为防止意外消耗额度，必须显式添加 --confirm-llm")
    params = {"select": (
                  "report_id,code,name,title,report_period,pdf_url,"
                  "candidate_pages,locator_terms"
              ),
              "status": "eq.located", "order": "publish_date.desc", "limit": str(args.limit)}
    if args.report_id:
        params.pop("status")
        params["report_id"] = f"in.({','.join(args.report_id)})"
    else:
        params["code"] = f"in.({','.join(load_sample_codes(args.sample))})"
    reports = sb_select("periodic_reports", params)
    selected_passes = args.pass_names or ["profile", *pp.METRIC_FAMILIES]
    is_full_run = set(selected_passes) == {"profile", *pp.METRIC_FAMILIES}
    run = []
    for i, report in enumerate(reports, 1):
        log(f"[{i}/{len(reports)}] LLM抽取 {report.get('name')} {report.get('report_period')}")
        content = cninfo.download_pdf(report["pdf_url"])
        if not content:
            raise RuntimeError(f"PDF下载失败: {report['report_id']}")
        located = locate_pdf(content, report.get("locator_terms") or [])
        context = (
            report["title"], report.get("name"), report["code"],
            report["report_period"], located.marked_text,
        )
        profile_result = (
            call_llm(pp.build_profile_messages(*context))
            if "profile" in selected_passes else {}
        )
        metric_results = {
            family: call_llm(pp.build_metric_messages(family, *context))
            for family in pp.METRIC_FAMILIES if family in selected_passes
        }
        result = merge_pass_results(profile_result, metric_results)
        if "pnl" in metric_results:
            deterministic = extract_explicit_pnl_metrics(located.marked_text)
            existing = {
                (
                    item.get("metric_type"),
                    item.get("page"),
                    item.get("value"),
                    item.get("unit"),
                )
                for item in result.get("metrics") or []
                if isinstance(item, dict)
            }
            result.setdefault("metrics", []).extend(
                item for item in deterministic
                if (
                    item["metric_type"],
                    item["page"],
                    item["value"],
                    item["unit"],
                ) not in existing
            )
        top, metrics = normalize(result, located.marked_text)
        accounting_items = normalize_accounting_items(result, located.marked_text)
        top["report_id"] = report["report_id"]
        if not args.dry_run:
            if "profile" in selected_passes:
                sb_upsert("periodic_derivatives", [top], on_conflict="report_id")
                sb_delete("periodic_hedge_accounting_items",
                          {"report_id": f"eq.{report['report_id']}"})
            for family in metric_results:
                if not should_replace_metric_family(is_full_run, family, metrics):
                    log(f"{family} 短批次返回0条，保留数据库中的既有事实")
                    continue
                family_types = ",".join(pp.METRIC_FAMILIES[family])
                sb_delete("periodic_metric_items", {
                    "report_id": f"eq.{report['report_id']}",
                    "metric_type": f"in.({family_types})",
                })
            if metrics:
                sb_insert("periodic_metric_items", [
                    {**item, "report_id": report["report_id"]} for item in metrics])
            if "profile" in selected_passes and accounting_items:
                sb_insert("periodic_hedge_accounting_items", [
                    {**item, "report_id": report["report_id"]} for item in accounting_items])
            if is_full_run:
                sb_update("periodic_reports", {"report_id": f"eq.{report['report_id']}"},
                          {"status": "extracted", "note": None})
        run.append({
            "report": report,
            "extraction": top,
            "metrics": metrics,
            "hedge_accounting_items": accounting_items,
            "raw": {
                "profile": profile_result,
                "metric_passes": metric_results,
            },
        })
        log(
            f"披露状态={top['disclosure_status']}；数值事实={len(metrics)} 条；"
            f"套期会计明细={len(accounting_items)} 条"
        )
    snapshot_json("periodic_extract_run", run)


if __name__ == "__main__":
    main()

