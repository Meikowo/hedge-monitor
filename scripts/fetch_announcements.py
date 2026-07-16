#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_announcements.py —— 套保公告采集入库（公告层 L1 标题召回）
================================================================
逐关键词查巨潮标题 → announcementId 去重 → 排除规则 → upsert announcements。
幂等：可无限重跑；重叠时间窗零成本（主键去重）。
注意：upsert 载荷不含 status/note 字段，因此重跑绝不会把已抽取
公告的状态打回 pending（新行由数据库默认值置 pending）。

用法：
  python scripts/fetch_announcements.py daily                       # 抓近3天（默认）
  python scripts/fetch_announcements.py daily --days 7
  python scripts/fetch_announcements.py backfill --year 2026
  python scripts/fetch_announcements.py backfill --start 2021-01-01 --end 2021-12-31
  python scripts/fetch_announcements.py daily --dry-run             # 只打印不写库
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
from common import ROOT, beijing_today, log, sb_upsert, snapshot_csv


def load_keyword_config() -> dict:
    with (ROOT / "config" / "keywords.yml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_exclude_re"] = re.compile(cfg.get("title_exclude_pattern") or r"$^")
    cfg["_exclude_codes"] = set(cfg.get("exclude_sec_codes") or [])
    return cfg


def fetch_window(sdate: str, edate: str, cfg: dict) -> list[dict]:
    """一个时间窗内：逐关键词查询 → 去重 → 排除。matched_keywords 记录全部命中词。"""
    bag: dict[str, dict] = {}
    for kw in cfg["title_keywords"]:
        log(f"[标题层] 关键词「{kw}」 {sdate}~{edate}")
        n_kw = 0
        for raw in cninfo.iter_query(searchkey=kw, se_date=f"{sdate}~{edate}"):
            rec = cninfo.normalize(raw, source=f"title:{kw}")
            aid = rec["ann_id"]
            if not aid:
                continue
            if aid in bag:
                bag[aid]["matched_keywords"].append(kw)
                continue
            if rec["code"] in cfg["_exclude_codes"]:
                continue
            if cfg["_exclude_re"].search(rec["title"]):
                continue
            rec["matched_keywords"] = [kw]
            bag[aid] = rec
            n_kw += 1
        log(f"  「{kw}」新增 {n_kw} 条（窗内累计 {len(bag)}）")
        cninfo.polite_sleep()
    return list(bag.values())


def upsert_announcements(rows: list[dict]) -> int:
    # 载荷刻意不含 status/note：新行走库默认 pending，旧行状态不被覆盖
    payload = [{
        "ann_id": r["ann_id"], "code": r["code"], "name": r["name"],
        "title": r["title"], "publish_time": r["publish_time"],
        "ann_date": r["ann_date"], "adjunct_url": r["adjunct_url"],
        "pdf_url": r["pdf_url"], "source": r["source"],
        "matched_keywords": r["matched_keywords"],
    } for r in rows]
    return sb_upsert("announcements", payload, on_conflict="ann_id")


def main() -> None:
    ap = argparse.ArgumentParser(description="巨潮套保公告采集 → Supabase")
    ap.add_argument("cmd", choices=["daily", "backfill"])
    ap.add_argument("--days", type=int, default=3, help="daily: 抓最近N天（含今天）")
    ap.add_argument("--year", type=int, help="backfill: 回填整年")
    ap.add_argument("--start", help="backfill: 起始日 YYYY-MM-DD")
    ap.add_argument("--end", help="backfill: 结束日 YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()

    cfg = load_keyword_config()
    today = beijing_today()

    if args.cmd == "daily":
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        edate = today.isoformat()
        rows = fetch_window(sdate, edate, cfg)
        log(f"daily {sdate}~{edate}: 召回 {len(rows)} 条")
        if not args.dry_run:
            n = upsert_announcements(rows)
            log(f"已 upsert {n} 条（新行入 pending，旧行元数据刷新、状态不动）")
        snapshot_csv("fetch_daily", rows)
        return

    # backfill
    if args.year:
        start, end = f"{args.year}-01-01", f"{args.year}-12-31"
    else:
        start, end = args.start, args.end
    if not start or not end:
        raise SystemExit("backfill 需要 --year 或 --start/--end")
    end = min(end, today.isoformat())

    total = 0
    all_rows: list[dict] = []
    for sdate, edate in cninfo.quarter_windows(start, end):
        log(f"===== 回填季度窗 {sdate} ~ {edate} =====")
        try:
            rows = fetch_window(sdate, edate, cfg)
            all_rows.extend(rows)
            if not args.dry_run:
                n = upsert_announcements(rows)
                total += n
                log(f"窗内召回 {len(rows)}，已 upsert {n}（累计 {total}）")
        except Exception as e:
            # 单窗失败不中断整体：幂等设计下，下次重跑同一年即可补全
            log(f"[ERROR] {sdate}~{edate} 失败: {repr(e)[:200]}，继续下一窗")
        cninfo.polite_sleep()
    log(f"回填完成：累计 upsert {total} 条")
    snapshot_csv(f"fetch_backfill_{start[:4]}", all_rows)


if __name__ == "__main__":
    main()
