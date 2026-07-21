#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载少量定期报告并定位候选页；不调用 LLM。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cninfo
from common import OUTPUT_DIR, ROOT, log, sb_select, sb_update, snapshot_json, warn
from periodic_pdf import LOCATOR_VERSION, locate_pdf


def load_terms(path: str) -> dict[str, list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["code"].zfill(6): json.loads(row.get("locator_terms") or "[]")
                for row in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser(description="定期报告候选页定位")
    ap.add_argument("--sample", default=str(ROOT / "config" / "annual_poc_2025.csv"))
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--report-id", action="append")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    params = {
        "select": "report_id,code,name,title,pdf_url,status",
        "order": "publish_date.desc", "limit": str(args.limit),
    }
    if args.report_id:
        params["report_id"] = f"in.({','.join(args.report_id)})"
    else:
        params["status"] = "in.(discovered,failed)"
    reports = sb_select("periodic_reports", params)
    terms = load_terms(args.sample)
    summary = []
    OUTPUT_DIR.mkdir(exist_ok=True)
    for i, report in enumerate(reports, 1):
        rid = report["report_id"]
        log(f"[{i}/{len(reports)}] {report.get('name')} | {report.get('title')}")
        content = cninfo.download_pdf(report["pdf_url"])
        if not content:
            warn("PDF 下载失败")
            if args.write:
                sb_update("periodic_reports", {"report_id": f"eq.{rid}"},
                          {"status": "failed", "note": "PDF下载失败"})
            continue
        located = locate_pdf(content, terms.get(report["code"], []))
        status = "located" if located.candidate_pages else (
            "needs_ocr" if located.text_chars < 500 else "skipped")
        patch = {
            "status": status, "candidate_pages": located.candidate_pages,
            "locator_terms": located.locator_terms, "locator_version": LOCATOR_VERSION,
            "page_count": located.page_count, "text_chars": located.text_chars,
            "note": None if status == "located" else "未定位到套保相关页面",
        }
        bundle = {
            "report": report, "locator": {**patch, "page_scores": located.page_scores},
            "marked_text": located.marked_text,
        }
        path = snapshot_json(f"periodic_candidate_{rid}", bundle)
        if args.write:
            sb_update("periodic_reports", {"report_id": f"eq.{rid}"}, patch)
        log(f"候选页 {located.candidate_pages}；总页数 {located.page_count}；快照 {path}")
        summary.append({"report_id": rid, "code": report["code"], **patch})
    snapshot_json("periodic_locate_run", summary)


if __name__ == "__main__":
    main()

