#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输出正式年报池的公司级处理进度。"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, log, sb_select, snapshot_json

STATUS_PRIORITY = {
    "skipped": 1,
    "failed": 2,
    "needs_ocr": 3,
    "discovered": 4,
    "located": 5,
    "extracted": 6,
}


def load_target_codes(path: str) -> set[str]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return {
            str(row.get("code") or "").zfill(6)
            for row in csv.DictReader(handle)
            if row.get("code")
        }


def summarize_progress(
    target_codes: set[str],
    report_rows: list[dict],
    derivative_rows: list[dict],
) -> dict:
    """同公司多版本报告按最有效状态归并，避免修订版重复计数。"""
    canonical: dict[str, dict] = {}
    for row in report_rows:
        code = str(row.get("code") or "").zfill(6)
        if code not in target_codes:
            continue
        current = canonical.get(code)
        rank = (
            STATUS_PRIORITY.get(row.get("status"), 0),
            bool(row.get("is_revised")),
            row.get("publish_date") or "",
            row.get("report_id") or "",
        )
        current_rank = (
            STATUS_PRIORITY.get(current.get("status"), 0),
            bool(current.get("is_revised")),
            current.get("publish_date") or "",
            current.get("report_id") or "",
        ) if current else None
        if current is None or rank > current_rank:
            canonical[code] = row

    counts = {status: 0 for status in STATUS_PRIORITY}
    for row in canonical.values():
        status = row.get("status")
        if status in counts:
            counts[status] += 1

    accepted_report_ids = {
        row.get("report_id")
        for row in derivative_rows
        if row.get("review_status") == "accepted"
    }
    accepted = sum(
        row.get("status") == "extracted"
        and row.get("report_id") in accepted_report_ids
        for row in canonical.values()
    )
    extracted = counts["extracted"]
    return {
        "target": len(target_codes),
        "found": len(canonical),
        "discovered": counts["discovered"],
        "located": counts["located"],
        "extracted": extracted,
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "needs_ocr": counts["needs_ocr"],
        "missing": len(target_codes) - len(canonical),
        "accepted": accepted,
        "verification_rate": round(accepted / extracted, 4) if extracted else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总正式年报池处理进度")
    parser.add_argument(
        "--sample",
        default=str(ROOT / "config" / "annual_formal_2025.csv"),
    )
    parser.add_argument("--fiscal-year", type=int, default=2025)
    parser.add_argument(
        "--report-type", choices=["annual", "semiannual"], default="annual"
    )
    args = parser.parse_args()

    target_codes = load_target_codes(args.sample)
    reports = sb_select("periodic_reports", {
        "select": "report_id,code,status,is_revised,publish_date",
        "fiscal_year": f"eq.{args.fiscal_year}",
        "report_type": f"eq.{args.report_type}",
    }, paginate=True)
    derivatives = sb_select("periodic_derivatives", {
        "select": "report_id,review_status",
    }, paginate=True)
    result = summarize_progress(target_codes, reports, derivatives)
    snapshot_json("periodic_progress", result)
    log(
        "年报进度："
        f"目标 {result['target']}，已发现 {result['found']}，"
        f"待定位 {result['discovered']}，已定位 {result['located']}，"
        f"已提取 {result['extracted']}，失败 {result['failed']}，"
        f"待发现 {result['missing']}，人工接受 {result['accepted']}"
    )


if __name__ == "__main__":
    main()
