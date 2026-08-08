#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发现公司池内定期报告元数据；默认只预览，--write 才写 Supabase。"""
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
from common import ROOT, log, sb_select, sb_update, sb_upsert, snapshot_csv, warn

CATEGORY = {"annual": "category_ndbg_szsh", "semiannual": "category_bndbg_szsh"}


def load_sample(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["code"].zfill(6): row for row in csv.DictReader(f)}


def build_missing_company_rows(
    sample: dict[str, dict],
    existing_codes: set[str],
) -> list[dict]:
    """为正式池中主表缺失的代码生成满足外键的最小公司记录。"""
    allowed_ent_types = {"央企", "地方国企", "民企", "外资", "集体", "其他"}
    rows = []
    for code in sorted(set(sample) - existing_codes):
        item = sample[code]
        ent_type = item.get("ent_type") or "其他"
        rows.append({
            "code": code,
            "name": item.get("name") or "",
            "ind_l1": item.get("industry") or "未分类",
            "ent_type": ent_type if ent_type in allowed_ent_types else "其他",
            "source": "periodic_formal_pool",
        })
    return rows


def is_target_title(title: str, fiscal_year: int, report_type: str) -> bool:
    title = title or ""
    period_word = "年度报告" if report_type == "annual" else "半年度报告"
    period_pattern = rf"{fiscal_year}年?{period_word}"
    return (
        re.search(period_pattern, title) is not None
        and not re.search(r"摘要|英文版|取消|提示性公告", title)
    )


def choose_canonical_reports(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """同公司同期只保留修订优先、发布日期最新的一份报告。"""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["code"], []).append(row)
    canonical: list[dict] = []
    superseded: list[dict] = []
    for code_rows in grouped.values():
        selected = max(
            code_rows,
            key=lambda row: (
                bool(row.get("is_revised")),
                row.get("publish_date") or "",
                row.get("report_id") or "",
            ),
        )
        canonical.append(selected)
        superseded.extend(
            row for row in code_rows if row["report_id"] != selected["report_id"]
        )
    canonical.sort(key=lambda row: (row["code"], row.get("publish_date") or ""))
    superseded.sort(key=lambda row: (row["code"], row.get("publish_date") or ""))
    return canonical, superseded


def iter_bounded_market_window(
    category: str,
    start_date: str,
    end_date: str,
):
    """查询一个日期窗；超出页数上限时递归二分，最小粒度为单日。"""
    window = f"{start_date}~{end_date}"
    try:
        yield from cninfo.iter_query(category=category, se_date=window, stock="")
        return
    except cninfo.QueryTruncatedError:
        start = dt.date.fromisoformat(start_date)
        end = dt.date.fromisoformat(end_date)
        if start >= end:
            raise
        midpoint = start + (end - start) // 2
        right_start = midpoint + dt.timedelta(days=1)
        log(
            f"全市场窗口 {window} 超过分页上限，自动拆分为 "
            f"{start.isoformat()}~{midpoint.isoformat()} 与 "
            f"{right_start.isoformat()}~{end.isoformat()}"
        )
        yield from iter_bounded_market_window(
            category, start.isoformat(), midpoint.isoformat()
        )
        yield from iter_bounded_market_window(
            category, right_start.isoformat(), end.isoformat()
        )


def iter_full_market_reports(
    category: str,
    start_date: str,
    end_date: str,
):
    """先按季度切窗，任一季度过密时继续自动二分。"""
    for window_start, window_end in cninfo.quarter_windows(start_date, end_date):
        window = f"{window_start}~{window_end}"
        log(f"全市场分窗扫描 {window}")
        yield from iter_bounded_market_window(category, window_start, window_end)


