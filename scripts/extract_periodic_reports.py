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
from common import ROOT, env, log, sb_delete, sb_insert, sb_select, sb_update, sb_upsert, snapshot_json, warn
from extract_announcements import call_llm, verify_quote
from periodic_pdf import (
    TABLE_CONTROLLED_METRICS,
    extract_derivative_note_metrics,
    extract_derivative_table_metrics,
    locate_pdf,
)

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
LEGACY_METRIC_TYPES = ("period_pnl",)
POLICY_ONLY_ACCOUNTING_MARKERS = (
    "本公司的套期包括",
    "本公司套期包括",
    "本集团的套期主要包括",
    "套期会计方法包括",
    "套期分为",
    "除现金流量套期中属于套期有效的部分",
)


def call_periodic_llm(messages: list[dict]) -> dict:
    """定期报告固定关闭 thinking，避免本地环境遗漏导致只有思考块。"""
    return call_llm(messages, thinking_setting="off")


def _list(value) -> list[str]:
    nullish = {"none", "null", "n/a", "未提及", "无"}
    return list(dict.fromkeys(str(x).strip() for x in (value or [])
                              if str(x).strip() and str(x).strip().lower() not in nullish))


def normalize_account_key(value: str | None) -> str:
    """去掉报表科目前的序号，避免同一事实因“（九）”等前缀重复入库。"""
    return re.sub(
        r"^\s*(?:[（(][一二三四五六七八九十百0-9]+[）)]|"
        r"[一二三四五六七八九十百0-9]+[、.．])\s*",
        "",
        value or "",
    ).strip()


def normalize_summary(
    summary: str | None,
    scopes: list[str],
    disclosure_status: str,
    accounting_status: str,
    non_application_reason: str | None,
) -> str | None:
    """结构化套期会计结论优先于模型生成的自然语言摘要。"""
    text = (summary or "").strip()
    if disclosure_status == "未提及":
        accounting_text = (
            "；未应用套期会计"
            if accounting_status == "未应用"
            else ""
        )
        return f"报告期未发现衍生品业务披露{accounting_text}。"
    applied_claims = ("采用套期会计", "应用套期会计", "套期会计核算")
    if accounting_status != "未应用" or not any(x in text for x in applied_claims):
        return text[:300] or None
    scope_text = "、".join(scopes)
    subject = f"{scope_text}衍生品业务" if scope_text else "衍生品业务"
    result = f"报告期披露{subject}；未应用套期会计。"
    if non_application_reason:
        result += f"未应用原因：{non_application_reason}。"
    return result[:300]


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
    "百万元": ("元", 1_000_000),
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
        r"([-+]?[0-9][0-9,]*(?:\.[0-9]+)?)\s*(千元|万元|百万元|亿元|万美元|亿美元)",
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


def normalize_metric_type(
    metric_type: str,
    quote: str,
    source_section: str = "",
    account_name: str = "",
) -> str:
    """用原文纠正容易混淆的峰值口径。"""
    if (
        metric_type == "notional_peak_reported"
        and "保证金" in quote
        and any(term in quote for term in ("最高", "最大", "任意时点"))
    ):
        return "margin_peak_reported"
    if (
        metric_type == "reported_derivative_comprehensive_pnl"
        and account_name == "处置损益"
        and "衍生品投资情况" in source_section
    ):
        return "derivative_disposal_investment_income"
    return metric_type


