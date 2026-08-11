#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将已抽取的巨潮官方风险公告投影为正式衍生品风险案例。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable


ALLOWED_ROLES = {"进展", "风险提示"}
DERIVATIVE_TERMS = (
    "套期保值", "套保", "衍生品", "衍生金融工具", "期货", "期权",
    "远期结售汇", "外汇远期", "远期外汇", "掉期", "互换",
)
ACTUAL_LOSS_TERMS = (
    "累计亏损", "累计浮动亏损", "出现亏损", "期货账户出现亏损",
    "已确认损益及浮动亏损金额已达到", "已经给公司带来", "亏损人民币",
    "亏损约", "亏损金额已达到", "损失约",
)
NO_LOSS_TERMS = ("未产生浮动亏损", "未发生亏损", "未产生亏损", "没有发生亏损")
HYPOTHETICAL_TERMS = ("每达到", "若发生", "如发生", "可能造成", "可能导致", "应及时披露")
RISK_TYPE = "重大衍生品损失"


@dataclass(frozen=True)
class CandidateDecision:
    accepted: bool
    reason: str
    loss_quote: str = ""
    loss_page: int | None = None
    evidence_field: str = ""


@dataclass(frozen=True)
class OfficialBundle:
    source: dict[str, Any]
    case: dict[str, Any]
    relation: dict[str, Any]
    evidence: list[dict[str, Any]]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _match_text(value: Any) -> str:
    return re.sub(r"[\s,，、。;；:：\"'“”()（）%％]", "", str(value or ""))


def normalized_quote_in_text(quote: str, text: str) -> bool:
    """Verify a model quote against PDF text while ignoring layout punctuation."""
    needle = _match_text(quote)
    haystack = _match_text(text)
    return bool(needle) and needle in haystack


def find_verified_quote(model_quote: str, pdf_text: str) -> str | None:
    """Locate and return the actual PDF sentence supporting a model excerpt."""
    flat = re.sub(r"\s+", " ", pdf_text).strip()
    anchors = sorted(
        (term for term in ACTUAL_LOSS_TERMS if term in model_quote),
        key=len,
        reverse=True,
    )
    anchors.extend(re.findall(r"[0-9][0-9,，]*(?:\.[0-9]+)?", model_quote))
    match = None
    for anchor in anchors:
        pattern = r"\s*".join(re.escape(char) for char in anchor)
        match = re.search(pattern, flat)
        if match:
            break
    if match is None:
        return None

    previous = max(flat.rfind("。", 0, match.start()), flat.rfind("；", 0, match.start()))
    start = previous + 1 if previous >= 0 else max(0, match.start() - 220)
    endings = [position for position in (
        flat.find("。", match.end()),
        flat.find("；", match.end()),
    ) if position >= 0]
    end = min(endings) + 1 if endings else min(len(flat), match.end() + 260)
    quote = _clean_text(flat[start:end]).strip(" ，,;；")
    return quote if normalized_quote_in_text(quote, pdf_text) else None


def _loss_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in _as_list(row.get("evidence")):
        if not isinstance(item, dict):
            continue
        quote = _clean_text(item.get("quote"))
        if not quote or any(term in quote for term in NO_LOSS_TERMS):
            continue
        if any(term in quote for term in ACTUAL_LOSS_TERMS):
            matches.append(item)
    return matches


