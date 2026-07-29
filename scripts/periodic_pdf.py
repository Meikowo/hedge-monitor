#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定期报告 PDF 候选页定位：纯本地处理，不调用 LLM。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

LOCATOR_VERSION = "v2.3"
MAX_CANDIDATE_PAGES = 15
MAX_MARKED_CHARS = 26000
TABLE_CONTROLLED_METRICS = {
    "derivative_fv_change_pnl",
    "oci_amount",
    "period_purchase_amount",
    "period_sale_amount",
    "ending_balance",
    "net_asset_ratio",
}

STRONG_TERMS = {
    "套期保值": 12, "套保": 10, "衍生品投资": 10, "衍生金融工具": 9,
    "现金流量套期": 10, "公允价值套期": 10, "套期工具": 8, "套期项目": 8,
    "远期结售汇": 9, "外汇远期": 8, "远期外汇": 8,
    "未应用套期会计": 18,
    "现金流量套期储备": 16,
    "本期所得税前发生额": 10,
    "衍生金融工具资产": 12, "衍生金融工具负债": 12,
    "衍生金融工具产生的公允价值变动收益": 14,
    "期货合约保证金": 12,
    "公司开展符合条件套期业务并应用套期会计": 18,
}
SUPPORT_TERMS = {
    "期货": 4, "期权": 4, "掉期": 4, "互换": 4, "衍生金融资产": 5,
    "衍生金融负债": 5, "公允价值变动损益": 5, "其他综合收益": 5,
    "投资收益": 3, "保证金": 5, "其他货币资金": 5, "其他应收款": 4,
    "受限资金": 5, "名义本金": 6, "敞口": 3,
    "公允价值变动收益": 6,
}

COVERAGE_TERM_GROUPS = {
    "activity": ("衍生品投资", "套期保值", "远期结售汇", "外汇远期"),
    "accounting": (
        "套期会计", "未应用套期会计", "现金流量套期",
        "公允价值套期", "套期工具", "套期项目",
        "公司开展符合条件套期业务并应用套期会计",
    ),
    "pnl_investment": ("投资收益",),
    "pnl_fv_change": (
        "公允价值变动损益", "公允价值变动收益",
        "衍生金融工具产生的公允价值变动收益",
    ),
    "pnl_oci": ("其他综合收益", "现金流量套期储备"),
    "pnl_oci_actual": ("现金流量套期储备", "本期所得税前发生额"),
    "balance_asset": ("衍生金融资产", "衍生金融工具资产"),
    "balance_liability": ("衍生金融负债", "衍生金融工具负债"),
    "margin": (
        "保证金", "期货合约保证金", "其他货币资金",
        "其他应收款", "受限资金",
    ),
}
REQUIRE_ALL_COVERAGE_TERMS = {"pnl_oci_actual"}


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


def unit_before_table(
    blocks: list[tuple],
    table_top: float,
    page_text: str,
) -> str:
    """按表格纵坐标选最近的前置单位，避免同页多表串用单位。"""
    candidates: list[tuple[float, str]] = []
    unit_pattern = re.compile(
        r"单位\s*[:：]\s*(?:人民币)?\s*"
        r"(亿美元|万美元|美元|亿元|百万元|万元|千元|元)"
    )
    for block in blocks:
        if len(block) < 5:
            continue
        y0, y1, text = float(block[1]), float(block[3]), str(block[4] or "")
        if y0 > table_top + 2:
            continue
        matches = list(unit_pattern.finditer(text))
        if matches:
            candidates.append((min(y1, table_top), matches[-1].group(1)))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    matches = list(unit_pattern.finditer(page_text or ""))
    return matches[-1].group(1) if matches else "元"


def find_parent_company_note_start(pages: list[str]) -> int | None:
    for page_number, text in enumerate(pages, 1):
        compact = re.sub(r"\s+", "", text or "")
        if "母公司财务报表主要项目注释" in compact:
            return page_number
    return None