def select_superseded_to_skip(
    superseded: list[dict],
    status_by_report: dict[str, str],
    accepted_report_ids: set[str],
) -> list[dict]:
    """只隐藏未验收旧版；已提取或人工接受结果保持可见。"""
    return [
        row for row in superseded
        if status_by_report.get(row["report_id"]) != "extracted"
        and row["report_id"] not in accepted_report_ids
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="发现定期报告元数据")
    ap.add_argument("--sample", default=str(ROOT / "config" / "annual_poc_2025.csv"))
    ap.add_argument("--fiscal-year", type=int, default=2025)
    ap.add_argument("--report-type", choices=["annual", "semiannual"], default="annual")
    ap.add_argument("--strategy", choices=["targeted", "full"], default="targeted",
                    help="targeted 按样本代码逐家查；full 按季度分窗扫描全市场分类")
    ap.add_argument("--only-code", help="仅测试一个证券代码")
    ap.add_argument("--write", action="store_true", help="确认写入 periodic_reports")
    args = ap.parse_args()

    sample = load_sample(args.sample)
    if args.only_code:
        sample = {k: v for k, v in sample.items() if k == args.only_code.zfill(6)}
    publish_year = args.fiscal_year + 1 if args.report_type == "annual" else args.fiscal_year
    date_window = f"{publish_year}-01-01~{publish_year}-12-31"
    found: dict[str, dict] = {}
    log(f"扫描巨潮 {date_window}，目标 {len(sample)} 家，策略={args.strategy}（只取完整报告，不取摘要）")
    org_map = cninfo.stock_org_map() if args.strategy == "targeted" else {}
    if args.strategy == "full":
        query_streams = [(
            None,
            iter_full_market_reports(
                CATEGORY[args.report_type],
                f"{publish_year}-01-01",
                f"{publish_year}-12-31",
            ),
        )]
    else:
        query_streams = []
        for query_code in sample:
            org_id = org_map.get(query_code)
            if not org_id:
                warn(f"巨潮证券列表缺少 {query_code}，跳过")
                continue
            stock = f"{query_code},{org_id}"
            query_streams.append((
                query_code,
                cninfo.iter_query(
                    category=CATEGORY[args.report_type],
                    se_date=date_window,
                    stock=stock,
                ),
            ))
    for query_code, raw_rows in query_streams:
        for raw in raw_rows:
            rec = cninfo.normalize(raw, source=f"cninfo:{CATEGORY[args.report_type]}")
            code = rec.get("code")
            if code not in sample or not is_target_title(rec.get("title") or "", args.fiscal_year, args.report_type):
                continue
            period = f"{args.fiscal_year}FY" if args.report_type == "annual" else f"{args.fiscal_year}H1"
            row = {
                "report_id": rec["ann_id"], "code": code, "name": rec.get("name"),
                "title": rec["title"], "report_type": args.report_type,
                "report_period": period, "fiscal_year": args.fiscal_year,
                "period_end": f"{args.fiscal_year}-12-31" if args.report_type == "annual" else f"{args.fiscal_year}-06-30",
                "publish_date": rec.get("ann_date"), "adjunct_url": rec.get("adjunct_url"),
                "pdf_url": rec.get("pdf_url"),
                "is_revised": bool(re.search(r"修订|更正", rec["title"])),
                "source": f"cninfo:{CATEGORY[args.report_type]}",
            }
            found[row["report_id"]] = row
        if query_code:
            cninfo.polite_sleep()
    rows, superseded = choose_canonical_reports(list(found.values()))
    covered = len({x["code"] for x in rows})
    log(
        f"发现 {len(rows)} 份规范报告，覆盖 {covered}/{len(sample)} 家；"
        f"旧版/被修订版 {len(superseded)} 份"
    )
    if args.write:
        existing_company_codes = {
            str(row["code"]).zfill(6)
            for row in sb_select("companies", {"select": "code"}, paginate=True)
        }
        missing_company_rows = build_missing_company_rows(
            sample, existing_company_codes
        )
        if missing_company_rows:
            sb_upsert("companies", missing_company_rows, on_conflict="code")
            log(f"已补齐公司主表最小记录 {len(missing_company_rows)} 家")
        existing_reports = sb_select("periodic_reports", {
            "select": "report_id,status",
            "fiscal_year": f"eq.{args.fiscal_year}",
            "report_type": f"eq.{args.report_type}",
        }, paginate=True)
        status_by_report = {
            row["report_id"]: row.get("status") for row in existing_reports
        }
        accepted_report_ids = {
            row["report_id"]
            for row in sb_select("periodic_derivatives", {
                "select": "report_id,review_status",
                "review_status": "eq.accepted",
            }, paginate=True)
        }
        sb_upsert("periodic_reports", rows, on_conflict="report_id")
        superseded_to_skip = select_superseded_to_skip(
            superseded, status_by_report, accepted_report_ids
        )
        protected = len(superseded) - len(superseded_to_skip)
        for old in superseded_to_skip:
            sb_update(
                "periodic_reports",
                {"report_id": f"eq.{old['report_id']}"},
                {"status": "skipped", "note": "同公司同期已有更新或修订版报告"},
            )
        if protected:
            log(f"已保护 {protected} 份已提取或人工接受的旧版报告，不自动隐藏")
        log("元数据已写入 periodic_reports")
    else:
        log("预览模式：未写数据库；确认后加 --write")
    snapshot_csv(f"periodic_{args.report_type}_{args.fiscal_year}", rows)


if __name__ == "__main__":
    main()