def assess_official_candidate(row: dict[str, Any]) -> CandidateDecision:
    if row.get("is_hedge_related") is not True:
        return CandidateDecision(False, "公告未标记为套保相关")
    if row.get("ann_role") not in ALLOWED_ROLES:
        return CandidateDecision(False, "不是进展或风险提示公告")

    evidence = _loss_evidence(row)
    if not evidence:
        return CandidateDecision(False, "没有已发生损失的官方引文")
    selected = evidence[0]
    quote = _clean_text(selected.get("quote"))
    combined = " ".join([
        _clean_text(row.get("title")),
        _clean_text(row.get("summary")),
        quote,
        " ".join(str(item) for item in _as_list(row.get("instruments"))),
    ])
    if not any(term in combined for term in DERIVATIVE_TERMS):
        return CandidateDecision(False, "损失未与衍生品业务直接关联")
    if any(term in quote for term in HYPOTHETICAL_TERMS) and not any(
        term in quote for term in ("已达到", "累计亏损", "出现亏损", "已经给公司带来")
    ):
        return CandidateDecision(False, "仅为假设性或制度披露阈值")
    return CandidateDecision(
        True,
        "官方公告明确披露已发生衍生品损失",
        loss_quote=quote,
        loss_page=selected.get("page") if isinstance(selected.get("page"), int) else None,
        evidence_field=_clean_text(selected.get("field")) or "loss",
    )


