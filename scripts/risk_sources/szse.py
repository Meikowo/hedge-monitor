#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shenzhen Stock Exchange official supervision-list adapter."""
from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit


SZSE_SITE_URL = "https://www.szse.cn"
SZSE_DOC_URL = "https://reportdocs.static.szse.cn"
SZSE_REPORT_URL = f"{SZSE_SITE_URL}/api/report/ShowReport/data"
LIST_PATHS = {
    "inquiry": "/disclosure/supervision/inquire/index.html",
    "regulatory_measure": "/disclosure/supervision/measure/measure/index.html",
    "disciplinary_action": "/disclosure/supervision/measure/pushish/index.html",
}
CATALOG_IDS = {
    "inquiry": "main_wxhj",
    "regulatory_measure": "1800_jgxxgk",
    "disciplinary_action": "1800_jgxxgk_cf",
}
FIELD_MAP = {
    "inquiry": {
        "code": "gsdm", "company_name": "gsjc", "publish_date": "fhrq",
        "category": "hjlb", "link": "ck", "objects": "hfck",
    },
    "regulatory_measure": {
        "code": "gkxx_gsdm", "company_name": "gkxx_gsjc", "publish_date": "gkxx_gdrq",
        "category": "gkxx_jgcs", "link": "hjnr", "objects": "gkxx_sjdx",
    },
    "disciplinary_action": {
        "code": "xx_gsdm", "company_name": "jc_gsjc", "publish_date": "xx_fwrq",
        "category": "xx_cflb", "link": "ck", "title": "xx_bt",
    },
}


class _TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._row = {"cells": [], "document_path": None}
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
        elif tag == "a" and self._row is not None:
            document_path = attributes.get("encode-open")
            if document_path and not self._row["document_path"]:
                self._row["document_path"] = document_path

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell_parts)).strip()
            self._row["cells"].append(value)
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
            self._cell_parts = None


def _page_count(html_text: str) -> int | None:
    visible = re.sub(r"<[^>]+>", " ", html.unescape(html_text))
    match = re.search(r"\u5171\s*(\d+)\s*\u9875", visible)
    return int(match.group(1)) if match else None


def _official_pdf_url(path: str) -> str | None:
    url = urljoin(f"{SZSE_DOC_URL}/", path.strip())
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "reportdocs.static.szse.cn":
        return None
    if not parsed.path.lower().endswith(".pdf"):
        return None
    return url


def parse_page(
    html_text: str,
    source_type: str,
) -> tuple[list[dict[str, Any]], int | None]:
    """Parse one official SZSE supervision list page."""
    if source_type not in LIST_PATHS:
        raise ValueError(f"Unsupported SZSE source type: {source_type}")

    parser = _TableRowParser()
    parser.feed(html_text)
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_row in parser.rows:
        cells = raw_row["cells"]
        if len(cells) < 5:
            continue
        code, company_name, publish_date, category = cells[:4]
        if not re.fullmatch(r"\d{6}", code):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publish_date):
            continue
        document_url = _official_pdf_url(str(raw_row.get("document_path") or ""))
        if not document_url:
            continue
        official_doc_id = Path(urlsplit(document_url).path).stem
        source_doc_id = f"szse:{official_doc_id}"
        if source_doc_id in seen:
            continue
        seen.add(source_doc_id)
        documents.append({
            "source_doc_id": source_doc_id,
            "source_org": "SZSE",
            "source_type": source_type,
            "official_doc_id": official_doc_id,
            "code": code,
            "company_name": company_name or None,
            "title": " ".join(item for item in (company_name, category) if item),
            "publish_date": publish_date,
            "document_url": document_url,
            "document_format": "pdf",
            "raw_metadata": {
                "list_cells": cells,
                "category": category or None,
                "objects": cells[5] if len(cells) > 5 and cells[5] else None,
            },
        })
    return documents, _page_count(html_text)


def _encoded_document_path(value: Any) -> str:
    match = re.search(r"encode-open\s*=\s*['\"]([^'\"]+)['\"]", str(value or ""), re.I)
    return html.unescape(match.group(1)).strip() if match else ""


