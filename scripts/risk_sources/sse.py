#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上海证券交易所监管信息公开接口适配器。"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin


SSE_QUERY_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_SITE_URL = "https://www.sse.com.cn/"
CHANNELS = {
    "inquiry": "10743,10744,10012",
    "regulatory_measure": "10007,10008,10009,10010",
}


def unwrap_jsonp(raw: str) -> dict[str, Any]:
    """Parse either plain JSON or the JSONP wrapper returned by SSE."""
    text = raw.strip()
    if text.startswith("{"):
        payload = text
    else:
        match = re.fullmatch(r"[\w.$]+\s*\((.*)\)\s*;?", text, re.DOTALL)
        if not match:
            raise ValueError("SSE response is neither JSON nor valid JSONP")
        payload = match.group(1)
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("SSE response root must be an object")
    return value


def normalize_document(row: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    """Map one SSE result into the risk_source_documents contract."""
    official_doc_id = str(row.get("docId") or "").strip()
    if not official_doc_id:
        raise ValueError("SSE document is missing docId")
    raw_url = str(row.get("docURL") or "").strip()
    if not raw_url:
        raise ValueError("SSE document is missing official URL")
    if re.match(r"^[\w.-]+\.sse\.com\.cn/", raw_url):
        url = f"https://{raw_url}"
    else:
        url = urljoin(SSE_SITE_URL, raw_url)
    if url.startswith("http://") and ".sse.com.cn/" in url:
        url = f"https://{url.removeprefix('http://')}"
    if not url.startswith("https://"):
        raise ValueError(f"SSE document URL is not HTTPS: {url}")

    suffix = url.split("?", 1)[0].lower()
    document_format = "pdf" if suffix.endswith(".pdf") else "html"
    code = str(row.get("extSECURITY_CODE") or "").strip() or None
    title = re.sub(r"<[^>]+>", "", str(row.get("docTitle") or "")).strip()
    publish_date = str(row.get("createTime") or "")[:10] or None

    return {
        "source_doc_id": f"sse:{official_doc_id}",
        "source_org": "SSE",
        "source_type": source_type,
        "official_doc_id": official_doc_id,
        "code": code,
        "company_name": str(row.get("extGSJC") or "").strip() or None,
        "title": title,
        "publish_date": publish_date,
        "document_url": url,
        "document_format": document_format,
        "raw_metadata": row,
    }


def _query_params(
    *,
    source_type: str,
    start_date: str,
    end_date: str,
    page_no: int,
    page_size: int,
) -> dict[str, str | int]:
    if source_type not in CHANNELS:
        raise ValueError(f"Unsupported SSE source type: {source_type}")
    params: dict[str, str | int] = {
        "isPagination": "true",
        "pageHelp.pageSize": page_size,
        "pageHelp.pageNo": page_no,
        "pageHelp.beginPage": page_no,
        "pageHelp.cacheSize": 1,
        "pageHelp.endPage": page_no,
        "sqlId": "BS_KCB_GGLL_NEW",
        "siteId": 28,
        "channelId": CHANNELS[source_type],
        "type": "",
        "stockcode": "",
        "createTime": f"{start_date} 00:00:00",
        "createTimeEnd": f"{end_date} 23:59:59",
        "order": "createTime|desc,stockcode|asc",
        "jsonCallBack": "jsonpCallback",
    }
    if source_type == "inquiry":
        params["extGGDL"] = ""
    else:
        params["extTeacher"] = ""
        params["extWTFL"] = ""
    return params


def iter_documents(
    *,
    source_type: str,
    start_date: str,
    end_date: str,
    page_size: int = 100,
    max_pages: int | None = None,
    pause_seconds: float = 0.3,
    session: Any = None,
) -> Iterator[dict[str, Any]]:
    """Yield normalized official documents, one SSE result page at a time."""
    import requests

    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0 hedge-monitor research",
            "Referer": "https://www.sse.com.cn/regulation/supervision/inquiries/",
        }
    )
    page_no = 1
    while max_pages is None or page_no <= max_pages:
        params = _query_params(
            source_type=source_type,
            start_date=start_date,
            end_date=end_date,
            page_no=page_no,
            page_size=page_size,
        )
        last_error: Exception | None = None
        response = None
        for attempt, backoff in enumerate((0, 1, 4), 1):
            if backoff:
                time.sleep(backoff)
            try:
                response = client.get(
                    SSE_QUERY_URL,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                response = None
        if response is None:
            raise RuntimeError(
                f"SSE request failed after {attempt} attempts: {last_error}"
            ) from last_error
        try:
            raw_text = response.content.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = response.content.decode("gb18030", errors="replace")
        payload = unwrap_jsonp(raw_text)
        page_help = payload.get("pageHelp") or {}
        rows = payload.get("result") or page_help.get("data") or []
        if not rows:
            return
        for row in rows:
            try:
                yield normalize_document(row, source_type=source_type)
            except ValueError:
                continue

        page_count = int(page_help.get("pageCount") or page_no)
        if page_no >= page_count or len(rows) < page_size:
            return
        page_no += 1
        if pause_seconds:
            time.sleep(pause_seconds)
