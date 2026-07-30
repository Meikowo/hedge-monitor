#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发现并筛选衍生品相关监管风险文档（M6a POC）。"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
from typing import Any, Iterable

try:
    from scripts.risk_relevance import assess_relevance
    from scripts.risk_sources.sse import iter_documents
except ModuleNotFoundError:  # direct execution: python scripts/fetch_risk_documents.py
    from risk_relevance import assess_relevance
    from risk_sources.sse import iter_documents


def prepare_document(
    document: dict[str, Any],
    text: str = "",
    *,
    fetched: bool = False,
    fetch_note: str | None = None,
) -> dict[str, Any]:
    """Apply the deterministic gate and return a database-ready row."""
    assessment = assess_relevance(
        document.get("title") or "",
        text,
        document.get("source_type") or "other_official",
    )
    raw_metadata = dict(document.get("raw_metadata") or {})
    raw_metadata["rule_relevant"] = assessment.relevant
    if fetched and text:
        terms = assessment.matched_derivative_terms + assessment.matched_risk_terms
        positions = [text.find(term) for term in terms if text.find(term) >= 0]
        if positions:
            start = max(0, min(positions) - 100)
            raw_metadata["gate_excerpt"] = re.sub(
                r"\s+",
                " ",
                text[start:start + 360],
            ).strip()
    row = {
        **document,
        "raw_metadata": raw_metadata,
        "matched_derivative_terms": list(assessment.matched_derivative_terms),
        "matched_risk_terms": list(assessment.matched_risk_terms),
        "status": (
            "candidate"
            if assessment.candidate
            else ("irrelevant" if fetched else "discovered")
        ),
        "note": fetch_note or assessment.reason,
        "text_chars": len(text) if fetched else None,
    }
    if fetched:
        row["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return row


def deduplicate_documents(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last normalized row while preserving first-seen order."""
    order: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_doc_id = row["source_doc_id"]
        if source_doc_id not in by_id:
            order.append(source_doc_id)
        by_id[source_doc_id] = row
    return [by_id[source_doc_id] for source_doc_id in order]


def sanitize_company_codes(
    rows: Iterable[dict[str, Any]],
    known_codes: set[str],
) -> list[dict[str, Any]]:
    """Avoid rejecting official documents for delisted/unknown company codes."""
    out: list[dict[str, Any]] = []
    for row in rows:
        clean = dict(row)
        if clean.get("code") not in known_codes:
            clean["code"] = None
        out.append(clean)
    return out


def persist_documents(
    rows: Iterable[dict[str, Any]],
    known_codes: set[str],
    upsert_fn: Any,
) -> int:
    """Persist normalized rows through the project's idempotent upsert contract."""
    safe_rows = sanitize_company_codes(rows, known_codes)
    return upsert_fn(
        "risk_source_documents",
        safe_rows,
        on_conflict="source_doc_id",
    )


def _html_to_text(content: bytes, encoding: str | None = None) -> str:
    decoded = content.decode(encoding or "utf-8", errors="replace")
    decoded = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", decoded)
    decoded = re.sub(r"(?s)<[^>]+>", " ", decoded)
    return re.sub(r"\s+", " ", html.unescape(decoded)).strip()


def fetch_document_text(
    document: dict[str, Any],
    *,
    session: Any = None,
    max_bytes: int = 30_000_000,
) -> str:
    """Download one official HTML/PDF and extract searchable plain text."""
    import requests

    client = session or requests.Session()
    response = client.get(
        document["document_url"],
        headers={
            "User-Agent": "Mozilla/5.0 hedge-monitor research",
            "Referer": "https://www.sse.com.cn/",
        },
        timeout=45,
    )
    response.raise_for_status()
    content = response.content
    if len(content) > max_bytes:
        raise ValueError(f"document exceeds {max_bytes} bytes")

    if document.get("document_format") == "pdf":
        import fitz

        pdf = fitz.open(stream=content, filetype="pdf")
        try:
            return "\n".join(page.get_text("text") for page in pdf)
        finally:
            pdf.close()
    return _html_to_text(content, response.encoding)


def collect_sse_documents(
    *,
    source_types: list[str],
    start_date: str,
    end_date: str,
    max_pages: int,
    limit: int,
    fetch_body: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_type in source_types:
        for document in iter_documents(
            source_type=source_type,
            start_date=start_date,
            end_date=end_date,
            max_pages=max_pages,
        ):
            text = ""
            fetched = False
            fetch_note = None
            if fetch_body:
                try:
                    text = fetch_document_text(document)
                    fetched = True
                except Exception as exc:  # source failures remain auditable
                    fetch_note = f"正文读取失败: {type(exc).__name__}: {exc}"
            rows.append(
                prepare_document(
                    document,
                    text,
                    fetched=fetched,
                    fetch_note=fetch_note,
                )
            )
            if len(rows) >= limit:
                return deduplicate_documents(rows)
    return deduplicate_documents(rows)


def parse_args() -> argparse.Namespace:
    today = dt.date.today().isoformat()
    parser = argparse.ArgumentParser(
        description="发现上交所衍生品风险监管文档；默认仅生成快照，不写库。"
    )
    parser.add_argument(
        "--source",
        choices=("sse",),
        default="sse",
    )
    parser.add_argument(
        "--kind",
        choices=("inquiry", "regulatory_measure", "all"),
        default="all",
    )
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default=today)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--fetch-body",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source != "sse":
        raise ValueError(f"Unsupported risk source: {args.source}")
    source_types = (
        ["inquiry", "regulatory_measure"]
        if args.kind == "all"
        else [args.kind]
    )
    rows = collect_sse_documents(
        source_types=source_types,
        start_date=args.start_date,
        end_date=args.end_date,
        max_pages=max(1, args.max_pages),
        limit=max(1, args.limit),
        fetch_body=args.fetch_body,
    )

    try:
        from scripts.common import log, sb_select, sb_upsert, snapshot_csv
    except ModuleNotFoundError:
        from common import log, sb_select, sb_upsert, snapshot_csv

    candidates = sum(row["status"] == "candidate" for row in rows)
    log(f"SSE 官方文档 {len(rows)} 条；规则候选 {candidates} 条")
    snapshot_csv("risk_documents_sse", rows)
    if not args.write:
        log("dry-run：未写入 Supabase")
        return

    known_codes = {
        row["code"]
        for row in sb_select(
            "companies",
            {"select": "code"},
            paginate=True,
        )
    }
    count = persist_documents(rows, known_codes, sb_upsert)
    log(f"已幂等写入 risk_source_documents：{count} 条")


if __name__ == "__main__":
    main()
