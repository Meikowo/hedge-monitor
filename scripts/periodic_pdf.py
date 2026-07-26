#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定期报告 PDF 候选页定位：纯本地处理，不调用 LLM。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

LOCATOR_VERSION = "v2.2"
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
    "投资收益": 3, "保证金": 5, "其他货币资金": 5, "其他应收款": 4,
    "受限资金": 5, "名义本金": 6, "敞口": 3,
}

COVERAGE_TERM_GROUPS = {
    "activity": ("衍生品投资", "套期保值", "远期结售汇", "外汇远期"),
    "accounting": ("套期会计", "现金流量套期", "公允价值套期", "套期工具", "套期项目"),
    "pnl_investment": ("投资收益",),
    "pnl_fv_change": ("公允价值变动损益",),
    "pnl_oci": ("其他综合收益",),
    "balance_asset": ("衍生金融资产",),
    "balance_liability": ("衍生金融负债",),
    "margin": ("保证金", "其他货币资金", "其他应收款", "受限资金"),
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


def select_candidate_pages(
    pages: list[str],
    custom_terms: list[str] | None = None,
) -> tuple[list[int], set[str], dict[int, int]]:
    """评分选页，并为五类关键财务事实保留至少一个候选页。"""
    custom = [str(x).strip() for x in (custom_terms or []) if str(x).strip()]
    weights = {**STRONG_TERMS, **SUPPORT_TERMS}
    scores: dict[int, int] = {}
    matched: set[str] = set()
    group_scores: dict[str, dict[int, int]] = {
        group: {} for group in COVERAGE_TERM_GROUPS
    }
    if custom:
        group_scores["custom"] = {}

    for idx, text in enumerate(pages, 1):
        score = 0
        for term, weight in weights.items():
            count = text.count(term)
            if count:
                contribution = weight * min(count, 5)
                score += contribution
                matched.add(term)
                for group, terms in COVERAGE_TERM_GROUPS.items():
                    if term in terms:
                        group_scores[group][idx] = (
                            group_scores[group].get(idx, 0) + contribution
                        )
        for term in custom:
            count = text.count(term)
            if count:
                contribution = 3 * min(count, 4)
                score += contribution
                matched.add(term)
                group_scores["custom"][idx] = (
                    group_scores["custom"].get(idx, 0) + contribution
                )
        if score:
            scores[idx] = score

    ranked = sorted(scores, key=lambda p: (-scores[p], p))
    mandatory: list[int] = []
    for group in group_scores:
        candidates = group_scores[group]
        if candidates:
            winner = min(candidates, key=lambda p: (-candidates[p], -scores.get(p, 0), p))
            if winner not in mandatory:
                mandatory.append(winner)

    picked: set[int] = set(mandatory[:MAX_CANDIDATE_PAGES])
    for page in mandatory:
        for neighbor in (page - 1, page + 1):
            if 1 <= neighbor <= len(pages) and len(picked) < MAX_CANDIDATE_PAGES:
                picked.add(neighbor)
    for page in ranked:
        if len(picked) >= MAX_CANDIDATE_PAGES:
            break
        picked.add(page)
    return sorted(picked), matched, scores


def _focused_excerpt(text: str, budget: int, focus_terms: list[str]) -> str:
    """在固定预算内保留每个命中词附近的上下文；无命中时保留页首。"""
    if len(text) <= budget:
        return text
    hits: list[tuple[int, str]] = []
    for term in focus_terms:
        pos = text.find(term)
        if pos >= 0:
            hits.append((pos, term))
    hits.sort()
    if not hits:
        return text[:budget]

    separator = "\n…\n"
    usable = max(1, budget - len(separator) * (len(hits) - 1))
    share = max(1, usable // len(hits))
    chunks: list[str] = []
    for pos, term in hits:
        before = max(0, (share - len(term)) // 2)
        start = max(0, pos - before)
        end = min(len(text), start + share)
        if end - start < share:
            start = max(0, end - share)
        chunks.append(text[start:end])
    return separator.join(chunks)[:budget]


def build_marked_text(
    pages: list[str],
    candidate_pages: list[int],
    focus_terms: list[str],
) -> str:
    """把字符预算均匀分配给候选页，避免后部财务附注被整体截掉。"""
    if not candidate_pages:
        return ""
    headers = [f"【P{page}】\n" for page in candidate_pages]
    separator = "\n\n"
    overhead = sum(len(header) for header in headers)
    overhead += len(separator) * (len(candidate_pages) - 1)
    page_budget = max(1, (MAX_MARKED_CHARS - overhead) // len(candidate_pages))
    parts = [
        header + _focused_excerpt(pages[page - 1], page_budget, focus_terms)
        for header, page in zip(headers, candidate_pages)
    ]
    return separator.join(parts)[:MAX_MARKED_CHARS]


def locate_pdf(content: bytes, custom_terms: list[str] | None = None) -> LocatedReport:
    """为整份 PDF 评分并返回 1-based 候选页及带页码正文。"""
    # 直接从内存打开，避免 Windows NamedTemporaryFile 独占锁导致 Permission denied。
    doc = fitz.open(stream=content, filetype="pdf")
    pages = [_clean(page.get_text()) for page in doc]
    doc.close()

    candidate_pages, matched, scores = select_candidate_pages(pages, custom_terms)

    focus_terms = list(dict.fromkeys([
        *STRONG_TERMS,
        *SUPPORT_TERMS,
        *[str(x).strip() for x in (custom_terms or []) if str(x).strip()],
    ]))
    marked_text = build_marked_text(pages, candidate_pages, focus_terms)
    return LocatedReport(
        marked_text=marked_text,
        page_count=len(pages),
        text_chars=sum(len(x) for x in pages),
        candidate_pages=candidate_pages,
        locator_terms=sorted(matched),
        page_scores={p: scores[p] for p in candidate_pages if p in scores},
    )