def parse_derivative_investment_table(
    rows: list[list[str | None]],
    page: int,
    unit: str,
) -> list[dict]:
    if len(rows) < 2:
        return []
    headers = [re.sub(r"\s+", "", str(cell or "")) for cell in rows[0]]
    mappings = {
        "本期公允价值变动损益": ("derivative_fv_change_pnl", "period"),
        "投资收益": ("derivative_disposal_investment_income", "period"),
        "计入权益的累计公允价值变动": ("oci_amount", "period"),
        "报告期内购入金额": ("period_purchase_amount", "period"),
        "报告期内售出金额": ("period_sale_amount", "period"),
        "期末金额": ("ending_balance", "period_end"),
        "期末账面价值": ("ending_balance", "period_end"),
        "期末投资金额占公司报告期末净资产比例": ("net_asset_ratio", "period_end"),
        "期末账面价值占公司报告期末净资产比例（%）": (
            "net_asset_ratio", "period_end",
        ),
    }
    if not headers or "衍生品投资类型" not in headers[0]:
        sparse_header = "".join(
            re.sub(r"\s+", "", str(cell or ""))
            for row in rows[:10]
            for cell in row
        )
        required = (
            "衍生品投资类", "本期公", "报告期内购",
            "报告期内售", "期末金额", "期末投资",
        )
        if not all(fragment in sparse_header for fragment in required):
            return []
        logical_columns = {
            3: ("derivative_fv_change_pnl", "period", "本期公允价值变动损益"),
            4: ("oci_amount", "period", "计入权益的累计公允价值变动"),
            5: ("period_purchase_amount", "period", "报告期内购入金额"),
            6: ("period_sale_amount", "period", "报告期内售出金额"),
            7: ("ending_balance", "period_end", "期末金额"),
            8: ("net_asset_ratio", "period_end", "期末投资金额占公司报告期末净资产比例"),
        }
        compact_rows = [
            [re.sub(r"\s+", "", str(cell)) for cell in row if str(cell or "").strip()]
            for row in rows
        ]
        metrics: list[dict] = []
        for compact in compact_rows:
            if len(compact) < 9:
                continue
            label = compact[0]
            if label == "合计" or "报告期" in label:
                continue
            if "利率" in label:
                scope = "利率"
            elif any(term in label for term in ("远期", "外汇", "汇率", "货币", "掉期")):
                scope = "外汇"
            elif any(term in label for term in ("期货", "期权", "商品")):
                scope = "商品"
            else:
                scope = None
            for idx, (metric_type, time_basis, header) in logical_columns.items():
                raw_value = compact[idx]
                if not raw_value or raw_value in {"-", "—", "–"}:
                    continue
                numeric = raw_value.removesuffix("%").replace(",", "")
                if numeric.startswith("(") and numeric.endswith(")"):
                    numeric = f"-{numeric[1:-1]}"
                try:
                    value = float(numeric)
                except ValueError:
                    continue
                metric_unit = "%" if metric_type == "net_asset_ratio" else unit
                metrics.append({
                    "metric_type": metric_type,
                    "fact_level": "scope" if scope else "report",
                    "scope": scope,
                    "underlying": None,
                    "value": value,
                    "currency": None if metric_unit == "%" else (
                        "USD" if "美元" in metric_unit else "CNY"
                    ),
                    "unit": metric_unit,
                    "time_basis": time_basis,
                    "source_section": "衍生品投资情况",
                    "account_name": label,
                    "is_restricted": None,
                    "counterparty": None,
                    "raw": f"{label} {header} {raw_value}",
                    "page": page,
                    "table_cell_verified": True,
                })
        return metrics
    columns = {
        idx: mappings[header]
        for idx, header in enumerate(headers)
        if header in mappings
    }
    metrics: list[dict] = []
    for row in rows[1:]:
        label = re.sub(r"\s+", "", str(row[0] or ""))
        if not label or label == "合计" or "报告期" in label:
            continue
        if "利率" in label:
            scope = "利率"
        elif any(term in label for term in ("远期", "外汇", "汇率", "货币", "掉期")):
            scope = "外汇"
        elif any(term in label for term in ("期货", "期权", "商品")):
            scope = "商品"
        else:
            scope = None
        for idx, (metric_type, time_basis) in columns.items():
            if idx >= len(row):
                continue
            raw_value = re.sub(r"\s+", "", str(row[idx] or ""))
            if not raw_value or raw_value in {"-", "—", "–"}:
                continue
            numeric = raw_value.removesuffix("%").replace(",", "")
            if numeric.startswith("(") and numeric.endswith(")"):
                numeric = f"-{numeric[1:-1]}"
            try:
                value = float(numeric)
            except ValueError:
                continue
            metric_unit = "%" if metric_type == "net_asset_ratio" else unit
            metrics.append({
                "metric_type": metric_type,
                "fact_level": "scope" if scope else "report",
                "scope": scope,
                "underlying": None,
                "value": value,
                "currency": None if metric_unit == "%" else (
                    "USD" if "美元" in metric_unit else "CNY"
                ),
                "unit": metric_unit,
                "time_basis": time_basis,
                "source_section": "衍生品投资情况",
                "account_name": label,
                "is_restricted": None,
                "counterparty": None,
                "raw": f"{label} {headers[idx]} {raw_value}",
                "page": page,
                "table_cell_verified": True,
            })
    return metrics