def should_skip_reviewed(review_status: str | None, force_reviewed: bool) -> bool:
    """人工已接受的金标准默认不被后续模型运行覆盖。"""
    return review_status == "accepted" and not force_reviewed


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
        page_body = page_match.group("body")
        page_body = re.sub(
            r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])",
            "",
            page_body,
        )
        for match in pnl_pattern.finditer(page_body):
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
        actual_pattern = re.compile(
            r"(?P<raw>(?P<label>[^，。\n]{0,40}?)"
            r"报告期内实际损益(?:金额)?为"
            r"(?P<value>[-−]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)\s*"
            r"(?P<unit>亿美元|万美元|美元|亿元|万元|千元|元))"
        )
        for match in actual_pattern.finditer(page_body):
            label = match.group("label")
            if "期货" in label or "商品" in label:
                scope = "商品"
            elif any(term in label for term in ("远期", "外汇", "汇率", "货币")):
                scope = "外汇"
            elif "利率" in label:
                scope = "利率"
            else:
                scope = None
            value = float(
                match.group("value").replace("−", "-").replace(" ", "").replace(",", "")
            )
            unit = match.group("unit")
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
        section_amount_pattern = re.compile(
            r"报告期实际损益情况的说明\s*"
            r"(?P<raw>实际损益(?:金额)?为\s*"
            r"(?P<value>[-−]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)\s*"
            r"(?P<unit>亿美元|万美元|美元|亿元|万元|千元|元))"
        )
        for match in section_amount_pattern.finditer(page_body):
            value = float(
                match.group("value").replace("−", "-").replace(" ", "").replace(",", "")
            )
            unit = match.group("unit")
            metrics.append({
                "metric_type": "reported_derivative_comprehensive_pnl",
                "fact_level": "report",
                "scope": None,
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
        actual_loss_pattern = re.compile(
            r"报告期实际损益情况的说明\s*"
            r"(?P<raw>(?:报告期内[，,]?\s*)?"
            r"(?P<label>[^。\n]{0,40}?)"
            r"(?:实际产生损益|确认投资收益)\s*(?:为)?\s*"
            r"(?P<value>[-−]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)\s*"
            r"(?P<unit>亿美元|万美元|美元|亿元|万元|千元|元))"
        )
        for match in actual_loss_pattern.finditer(page_body):
            label = match.group("label")
            if "利率" in label:
                scope = "利率"
            elif "期货" in label or "商品" in label:
                scope = "商品"
            elif any(term in label for term in ("远期", "外汇", "汇率", "货币")):
                scope = "外汇"
            else:
                scope = None
            value = float(
                match.group("value").replace("−", "-").replace(" ", "").replace(",", "")
            )
            unit = match.group("unit")
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


def should_purge_legacy_metrics(is_full_run: bool) -> bool:
    return is_full_run


def merge_table_metrics(
    result: dict,
    table_metrics: list[dict],
    table_pages: set[int],
    selected_passes: list[str],
) -> dict:
    selected_types = {
        metric_type
        for family in selected_passes
        for metric_type in pp.METRIC_FAMILIES.get(family, ())
    }
    merged = dict(result)
    merged["metrics"] = [
        item for item in result.get("metrics") or []
        if not (
            isinstance(item, dict)
            and item.get("page") in table_pages
            and item.get("metric_type") in TABLE_CONTROLLED_METRICS
        )
    ]
    merged["metrics"].extend(
        item for item in table_metrics
        if item.get("metric_type") in selected_types
    )
    return merged


def merge_verified_note_metrics(
    result: dict,
    note_metrics: list[dict],
    selected_passes: list[str],
) -> dict:
    selected_types = {
        metric_type
        for family in selected_passes
        for metric_type in pp.METRIC_FAMILIES.get(family, ())
    }
    selected_notes = [
        item for item in note_metrics
        if item.get("metric_type") in selected_types
    ]
    verified_keys = {
        (item.get("metric_type"), item.get("page"))
        for item in selected_notes
    }
    merged = dict(result)
    merged["metrics"] = [
        item for item in result.get("metrics") or []
        if not (
            isinstance(item, dict)
            and (item.get("metric_type"), item.get("page")) in verified_keys
        )
    ]
    merged["metrics"].extend(selected_notes)
    return merged


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
    no_derivative_phrase = next(
        (
            phrase for phrase in (
                "报告期不存在衍生品投资",
                "报告期内不存在衍生品投资",
                "本报告期不存在衍生品投资",
            )
            if phrase in (body or "")
        ),
        None,
    )
    if no_derivative_phrase:
        page, quote = find_page_evidence(body, no_derivative_phrase)
        return [{
            "scope": None,
            "instrument": None,
            "underlying_asset": None,
            "application_status": "未应用",
            "accounting_type": None,
            "non_application_reason": "报告期不存在衍生品投资",
            "source_section": "衍生品投资情况",
            "page": page,
            "quote": quote,
            "quote_verified": True,
            "confidence": 1.0,
            "need_review": False,
        }]
    items: list[dict] = []
    for raw_item in result.get("hedge_accounting_items") or []:
        if not isinstance(raw_item, dict):
            continue
        status = raw_item.get("application_status")
        status = status if status in ACCOUNTING_ITEM_STATUS else "需复核"
        accounting_type = raw_item.get("accounting_type")
        accounting_type = accounting_type if accounting_type in HEDGE_ACCOUNTING_TYPES else None
        if status != "已应用":
            accounting_type = None
        page = raw_item.get("page")
        page = page if isinstance(page, int) and page > 0 else None
        quote = str(raw_item.get("quote") or "")[:240] or None
        if (
            quote
            and any(marker in quote for marker in POLICY_ONLY_ACCOUNTING_MARKERS)
        ):
            continue
        quote_verified = verify_quote(quote, body) if quote else None
        if status == "已应用" and not any(
            term in (quote or "")
            for term in (
                "套期会计",
                "现金流量套期",
                "公允价值套期",
                "套期储备",
                "指定为套期工具",
            )
        ):
            continue
        if status == "未应用" and not any(
            term in (quote or "")
            for term in (
                "未应用套期会计",
                "不适用",
                "未被指定为套期工具",
                "不符合套期会计",
                "不存在衍生品投资",
            )
        ):
            continue
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
    items = [
        item for item in items
        if item["quote_verified"] is True
    ]
    checkbox_page, checkbox_quote = find_non_application_checkbox(body)
    if checkbox_page:
        verified_unapplied = [
            item for item in items
            if item["application_status"] == "未应用"
            and item["quote_verified"] is True
        ]
        if verified_unapplied:
            return verified_unapplied
        return [{
            "scope": None,
            "instrument": None,
            "underlying_asset": None,
            "application_status": "未应用",
            "accounting_type": None,
            "non_application_reason": None,
            "source_section": "套期",
            "page": checkbox_page,
            "quote": checkbox_quote,
            "quote_verified": True,
            "confidence": 1.0,
            "need_review": False,
        }]
    cash_flow_page, cash_flow_quote = find_page_evidence(
        body,
        "现金流量套期储备",
        require_numeric=True,
    )
    if cash_flow_page and not any(
        item["application_status"] == "已应用"
        and item["accounting_type"] == "现金流量套期"
        for item in items
    ):
        items.append({
            "scope": None,
            "instrument": None,
            "underlying_asset": None,
            "application_status": "已应用",
            "accounting_type": "现金流量套期",
            "non_application_reason": None,
            "source_section": "其他综合收益",
            "page": cash_flow_page,
            "quote": cash_flow_quote,
            "quote_verified": True,
            "confidence": 1.0,
            "need_review": False,
        })
    decisive_scopes = {
        item["scope"]
        for item in items
        if item["application_status"] in {"已应用", "未应用"}
    }
    return [
        item for item in items
        if not (
            item["application_status"] == "未明确披露"
            and item["scope"] in decisive_scopes
        )
    ]


def find_page_evidence(
    body: str,
    term: str,
    *,
    require_numeric: bool = False,
) -> tuple[int | None, str | None]:
    for match in re.finditer(
        r"【P(?P<page>\d+)】(?P<body>.*?)(?=【P\d+】|\Z)",
        body or "",
        flags=re.S,
    ):
        page_body = match.group("body")
        if term not in page_body:
            continue
        numeric_evidence = None
        if require_numeric:
            numeric_evidence = re.search(
                re.escape(term)
                + (
                    r"(?:\s+[-+]?(?:"
                    r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?"
                    r"|[0-9]+\.[0-9]+)){1,8}"
                ),
                page_body,
            )
            if not numeric_evidence:
                continue
        quote = (
            re.sub(r"\s+", " ", numeric_evidence.group(0)).strip()
            if numeric_evidence
            else next(
                (
                    line.strip()
                    for line in page_body.splitlines()
                    if term in line and line.strip()
                ),
                term,
            )
        )
        return int(match.group("page")), quote[:240]
    return None, None


def find_non_application_checkbox(body: str) -> tuple[int | None, str | None]:
    for match in re.finditer(
        r"【P(?P<page>\d+)】(?P<body>.*?)(?=【P\d+】|\Z)",
        body or "",
        flags=re.S,
    ):
        compact = re.sub(r"\s+", "", match.group("body"))
        heading = re.search(
            r"公司开展符合条件套期业务并应用套期会计",
            compact,
        )
        if not heading:
            continue
        tail = compact[heading.end():heading.end() + 50]
        checked = re.match(
            r"(?:[□☐]适用[√✓☑■]不适用|"
            r"适用[□☐][√✓☑■]?不适用|"
            r"[□☐]?适用不适用[√✓☑■])",
            tail,
        )
        plain = re.match(r"[:：]?不适用(?:[。；;]|$)", tail)
        if checked or plain:
            end = heading.end() + (checked or plain).end()
            return int(match.group("page")), compact[heading.start():end][:240]
    return None, None


def promote_verified_accounting_evidence(
    top: dict,
    accounting_items: list[dict],
) -> None:
    status_map = {
        "已应用": "已应用",
        "未应用": "未应用",
    }
    target_status = status_map.get(top.get("hedge_accounting_status"))
    if not target_status:
        return
    verified = next(
        (
            item for item in accounting_items
            if item.get("application_status") == target_status
            and item.get("quote_verified") is True
            and item.get("quote")
        ),
        None,
    )
    if not verified:
        return
    top["hedge_accounting_page"] = verified.get("page")
    top["hedge_accounting_quote"] = verified.get("quote")
    top["hedge_accounting_quote_verified"] = True
    if verified.get("non_application_reason"):
        top["non_application_reason"] = verified["non_application_reason"]


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
    if accounting_status in {"未应用", "未明确披露"}:
        legacy_accounting = []
        accounting_types = []
    accounting_evidence = result.get("hedge_accounting_evidence")
    accounting_evidence = accounting_evidence if isinstance(accounting_evidence, dict) else {}
    accounting_page = accounting_evidence.get("page")
    accounting_page = accounting_page if isinstance(accounting_page, int) and accounting_page > 0 else None
    accounting_quote = str(accounting_evidence.get("quote") or "")[:240] or None
    if (
        accounting_quote
        and any(marker in accounting_quote for marker in POLICY_ONLY_ACCOUNTING_MARKERS)
    ):
        cash_flow_page, cash_flow_quote = find_page_evidence(
            body,
            "现金流量套期储备",
            require_numeric=True,
        )
        if cash_flow_page:
            legacy_accounting = ["现金流量套期"]
            accounting_types = ["现金流量套期"]
            accounting_status = "已应用"
            accounting_page = cash_flow_page
            accounting_quote = cash_flow_quote
        else:
            legacy_accounting = []
            accounting_types = []
            accounting_status = "未明确披露"
            accounting_page = None
            accounting_quote = None
    if accounting_status == "已应用" and accounting_types == ["现金流量套期"]:
        cash_flow_page, cash_flow_quote = find_page_evidence(
            body,
            "现金流量套期储备",
            require_numeric=True,
        )
        if cash_flow_page:
            accounting_page = cash_flow_page
            accounting_quote = cash_flow_quote
    no_derivative_phrase = next(
        (
            phrase for phrase in (
                "报告期不存在衍生品投资",
                "报告期内不存在衍生品投资",
                "本报告期不存在衍生品投资",
            )
            if phrase in (body or "")
        ),
        None,
    )
    if (
        status == "未提及"
        and no_derivative_phrase
    ):
        status = "提及无数值"
    if no_derivative_phrase:
        no_derivative_page, no_derivative_quote = find_page_evidence(
            body,
            no_derivative_phrase,
        )
        accounting_status = "未应用"
        accounting_types = []
        legacy_accounting = []
        accounting_page = no_derivative_page
        accounting_quote = no_derivative_quote
        if not result.get("non_application_reason"):
            result = {
                **result,
                "non_application_reason": "报告期不存在衍生品投资",
            }
    checkbox_page, checkbox_quote = find_non_application_checkbox(body)
    if checkbox_page:
        accounting_status = "未应用"
        accounting_types = []
        legacy_accounting = []
        accounting_page = checkbox_page
        accounting_quote = checkbox_quote
        result = {**result, "non_application_reason": None}
    normalized_scopes = [x for x in _list(result.get("scopes")) if x in SCOPES]
    non_application_reason = result.get("non_application_reason") or None
    top = {
        "disclosure_status": status,
        "scopes": normalized_scopes,
        "instruments": _list(result.get("instruments")),
        "underlyings": _list(result.get("underlyings")),
        "purpose": (result.get("purpose") or None),
        "hedge_accounting": legacy_accounting or accounting_types,
        "hedge_accounting_status": accounting_status,
        "hedge_accounting_types": accounting_types,
        "non_application_reason": non_application_reason,
        "hedge_accounting_page": accounting_page,
        "hedge_accounting_quote": accounting_quote,
        "hedge_accounting_quote_verified": (
            verify_quote(accounting_quote, body) if accounting_quote else None
        ),
        "summary": normalize_summary(
            result.get("summary"),
            normalized_scopes,
            status,
            accounting_status,
            non_application_reason,
        ),
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "confidence": float(result["confidence"]) if isinstance(result.get("confidence"), (int, float)) else None,
        "model": env("LLM_MODEL", "MiniMax-M3"), "prompt_version": pp.PROMPT_VERSION,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    has_verified_business_table = any(
        isinstance(item, dict)
        and item.get("table_cell_verified") is True
        and item.get("source_section") == "衍生品投资情况"
        for item in (result.get("metrics") or [])
    )
    has_verified_explicit_derivative_note = any(
        isinstance(item, dict)
        and item.get("table_cell_verified") is True
        and item.get("source_section") in {
            "投资收益",
            "公允价值变动收益",
            "公允价值披露",
        }
        and any(
            marker in str(item.get("raw") or "")
            for marker in ("衍生金融工具", "衍生金融资产", "衍生金融负债")
        )
        for item in (result.get("metrics") or [])
    )
    metrics: list[dict] = []
    for raw_item in result.get("metrics") or []:
        if not isinstance(raw_item, dict):
            continue
        value = raw_item.get("value")
        page = raw_item.get("page")
        quote = str(raw_item.get("raw") or "")[:240]
        if not isinstance(value, (int, float)) or not isinstance(page, int) or page <= 0 or not quote:
            continue
        source_section = str(raw_item.get("source_section") or "")
        account_name = str(raw_item.get("account_name") or "")
        metric_type = normalize_metric_type(
            str(raw_item.get("metric_type") or ""),
            quote,
            source_section,
            account_name,
        )
        if metric_type not in METRICS:
            continue
        derivative_context = " ".join((quote, source_section, account_name))
        if (
            metric_type == "derivative_disposal_investment_income"
            and not any(
                marker in derivative_context
                for marker in (
                    "衍生", "期货", "期权", "远期", "掉期", "互换", "套期", "T+D",
                )
            )
        ):
            continue
        if metric_type == "margin_end_cash":
            if "黄金租赁" in derivative_context or "租借黄金" in derivative_context:
                continue
            if not any(
                marker in derivative_context
                for marker in (
                    "衍生", "期货", "期权", "远期", "结售汇", "掉期", "互换", "T+D",
                )
            ):
                continue
        value, unit = restore_literal_scale(value, raw_item.get("unit"), quote)
        value_verified = verify_raw_value(value, quote)
        if float(value) == 0 and not zero_literal_matches_unit(unit, quote):
            value_verified = False
        if float(value) == 0 and not value_verified:
            continue
        if not value_verified:
            continue
        scope = raw_item.get("scope") if raw_item.get("scope") in SCOPES else None
        inferred_scope = False
        if metric_type in {
            "reported_derivative_comprehensive_pnl",
            "derivative_disposal_investment_income",
        } and scope is None:
            has_commodity = any(
                term in derivative_context for term in ("商品", "期货", "T+D")
            )
            has_fx = any(
                term in derivative_context for term in ("外汇", "汇率", "远期")
            )
            if has_commodity != has_fx:
                scope = "商品" if has_commodity else "外汇"
                inferred_scope = True
        underlying = raw_item.get("underlying") or None
        fact_level = raw_item.get("fact_level")
        if inferred_scope and fact_level == "report":
            fact_level = "scope"
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
        quote_verified = (
            True if raw_item.get("table_cell_verified") is True
            else verify_quote(quote, body)
        )
        if quote_verified is not True:
            continue
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
            "quote_verified": quote_verified,
            "value_origin": "reported",
        })
    deduplicated: list[dict] = []
    seen_metrics: set[tuple] = set()
    for item in metrics:
        key = (
            item["metric_type"], item["fact_level"], item["scope"],
            item["underlying"], item["value"], item["currency"], item["unit"],
            item["time_basis"], normalize_account_key(item["account_name"]), item["page"],
        )
        if key in seen_metrics:
            continue
        seen_metrics.add(key)
        deduplicated.append(item)
    metrics = deduplicated
    if metrics and top["disclosure_status"] in {"提及无数值", "未提及"}:
        has_profile_hedge_context = bool(top["scopes"] or top["purpose"])
        top["disclosure_status"] = "有数值" if (
            has_verified_business_table
            or (has_verified_explicit_derivative_note and has_profile_hedge_context)
        ) else "需复核"
    return top, metrics


def build_report_query(
    sample: str,
    limit: int,
    report_ids: list[str] | None = None,
    fiscal_year: int = 2025,
    report_type: str = "annual",
) -> dict[str, str]:
    params = {
        "select": (
            "report_id,code,name,title,report_period,pdf_url,"
            "candidate_pages,locator_terms,status,note"
        ),
        "status": "eq.located",
        "order": "publish_date.desc",
        "limit": str(limit),
        "fiscal_year": f"eq.{fiscal_year}",
        "report_type": f"eq.{report_type}",
    }
    if report_ids:
        params.pop("status")
        params.pop("limit")
        params["report_id"] = f"in.({','.join(report_ids)})"
    else:
        params["code"] = f"in.({','.join(load_sample_codes(sample))})"
    return params


def claim_report(report_id: str, dry_run: bool = False) -> None:
    """在模型调用前持久化领取；硬终止时报告保持 failed，等待人工恢复。"""
    if not dry_run:
        sb_update(
            "periodic_reports",
            {"report_id": f"eq.{report_id}"},
            {
                "status": "failed",
                "note": "抽取处理中；异常中断时需人工重试",
            },
        )


def restore_report_state(report: dict, dry_run: bool = False) -> None:
    """选择性短批次成功后恢复运行前可见性状态。"""
    if not dry_run:
        sb_update(
            "periodic_reports",
            {"report_id": f"eq.{report['report_id']}"},
            {
                "status": report.get("status") or "located",
                "note": report.get("note"),
            },
        )


def quarantine_report(
    report_id: str,
    error: Exception,
    dry_run: bool = False,
) -> None:
    """隔离单份失败报告，避免定时任务反复消耗模型额度。"""
    note = f"抽取失败: {type(error).__name__}: {error}"[:500]
    warn(f"{report_id} {note}")
    if not dry_run:
        sb_update(
            "periodic_reports",
            {"report_id": f"eq.{report_id}"},
            {"status": "failed", "note": note},
        )


def record_report_failure(
    report: dict,
    completed_runs: list[dict],
    error: Exception,
    dry_run: bool = False,
) -> None:
    """失败快照与状态说明分别尽力写入，不遮蔽原始异常。"""
    try:
        snapshot_json("periodic_extract_run", [
            *completed_runs,
            {
                "report": report,
                "error": f"{type(error).__name__}: {error}"[:500],
            },
        ])
    except Exception as snapshot_error:
        warn(f"{report['report_id']} 失败快照写入失败: {snapshot_error}")
    try:
        quarantine_report(report["report_id"], error, dry_run)
    except Exception as quarantine_error:
        warn(f"{report['report_id']} 隔离说明更新失败: {quarantine_error}")


def extract_one_report(
    report: dict,
    selected_passes: list[str],
    is_full_run: bool,
    dry_run: bool,
) -> dict:
    content = cninfo.download_pdf(report["pdf_url"])
    if not content:
        raise RuntimeError(f"PDF下载失败: {report['report_id']}")
    located = locate_pdf(content, report.get("locator_terms") or [])
    context = (
        report["title"], report.get("name"), report["code"],
        report["report_period"], located.marked_text,
    )
    profile_result = (
        call_periodic_llm(pp.build_profile_messages(*context))
        if "profile" in selected_passes else {}
    )
    metric_results = {
        family: call_periodic_llm(pp.build_metric_messages(family, *context))
        for family in pp.METRIC_FAMILIES if family in selected_passes
    }
    result = merge_pass_results(profile_result, metric_results)
    table_metrics, table_pages = extract_derivative_table_metrics(
        content,
        located.candidate_pages,
    )
    result = merge_table_metrics(
        result,
        table_metrics,
        table_pages,
        selected_passes,
    )
    result = merge_verified_note_metrics(
        result,
        extract_derivative_note_metrics(content, located.candidate_pages),
        selected_passes,
    )
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
    promote_verified_accounting_evidence(top, accounting_items)
    top["report_id"] = report["report_id"]
    if not dry_run:
        if "profile" in selected_passes:
            sb_upsert("periodic_derivatives", [top], on_conflict="report_id")
            sb_delete(
                "periodic_hedge_accounting_items",
                {"report_id": f"eq.{report['report_id']}"},
            )
        if should_purge_legacy_metrics(is_full_run):
            legacy_types = ",".join(LEGACY_METRIC_TYPES)
            sb_delete("periodic_metric_items", {
                "report_id": f"eq.{report['report_id']}",
                "metric_type": f"in.({legacy_types})",
            })
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
                {**item, "report_id": report["report_id"]} for item in metrics
            ])
        if "profile" in selected_passes and accounting_items:
            sb_insert("periodic_hedge_accounting_items", [
                {**item, "report_id": report["report_id"]}
                for item in accounting_items
            ])
        if is_full_run:
            sb_update(
                "periodic_reports",
                {"report_id": f"eq.{report['report_id']}"},
                {"status": "extracted", "note": None},
            )
    return {
        "report": report,
        "extraction": top,
        "metrics": metrics,
        "hedge_accounting_items": accounting_items,
        "raw": {
            "profile": profile_result,
            "metric_passes": metric_results,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="小批量抽取定期报告")
    ap.add_argument("--sample", default=str(ROOT / "config" / "annual_validation_2025.csv"))
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--report-id", action="append")
    ap.add_argument("--fiscal-year", type=int, default=2025)
    ap.add_argument(
        "--report-type",
        choices=["annual", "semiannual"],
        default="annual",
    )
    ap.add_argument(
        "--pass",
        dest="pass_names",
        action="append",
        choices=["profile", *pp.METRIC_FAMILIES],
        help="只执行指定短批次；可重复传入。默认执行全部。",
    )
    ap.add_argument("--confirm-llm", action="store_true", help="确认本次会产生模型调用")
    ap.add_argument("--dry-run", action="store_true", help="调用模型但不写数据库")
    ap.add_argument(
        "--force-reviewed",
        action="store_true",
        help="允许覆盖 review_status=accepted 的人工金标准；默认保护。",
    )
    args = ap.parse_args()
    if not args.confirm_llm:
        raise SystemExit("为防止意外消耗额度，必须显式添加 --confirm-llm")
    params = build_report_query(
        args.sample,
        args.limit,
        args.report_id,
        fiscal_year=args.fiscal_year,
        report_type=args.report_type,
    )
    reports = sb_select("periodic_reports", params)
    review_status_by_report: dict[str, str] = {}
    if reports:
        review_rows = sb_select("periodic_derivatives", {
            "select": "report_id,review_status",
            "report_id": f"in.({','.join(row['report_id'] for row in reports)})",
        })
        review_status_by_report = {
            row["report_id"]: row.get("review_status")
            for row in review_rows
        }
    selected_passes = args.pass_names or ["profile", *pp.METRIC_FAMILIES]
    is_full_run = set(selected_passes) == {"profile", *pp.METRIC_FAMILIES}
    run = []
    for i, report in enumerate(reports, 1):
        if should_skip_reviewed(
            review_status_by_report.get(report["report_id"]),
            args.force_reviewed,
        ):
            log(
                f"[{i}/{len(reports)}] 跳过人工已接受金标准 "
                f"{report.get('name')}；如需重跑请显式 --force-reviewed"
            )
            continue
        log(f"[{i}/{len(reports)}] LLM抽取 {report.get('name')} {report.get('report_period')}")
        claim_report(report["report_id"], args.dry_run)
        try:
            report_run = extract_one_report(
                report,
                selected_passes,
                is_full_run,
                args.dry_run,
            )
        except Exception as exc:
            record_report_failure(report, run, exc, args.dry_run)
            raise
        if not is_full_run:
            restore_report_state(report, args.dry_run)
        run.append(report_run)
        top = report_run["extraction"]
        metrics = report_run["metrics"]
        accounting_items = report_run["hedge_accounting_items"]
        log(
            f"披露状态={top['disclosure_status']}；数值事实={len(metrics)} 条；"
            f"套期会计明细={len(accounting_items)} 条"
        )
    snapshot_json("periodic_extract_run", run)


if __name__ == "__main__":
    main()
