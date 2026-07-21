#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定期报告 PDF 候选页定位：纯本地处理，不调用 LLM。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

LOCATOR_VERSION = "v1.0"
MAX_CANDIDATE_PAGES = 15
MAX_MARKED_CHARS = 26000

STRONG_TERMS = {
    "套期保值": 12, "套保": 10, "衍生品投资": 10, "衍生金融工具": 9,
    "现金流量套期": 10, "公允价值套期": 10, "套期工具": 8, "套期项目": 8,
    "远期结售汇": 9, "外汇远期": 8, "远期外汇": 8,
}
SUPPORT_TERMS = {
    "期货": 4, "期权": 4, "掉期": 4, "互换": 4, "衍生金融资产": 5,
    "衍生金融负债": 5, "公允价值变动损益": 5, "其他综合收益": 5,
    "投资收益": 3, "保证金": 5, "名义本金": 6, "敞口": 3,
}


@dataclass
class LocatedReport:
    marked_text: str
    page_count: int
    text_chars: int
    candidate_pages: list[int]
    locator_terms: list[str]
    page_scores: dict[int, int]


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def locate_pdf(content: bytes, custom_terms: list[str] | None = None) -> LocatedReport:
    """为整份 PDF 评分并返回 1-based 候选页及带页码正文。"""
    custom = [str(x).strip() for x in (custom_terms or []) if str(x).strip()]
    # 直接从内存打开，避免 Windows NamedTemporaryFile 独占锁导致 Permission denied。
    doc = fitz.open(stream=content, filetype="pdf")
    pages = [_clean(page.get_text()) for page in doc]
    doc.close()

    scores: dict[int, int] = {}
    matched: set[str] = set()
    for idx, text in enumerate(pages, 1):
        score = 0
        for term, weight in {**STRONG_TERMS, **SUPPORT_TERMS}.items():
            count = text.count(term)
            if count:
                score += weight * min(count, 5)
                matched.add(term)
        for term in custom:
            count = text.count(term)
            if count:
                score += 3 * min(count, 4)
                matched.add(term)
        if score:
            scores[idx] = score

    ranked = sorted(scores, key=lambda p: (-scores[p], p))
    picked: set[int] = set()
    for page in ranked:
        if len(picked) >= MAX_CANDIDATE_PAGES:
            break
        picked.add(page)
        # 表格标题、表头与续表经常跨页，保留相邻页作为上下文。
        for neighbor in (page - 1, page + 1):
            if 1 <= neighbor <= len(pages) and len(picked) < MAX_CANDIDATE_PAGES:
                picked.add(neighbor)
    candidate_pages = sorted(picked)

    parts: list[str] = []
    used = 0
    for page in candidate_pages:
        segment = f"【P{page}】\n{pages[page - 1]}"
        if used + len(segment) > MAX_MARKED_CHARS:
            segment = segment[:max(0, MAX_MARKED_CHARS - used)]
        if segment:
            parts.append(segment)
            used += len(segment)
        if used >= MAX_MARKED_CHARS:
            break
    return LocatedReport(
        marked_text="\n\n".join(parts),
        page_count=len(pages),
        text_chars=sum(len(x) for x in pages),
        candidate_pages=candidate_pages,
        locator_terms=sorted(matched),
        page_scores={p: scores[p] for p in candidate_pages if p in scores},
    )
