#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套保公告 5 年历史回填
=====================
按季度切时间窗翻页，避免深分页被截断。
只写入 announcements 表（不写 hedge_events 占位，留给抽取管线处理）。
幂等写入：以巨潮 announcement_id 为去重键（on conflict do nothing）。

用法:
  python scripts/backfill_announcements.py --year 2025
  python scripts/backfill_announcements.py --start-date 2021-01-01 --end-date 2025-12-31
  python scripts/backfill_announcements.py --year 2025 --keywords 套期保值 套保
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cninfo_hedging_crawler import fetch_hedging  # noqa: E402
from ingest_to_supabase import normalize_announcement_row, upsert_table  # noqa: E402


def get_client():
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")
    from supabase import create_client
    return create_client(url, key)


def quarter_windows(start_date: str, end_date: str):
    """按自然季度切窗，避免单查询深翻页被截断。"""
    start = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    current = start
    while current <= end:
        q = (current.month - 1) // 3 + 1
        year = current.year
        if q == 1:
            q_end = dt.date(year, 3, 31)
        elif q == 2:
            q_end = dt.date(year, 6, 30)
        elif q == 3:
            q_end = dt.date(year, 9, 30)
        else:
            q_end = dt.date(year, 12, 31)
        window_end = min(q_end, end)
        yield current.isoformat(), window_end.isoformat()
        current = window_end + dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser(description="套保公告历史回填")
    ap.add_argument("--start-date", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--end-date", help="结束日期 YYYY-MM-DD")
    ap.add_argument("--year", type=int, help="回填整年（覆盖 start-date/end-date）")
    ap.add_argument("--keywords", nargs="+", help="覆盖默认标题关键词")
    args = ap.parse_args()

    if args.year:
        start, end = f"{args.year}-01-01", f"{args.year}-12-31"
    else:
        start, end = args.start_date, args.end_date

    if not start or not end:
        raise SystemExit("需要 --year 或 --start-date/--end-date")

    client = get_client()
    total = 0

    for sdate, edate in quarter_windows(start, end):
        print(f"[回填] {sdate} ~ {edate}")
        try:
            records = fetch_hedging(sdate, edate, keywords=args.keywords)
            rows = [normalize_announcement_row(r) for r in records if r.get("announcement_id")]
            n = upsert_table(client, "announcements", rows, "announcement_id")
            total += n
            print(f"  命中 {len(records)} 条，写入 {n} 条（累计 {total}）")
        except Exception as e:
            print(f"  [ERROR] {sdate}~{edate} 失败: {e}", file=sys.stderr)
            # 继续下一季度，不中断；失败的数据下次重跑会幂等补全
        # 季度之间礼貌限速（与 fetch_hedging 内部的页间限速叠加）
        time.sleep(random.uniform(1.5, 2.0))

    print(f"\n回填完成：共写入 {total} 条")


if __name__ == "__main__":
    main()