def _is_derivative_investment_header(
    rows: list[list[str | None]],
) -> bool:
    header_text = "".join(
        re.sub(r"\s+", "", str(cell or ""))
        for row in rows[:10]
        for cell in row
    )
    return all(fragment in header_text for fragment in (
        "衍生品投资类",
        "本期公允价值变动损益",
        "期末投资金额",
    ))


def merge_derivative_continuation(
    rows: list[list[str | None]],
    *,
    prior_header_rows: list[list[str | None]] | None,
    prior_page: int | None,
    page: int,
    table_top: float,
) -> list[list[str | None]]:
    """把上一页的标准衍生品表头接到紧邻下一页的续表数据前。"""
    if (
        prior_header_rows
        and prior_page == page - 1
        and table_top < 350
        and not _is_derivative_investment_header(rows)
    ):
        return [*prior_header_rows, *rows]
    return rows


def _table_number(value: str | None) -> tuple[float, str] | None:
    raw = re.sub(r"\s+", "", str(value or ""))
    if not raw or raw in {"-", "—", "–", "/"}:
        return None
    numeric = raw.replace(",", "")
    if numeric.startswith("(") and numeric.endswith(")"):
        numeric = f"-{numeric[1:-1]}"
    try:
        return float(numeric), raw
    except ValueError:
        return None


