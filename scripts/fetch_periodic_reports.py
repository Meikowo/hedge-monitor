#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发现公司池内定期报告元数据；默认只预览，--write 才写 Supabase。"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cninfo
from common import ROOT, log, sb_upsert, snapshot_csv, warn

CATEGORY = {"annual": "category_ndbg_szsh", "semiannual": "category_bndbg_szsh"}


def load_sample(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["code"].zfill(6): row for row in csv.DictReader(f)}


def is_target_title(title: str, fiscal_year: int, report_type: str) -> bool:
    title = title or ""
    period_word = "年度报告" if report_type == "annual" else "半年度报告"
    return (f"{fiscal_year}年{period_word}" in title and
            not re.search(r"摘要|英文版|取消|提示性公告", title))


def main() -> None:
    ap = argparse.ArgumentParser(description="发现定期报告元数据")
    ap.add_argument("--sample", default=str(ROOT / "config" / "annual_poc_2025.csv"))
    ap.add_argument("--fiscal-year", type=int, default=2025)
    ap.add_argument("--report-type", choices=["annual", "semiannual"], default="annual")
    ap.add_argument("--strategy", choices=["targeted", "full"], default="targeted",
                    help="targeted 按样本代码逐家查；full 扫全市场分类（仅排错）")
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
    queries = ([None] if args.strategy == "full" else list(sample))
    for query_code in queries:
        stock = ""
        if query_code:
            org_id = org_map.get(query_code)
            if not org_id:
                warn(f"巨潮证券列表缺少 {query_code}，跳过")
                continue
            stock = f"{query_code},{org_id}"
        for raw in cninfo.iter_query(category=CATEGORY[args.report_type], se_date=date_window,
                                     stock=stock):
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
    rows = sorted(found.values(), key=lambda x: (x["code"], x["publish_date"] or ""))
    covered = len({x["code"] for x in rows})
    log(f"发现 {len(rows)} 份完整报告，覆盖 {covered}/{len(sample)} 家")
    if args.write:
        sb_upsert("periodic_reports", rows, on_conflict="report_id")
        log("元数据已写入 periodic_reports")
    else:
        log("预览模式：未写数据库；确认后加 --write")
    snapshot_csv(f"periodic_{args.report_type}_{args.fiscal_year}", rows)


if __name__ == "__main__":
    main()