def parse_payload(
    payload: Any,
    source_type: str,
) -> tuple[list[dict[str, Any]], int | None]:
    """Normalize the JSON payload used by the official SZSE report widget."""
    if source_type not in FIELD_MAP:
        raise ValueError(f"Unsupported SZSE source type: {source_type}")
    if not isinstance(payload, list):
        raise ValueError("SZSE report response root must be a list")

    fields = FIELD_MAP[source_type]
    page_counts: list[int] = []
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for report in payload:
        if not isinstance(report, dict):
            continue
        metadata = report.get("metadata") or {}
        try:
            page_counts.append(int(metadata.get("pagecount") or 0))
        except (TypeError, ValueError):
            pass
        for row in report.get("data") or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get(fields["code"]) or "").strip()
            company_name = str(row.get(fields["company_name"]) or "").strip()
            publish_date = str(row.get(fields["publish_date"]) or "")[:10]
            category = str(row.get(fields["category"]) or "").strip()
            if not re.fullmatch(r"\d{6}", code):
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publish_date):
                continue
            document_url = _official_pdf_url(_encoded_document_path(row.get(fields["link"])))
            if not document_url:
                continue
            official_doc_id = Path(urlsplit(document_url).path).stem
            source_doc_id = f"szse:{official_doc_id}"
            if source_doc_id in seen:
                continue
            seen.add(source_doc_id)
            explicit_title = str(row.get(fields.get("title", "")) or "").strip()
            title = explicit_title or " ".join(
                item for item in (company_name, category) if item
            )
            objects_field = fields.get("objects")
            documents.append({
                "source_doc_id": source_doc_id,
                "source_org": "SZSE",
                "source_type": source_type,
                "official_doc_id": official_doc_id,
                "code": code,
                "company_name": company_name or None,
                "title": title,
                "publish_date": publish_date,
                "document_url": document_url,
                "document_format": "pdf",
                "raw_metadata": {
                    "catalog_id": CATALOG_IDS[source_type],
                    "category": category or None,
                    "objects": row.get(objects_field) if objects_field else None,
                    "report_row": row,
                },
            })
    page_count = max(page_counts) if page_counts else None
    return documents, page_count


def iter_documents(
    *,
    source_type: str,
    start_date: str,
    end_date: str,
    max_pages: int | None = None,
    pause_seconds: float = 0.5,
    session: Any = None,
) -> Iterator[dict[str, Any]]:
    """Yield normalized SZSE documents within an inclusive date range."""
    if source_type not in LIST_PATHS:
        raise ValueError(f"Unsupported SZSE source type: {source_type}")

    import requests

    client = session or requests.Session()
    client.headers.update({
        "User-Agent": "Mozilla/5.0 hedge-monitor research",
        "Referer": f"{SZSE_SITE_URL}{LIST_PATHS[source_type]}",
    })
    seen: set[str] = set()
    page_no = 1
    while max_pages is None or page_no <= max_pages:
        params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": CATALOG_IDS[source_type],
            "PAGENO": page_no,
        }
        response = None
        last_error: Exception | None = None
        attempts = 0
        for attempts, backoff in enumerate((0, 1, 4), 1):
            if backoff:
                time.sleep(backoff)
            try:
                response = client.get(SZSE_REPORT_URL, params=params, timeout=30)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                response = None
                last_error = exc
        if response is None:
            raise RuntimeError(
                f"SZSE request failed after {attempts} attempts: {last_error}"
            ) from last_error

        try:
            response_text = response.content.decode("utf-8")
        except UnicodeDecodeError:
            response_text = response.content.decode("gb18030", errors="replace")
        rows, page_count = parse_payload(json.loads(response_text), source_type)
        dates = [str(row["publish_date"]) for row in rows if row.get("publish_date")]
        for row in rows:
            publish_date = str(row["publish_date"])
            if start_date <= publish_date <= end_date and row["source_doc_id"] not in seen:
                seen.add(row["source_doc_id"])
                yield row

        if dates and max(dates) < start_date:
            return
        if not rows or (page_count is not None and page_no >= page_count):
            return
        page_no += 1
        if pause_seconds:
            time.sleep(pause_seconds)