def parse_derivative_note_table(
    rows: list[list[str | None]],
    page: int,
    unit: str,
) -> list[dict]:
    """从财务附注表格抽取可由表头和单元格直接确认的衍生品事实。"""
    if len(rows) < 2:
        return []
    header_rows = rows[:2]
    header_text = " ".join(
        re.sub(r"\s+", "", str(cell or ""))
        for row in header_rows
        for cell in row
    )
    metrics: list[dict] = []
    fair_value_side: str | None = None
    derivative_liability_section = False

    def add(
        metric_type: str,
        value_cell: str | None,
        label: str,
        column: str,
        source_section: str,
        time_basis: str,
    ) -> None:
        parsed = _table_number(value_cell)
        if not parsed:
            return
        value, raw_value = parsed
        metrics.append({
            "metric_type": metric_type,
            "fact_level": "report",
            "scope": None,
            "underlying": None,
            "value": value,
            "currency": "USD" if "美元" in unit else "CNY",
            "unit": unit,
            "time_basis": time_basis,
            "source_section": source_section,
            "account_name": label,
            "is_restricted": None,
            "counterparty": None,
            "raw": f"{label} {column} {raw_value}",
            "page": page,
            "table_cell_verified": True,
        })

    first_row_text = "".join(
        re.sub(r"\s+", "", str(cell or ""))
        for cell in rows[0]
    )
    first_row_is_header = any(
        marker in first_row_text
        for marker in (
            "项目本期发生额",
            "款项性质",
            "期末公允价值",
            "年末公允价值",
            "产生公允价值变动收益的来源",
        )
    )
    data_rows = rows[1:] if first_row_is_header else rows
    for row in data_rows:
        if not row:
            continue
        label = re.sub(r"\s+", "", str(row[0] or ""))
        if not label:
            continue
        if "交易性金融资产" in label or label == "衍生金融资产":
            fair_value_side = "asset"
        elif "交易性金融负债" in label or label == "衍生金融负债":
            fair_value_side = "liability"
        if "衍生金融负债" in label:
            derivative_liability_section = True

        if "期货合约保证金" in label:
            add(
                "margin_end_cash", row[1] if len(row) > 1 else None,
                label, "期末余额", "其他货币资金或其他应收款", "period_end",
            )

        if "现金流量套期储备" in label and len(row) > 3:
            add(
                "oci_amount", row[2], label, "本期所得税前发生额",
                "其他综合收益", "period",
            )
            add(
                "reclassification_amount", row[3], label,
                "前期计入其他综合收益当期转入损益",
                "其他综合收益", "period",
            )

        if (
            "衍生金融工具取得的投资收益" in label
            or "处置衍生金融工具取得的投资收益" in label
            or (
                "收益" in label
                and any(
                    marker in label
                    for marker in (
                        "期货",
                        "期权",
                        "远期外汇",
                        "远期结售汇",
                        "掉期",
                        "互换",
                        "T+D",
                    )
                )
            )
        ):
            add(
                "derivative_disposal_investment_income",
                row[1] if len(row) > 1 else None,
                label, "本期发生额", "投资收益", "period",
            )

        if (
            "衍生金融工具产生的公允价值变动" in label
            or (
                label == "衍生金融工具"
                and "产生公允价值变动收益的来源" in header_text
            )
        ):
            add(
                "derivative_fv_change_pnl",
                row[1] if len(row) > 1 else None,
                label, "本期发生额", "公允价值变动收益", "period",
            )

        is_derivative_position = (
            "衍生金融工具" in label
            or "衍生金融资产" in label
            or "衍生金融负债" in label
        )
        if (
            is_derivative_position
            and any(term in header_text for term in ("期末公允价值", "年末公允价值"))
        ):
            side = (
                "liability" if "负债" in label
                else "asset" if "资产" in label
                else fair_value_side
            )
            value_cell = next(
                (
                    cell for cell in reversed(row[1:])
                    if _table_number(cell) is not None
                ),
                None,
            )
            if side == "asset":
                add(
                    "derivative_asset_fv", value_cell, label,
                    "期末公允价值合计", "公允价值的披露", "period_end",
                )
            elif side == "liability":
                add(
                    "derivative_liability_fv", value_cell, label,
                    "期末公允价值合计", "公允价值的披露", "period_end",
                )
        if (
            derivative_liability_section
            and "负债总额" in label
            and any(term in header_text for term in ("期末公允价值", "年末公允价值"))
        ):
            value_cell = next(
                (
                    cell for cell in reversed(row[1:])
                    if _table_number(cell) is not None
                ),
                None,
            )
            add(
                "derivative_liability_fv", value_cell, "衍生金融负债",
                "期末公允价值合计", "公允价值的披露", "period_end",
            )
            derivative_liability_section = False
    return metrics


