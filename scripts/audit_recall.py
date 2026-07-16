#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_recall.py —— 查全率自动审计（L2 全文补捞，自动闭环）
==========================================================
问题：只按标题关键词召回会系统性漏掉「董事会决议公告」这类
标题不含套保词、正文却藏着套保议案的公告。

方案（全自动，无需人工介入）：
  1. 用巨潮全文检索接口按审计词查近 N 天正文命中清单；
  2. 与库中已有 ann_id 求差集 → 得到「正文命中但标题层漏掉」的公告；
  3. 以 ignore-duplicates 方式只插新行（source='fulltext-audit'），
     新行默认 status=pending，自然进入抽取管线；
  4. 全文命中噪音大（重组报告书、审计报告都含"套期保值"），
     由抽取阶段的 LLM is_hedge_related=false 自动打成 irrelevant。
  5. 每次运行落 output/ 快照，Actions 里作为 artifact 可回查。

用法：
  python scripts/audit_recall.py --days 35        # 月度定时用
  python scripts/audit_recall.py --start 2025-01-01 --end 2025-12-31   # 历史审计
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

import cninfo
from common import ROOT, beijing_today, log, sb_select, sb_upsert, snapshot_csv


def known_ann_ids(sdate: str, edate: str) -> set[str]:
    rows = sb_select("announcements", {
        "select": "ann_id",
        "and": f"(ann_date.gte.{sdate},ann_date.lte.{edate})",
    }, paginate=True)
    return {r["ann_id"] for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="全文检索查全率审计（自动补捞）")
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--start", help="YYYY-MM-DD（与 --end 搭配，覆盖 --days）")
    ap.add_argument("--end")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = beijing_today()
    if args.start and args.end:
        sdate, edate = args.start, args.end
    else:
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        edate = today.isoformat()

    with (ROOT / "config" / "keywords.yml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    exclude_re = re.compile(cfg.get("title_exclude_pattern") or r"$^")
    exclude_codes = set(cfg.get("exclude_sec_codes") or [])

    log(f"审计窗口 {sdate} ~ {edate}，先取库内已有 ann_id ...")
    known = known_ann_ids(sdate, edate)
    log(f"库内窗口期公告 {len(known)} 条")

    bag: dict[str, dict] = {}
    for kw in cfg["fulltext_audit_keywords"]:
        log(f"[全文层] 关键词「{kw}」")
        n_hit = n_new = 0
        for raw in cninfo.iter_fulltext(kw, sdate, edate):
            rec = cninfo.normalize(raw, source="fulltext-audit")
            aid = rec["ann_id"]
            n_hit += 1
            if not aid or aid in known or aid in bag:
                continue
            if rec["code"] in exclude_codes or exclude_re.search(rec["title"]):
                continue
            rec["matched_keywords"] = [f"fulltext:{kw}"]
            bag[aid] = rec
            n_new += 1
        log(f"  「{kw}」正文命中 {n_hit}，其中标题层漏检 {n_new}")
        cninfo.polite_sleep()

    misses = list(bag.values())
    miss_rate = f"{len(misses)}/{len(known) + len(misses)}"
    log(f"审计结论：漏检 {len(misses)} 条（窗口漏检率约 {miss_rate}）")
    snapshot_csv("recall_audit", misses)

    if misses and not args.dry_run:
        payload = [{
            "ann_id": r["ann_id"], "code": r["code"], "name": r["name"],
            "title": r["title"], "publish_time": r["publish_time"],
            "ann_date": r["ann_date"], "adjunct_url": r["adjunct_url"],
            "pdf_url": r["pdf_url"], "source": r["source"],
            "matched_keywords": r["matched_keywords"],
        } for r in misses]
        # ignore-duplicates：只插新行，绝不覆盖标题层已有记录
        n = sb_upsert("announcements", payload, on_conflict="ann_id",
                      resolution="ignore-duplicates")
        log(f"漏检公告已入库 {n} 条（status=pending，将由抽取管线自动判别）")


if __name__ == "__main__":
    main()