def extract_loss_amount(quote: str) -> float | None:
    """Return an exact disclosed loss amount in 万元; thresholds stay null."""
    text = _clean_text(quote)
    if any(term in text for term in ("超过一千万元", "超一千万元", "大于一千万元")):
        return None
    patterns = (
        r"(?:累计(?:浮动)?亏损|亏损(?:金额)?|损失)(?:累计|合计|约|为|达到|已达|人民币|\s)*"
        r"([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(万元|亿元|元)",
        r"(?:人民币\s*)?([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(万元|亿元|元)"
        r"(?:的)?(?:汇兑)?(?:亏损|损失)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        value = float(match.group(1).replace(",", "").replace("，", ""))
        unit = match.group(2)
        if unit == "亿元":
            return round(value * 10_000, 6)
        if unit == "元":
            return round(value / 10_000, 6)
        return value
    return None


def _case_key(row: dict[str, Any]) -> str:
    return f"{row['code']}|{str(row['ann_date'])[:10]}|{RISK_TYPE}|official"


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def build_official_bundle(row: dict[str, Any], *, verified_text: str) -> OfficialBundle:
    decision = assess_official_candidate(row)
    if not decision.accepted:
        raise ValueError(decision.reason)
    official_quote = find_verified_quote(decision.loss_quote, verified_text)
    if not official_quote:
        raise ValueError("损失引文未能在官方 PDF 原文中回验")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    source_doc_id = f"cninfo:{row['ann_id']}"
    case_key = _case_key(row)
    amount = extract_loss_amount(official_quote)
    combined = " ".join((
        _clean_text(row.get("title")),
        _clean_text(row.get("summary")),
        official_quote,
    ))
    source = {
        "source_doc_id": source_doc_id,
        "source_org": "CNINFO",
        "source_type": "company_announcement",
        "official_doc_id": str(row["ann_id"]),
        "code": row["code"],
        "company_name": row.get("name"),
        "title": row["title"],
        "publish_date": str(row["ann_date"])[:10],
        "document_url": row["pdf_url"],
        "document_format": "pdf",
        "content_sha256": hashlib.sha256(verified_text.encode("utf-8")).hexdigest(),
        "text_chars": len(verified_text),
        "matched_derivative_terms": _matched_terms(combined, DERIVATIVE_TERMS),
        "matched_risk_terms": _matched_terms(combined, ACTUAL_LOSS_TERMS),
        "raw_metadata": {
            "announcement_role": row.get("ann_role"),
            "extraction_confidence": row.get("confidence"),
            "loss_evidence_field": decision.evidence_field,
        },
        "status": "extracted",
        "note": decision.reason,
        "fetched_at": now,
    }
    case = {
        "case_key": case_key,
        "code": row["code"],
        "company_name": row.get("name"),
        "event_date": str(row["ann_date"])[:10],
        "first_disclosure_date": str(row["ann_date"])[:10],
        "risk_type": RISK_TYPE,
        "instruments": _as_list(row.get("instruments")),
        "underlyings": _as_list(row.get("underlyings")),
        "summary": _clean_text(row.get("summary"))[:300] or official_quote[:300],
        "amount": amount,
        "currency": "CNY" if amount is not None else None,
        "unit": "万元" if amount is not None else None,
        "regulatory_action": "未见监管措施",
        "outcome": "待后续公告或定期报告确认",
        "case_status": "进行中",
        "confidence": max(float(row.get("confidence") or 0), 0.9),
        "need_review": True,
        "model": "existing-announcement-extraction",
        "prompt_version": "risk-official-v1",
        "extracted_at": now,
    }
    relation = {
        "case_key": case_key,
        "source_doc_id": source_doc_id,
        "relation_type": "supporting",
    }
    extracted_value = (
        f"{amount:g}万元人民币" if amount is not None
        else "达到净利润10%且绝对金额超过1000万元的披露标准"
    )
    evidence = [{
        "case_key": case_key,
        "source_doc_id": source_doc_id,
        "field": "loss",
        "page": decision.loss_page,
        "paragraph": None,
        "quote": official_quote,
        "extracted_value": extracted_value,
        "source_url": row["pdf_url"],
        "quote_verified": True,
        "value_verified": True,
        "confidence": max(float(row.get("confidence") or 0), 0.9),
    }]
    return OfficialBundle(source=source, case=case, relation=relation, evidence=evidence)


def select_publishable(
    rows: Iterable[dict[str, Any]],
    limit: int,
    existing_source_doc_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    existing = existing_source_doc_ids or set()
    accepted = [
        row for row in rows
        if assess_official_candidate(row).accepted
        and f"cninfo:{row['ann_id']}" not in existing
    ]
    accepted.sort(key=lambda row: (str(row.get("ann_date") or ""), str(row.get("ann_id") or "")), reverse=True)
    return accepted[:max(0, limit)]


def _evidence_signature(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("case_key") or ""),
        str(row.get("source_doc_id") or ""),
        str(row.get("field") or ""),
        str(row.get("quote") or ""),
    )


def _matching_media(bundle: OfficialBundle, reports: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    event_date = dt.date.fromisoformat(bundle.case["event_date"])
    matches = []
    for report in reports:
        if report.get("code") != bundle.case["code"] or report.get("risk_type") != "loss":
            continue
        if report.get("publish_status") not in {"published", "corroborated"}:
            continue
        try:
            media_date = dt.date.fromisoformat(str(report.get("event_date"))[:10])
        except ValueError:
            continue
        if abs((media_date - event_date).days) <= 14:
            matches.append(report)
    return matches


def persist_bundles(
    bundles: list[OfficialBundle],
    *,
    existing_evidence: Iterable[dict[str, Any]],
    media_reports: Iterable[dict[str, Any]],
    upsert_fn: Callable[..., int],
    insert_fn: Callable[..., int],
    update_fn: Callable[..., None],
) -> dict[str, int]:
    if not bundles:
        return {"sources": 0, "cases": 0, "relations": 0, "evidence_inserted": 0, "media_corroborated": 0}
    source_count = upsert_fn(
        "risk_source_documents", [item.source for item in bundles], on_conflict="source_doc_id"
    )
    case_count = upsert_fn(
        "derivative_risk_cases", [item.case for item in bundles], on_conflict="case_key"
    )
    relation_count = upsert_fn(
        "risk_case_documents", [item.relation for item in bundles], on_conflict="case_key,source_doc_id"
    )
    signatures = {_evidence_signature(row) for row in existing_evidence}
    new_evidence = [
        row for bundle in bundles for row in bundle.evidence
        if _evidence_signature(row) not in signatures
    ]
    evidence_count = insert_fn("risk_case_evidence", new_evidence) if new_evidence else 0
    media_count = 0
    for bundle in bundles:
        for report in _matching_media(bundle, media_reports):
            update_fn(
                "risk_media_reports",
                {"media_key": f"eq.{report['media_key']}"},
                {
                    "verification_status": "officially_corroborated",
                    "official_case_key": bundle.case["case_key"],
                    "publish_status": "corroborated",
                },
            )
            media_count += 1
    return {
        "sources": source_count,
        "cases": case_count,
        "relations": relation_count,
        "evidence_inserted": evidence_count,
        "media_corroborated": media_count,
    }


def fetch_pdf_text(url: str) -> str:
    import pymupdf as fitz
    import requests

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 hedge-monitor research", "Referer": "https://www.cninfo.com.cn/"},
        timeout=60,
    )
    response.raise_for_status()
    if len(response.content) > 30_000_000:
        raise ValueError("official PDF exceeds 30 MB")
    pdf = fitz.open(stream=response.content, filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in pdf)
    finally:
        pdf.close()


def load_candidate_rows(select_fn: Callable[..., list[dict[str, Any]]]) -> list[dict[str, Any]]:
    extractions = select_fn(
        "extractions",
        {
            "select": "ann_id,is_hedge_related,ann_role,instruments,underlyings,summary,confidence,evidence",
            "is_hedge_related": "eq.true",
            "ann_role": "in.(进展,风险提示)",
        },
        paginate=True,
    )
    by_id = {str(row["ann_id"]): row for row in extractions}
    announcements: list[dict[str, Any]] = []
    ids = list(by_id)
    for start in range(0, len(ids), 250):
        chunk = ids[start:start + 250]
        announcements.extend(select_fn(
            "announcements",
            {
                "select": "ann_id,code,name,title,ann_date,pdf_url",
                "ann_id": f"in.({','.join(chunk)})",
            },
        ))
    return [
        {**announcement, **by_id[str(announcement["ann_id"])]}
        for announcement in announcements
        if str(announcement.get("ann_id")) in by_id and announcement.get("pdf_url")
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="发布经官方 PDF 引文回验的衍生品风险案例")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from scripts.common import log, sb_insert, sb_select, sb_update, sb_upsert, snapshot_json
    except ModuleNotFoundError:
        from common import log, sb_insert, sb_select, sb_update, sb_upsert, snapshot_json

    existing_source_doc_ids = {
        str(row["source_doc_id"])
        for row in sb_select(
            "risk_source_documents",
            {"select": "source_doc_id"},
            paginate=True,
        )
    }
    rows = load_candidate_rows(sb_select)
    candidates = select_publishable(
        rows,
        limit=max(1, args.limit),
        existing_source_doc_ids=existing_source_doc_ids,
    )
    if not candidates:
        snapshot_json("official_risk_cases", {"selected": [], "rejected": []})
        log("No unpublished official risk case candidates; completed as a normal no-op")
        return
    bundles: list[OfficialBundle] = []
    rejected: list[dict[str, str]] = []
    for row in candidates:
        try:
            text = fetch_pdf_text(row["pdf_url"])
            bundles.append(build_official_bundle(row, verified_text=text))
        except Exception as exc:
            rejected.append({"ann_id": str(row.get("ann_id")), "reason": f"{type(exc).__name__}: {exc}"})

    snapshot_json("official_risk_cases", {
        "selected": [{"case": item.case, "source": item.source, "evidence": item.evidence} for item in bundles],
        "rejected": rejected,
    })
    log(f"官方风险候选 {len(candidates)} 条；PDF 回验通过 {len(bundles)} 条；失败 {len(rejected)} 条")
    if not args.write:
        log("dry-run：未写入 Supabase")
        return
    if not bundles:
        raise RuntimeError("没有通过官方 PDF 引文回验的案例，拒绝写库")

    existing_evidence = sb_select(
        "risk_case_evidence",
        {"select": "case_key,source_doc_id,field,quote"},
        paginate=True,
    )
    media_reports = sb_select(
        "risk_media_reports",
        {"select": "media_key,code,event_date,risk_type,publish_status"},
        paginate=True,
    )
    result = persist_bundles(
        bundles,
        existing_evidence=existing_evidence,
        media_reports=media_reports,
        upsert_fn=sb_upsert,
        insert_fn=sb_insert,
        update_fn=sb_update,
    )
    log(f"正式官方案例写入完成：{result}")


if __name__ == "__main__":
    main()