def extract_derivative_table_metrics(
    content: bytes,
    candidate_pages: list[int],
) -> tuple[list[dict], set[int]]:
    """用 PDF 单元格坐标提取标准衍生品投资表，避免扁平文本列错位。"""
    doc = fitz.open(stream=content, filetype="pdf")
    metrics: list[dict] = []
    table_pages: set[int] = set()
    try:
        carry_header_rows: list[list[str | None]] | None = None
        carry_page: int | None = None
        carry_unit: str | None = None
        for page_number in candidate_pages:
            page = doc[page_number - 1]
            for table in page.find_tables().tables:
                raw_rows = table.extract()
                unit = unit_before_table(
                    page.get_text("blocks"),
                    table_top=table.bbox[1],
                    page_text=page.get_text(),
                )
                rows = merge_derivative_continuation(
                    raw_rows,
                    prior_header_rows=carry_header_rows,
                    prior_page=carry_page,
                    page=page_number,
                    table_top=table.bbox[1],
                )
                if rows is not raw_rows and carry_unit:
                    unit = carry_unit
                parsed = parse_derivative_investment_table(
                    rows,
                    page=page_number,
                    unit=unit,
                )
                if parsed:
                    metrics.extend(parsed)
                    table_pages.add(page_number)
                    if rows is not raw_rows:
                        carry_header_rows = None
                        carry_page = None
                        carry_unit = None
                elif _is_derivative_investment_header(raw_rows):
                    carry_header_rows = raw_rows
                    carry_page = page_number
                    carry_unit = unit
    finally:
        doc.close()
    return metrics, table_pages


def extract_derivative_note_metrics(
    content: bytes,
    candidate_pages: list[int],
) -> list[dict]:
    """扫描候选页财务附注表格，补足保证金、期末公允价值及损益组成。"""
    doc = fitz.open(stream=content, filetype="pdf")
    metrics: list[dict] = []
    try:
        page_texts = [page.get_text() for page in doc]
        parent_note_start = find_parent_company_note_start(page_texts)
        scan_pages = sorted({
            neighbor
            for page_number in candidate_pages
            for neighbor in (page_number - 1, page_number, page_number + 1)
            if 1 <= neighbor <= len(doc)
        })
        carry_fair_value_headers: list[list[str | None]] | None = None
        carry_page: int | None = None
        for page_number in scan_pages:
            if parent_note_start and page_number >= parent_note_start:
                continue
            page = doc[page_number - 1]
            for table in page.find_tables().tables:
                rows = table.extract()
                unit = unit_before_table(
                    page.get_text("blocks"),
                    table_top=table.bbox[1],
                    page_text=page_texts[page_number - 1],
                )
                header_text = "".join(
                    re.sub(r"\s+", "", str(cell or ""))
                    for row in rows[:2]
                    for cell in row
                )
                if any(term in header_text for term in ("期末公允价值", "年末公允价值")):
                    carry_fair_value_headers = rows[:2]
                    carry_page = page_number
                elif (
                    carry_fair_value_headers
                    and carry_page == page_number - 1
                    and table.bbox[1] < 350
                    and any(
                        "衍生金融负债" in re.sub(r"\s+", "", str(row[0] or ""))
                        for row in rows
                        if row
                    )
                ):
                    rows = [*carry_fair_value_headers, *rows]
                metrics.extend(parse_derivative_note_table(
                    rows,
                    page=page_number,
                    unit=unit,
                ))
    finally:
        doc.close()
    return metrics


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
        compact_text = re.sub(r"\s+", "", text)
        score = 0
        for term, weight in weights.items():
            count = compact_text.count(re.sub(r"\s+", "", term))
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
            count = compact_text.count(re.sub(r"\s+", "", term))
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
        if group in REQUIRE_ALL_COVERAGE_TERMS:
            required = COVERAGE_TERM_GROUPS[group]
            candidates = {
                page: score for page, score in candidates.items()
                if all(
                    re.sub(r"\s+", "", term)
                    in re.sub(r"\s+", "", pages[page - 1])
                    for term in required
                )
            }
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

