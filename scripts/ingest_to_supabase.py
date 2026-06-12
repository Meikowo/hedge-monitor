#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把巨潮套保公告采集结果写入 Supabase。

运行前：
  1) pip install -r requirements.txt
  2) cp .env.example .env，并填写 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
  3) 在 Supabase SQL Editor 执行 supabase/schema.sql

示例：
  python scripts/ingest_to_supabase.py daily --days 3
  python scripts/ingest_to_supabase.py fulltext --days 7 --keyword 套期保值
  python scripts/ingest_to_supabase.py annual --year 2025
  python scripts/ingest_to_supabase.py backfill --start 2025-01 --end 2025-12
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from supabase import create_client

# 让脚本可以 import 项目根目录的 cninfo_hedging_crawler.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cninfo_hedging_crawler import (  # noqa: E402
    beijing_today,
    fetch_annual_reports,
    fetch_fulltext,
    fetch_hedging,
    month_windows,
)

CN_TZ = ZoneInfo("Asia/Shanghai")


def parse_cn_time(value: str | None) -> str | None:
    """把 'YYYY-MM-DD HH:MM:SS' 转成带 +08:00 的 ISO，方便 Supabase timestamptz 正确识别。"""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        d = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TZ)
        return d.isoformat()
    except ValueError:
        return value


def get_client():
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY。请复制 .env.example 为 .env 后填写。")
    return create_client(url, key)


def chunked(items: list[dict[str, Any]], size: int = 200) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def normalize_announcement_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "announcement_id": str(r.get("announcement_id") or ""),
        "sec_code": r.get("sec_code"),
        "sec_name": r.get("sec_name"),
        "title": r.get("title") or "",
        "publish_time": parse_cn_time(r.get("publish_time")),
        "adjunct_url": r.get("adjunct_url"),
        "pdf_url": r.get("pdf_url"),
        "source": r.get("source"),
        "is_candidate": True,
    }


def normalize_annual_row(r: dict[str, Any], report_year: int | None = None) -> dict[str, Any]:
    return {
        "announcement_id": str(r.get("announcement_id") or ""),
        "sec_code": r.get("sec_code"),
        "sec_name": r.get("sec_name"),
        "title": r.get("title") or "",
        "report_year": report_year,
        "publish_time": parse_cn_time(r.get("publish_time")),
        "adjunct_url": r.get("adjunct_url"),
        "pdf_url": r.get("pdf_url"),
        "source": r.get("source") or "annual",
        "is_revised": bool(r.get("is_revised")),
    }


def make_basic_tips(r: dict[str, Any]) -> list[dict[str, Any]]:
    """基于标题和关键词的轻量提示。后续接 PDF 解析/LLM 后可替换为更深的提示。"""
    aid = str(r.get("announcement_id") or "")
    title = r.get("title") or ""
    source = r.get("source") or ""
    tips: list[dict[str, Any]] = []

    def add(tip_type: str, level: str, tip_title: str, msg: str):
        tips.append({
            "announcement_id": aid,
            "tip_type": tip_type,
            "tip_level": level,
            "tip_title": tip_title,
            "tip_message": msg,
        })

    if "套期保值" in title or "套保" in title:
        add("hedging_title_hit", "info", "标题命中套保", "公告标题包含套期保值/套保，建议进一步查看原文。")
    if "远期结售汇" in title or "外汇" in title:
        add("fx_hedging", "notice", "疑似外汇套保", "标题出现远期结售汇/外汇衍生品，可能涉及汇率风险管理。")
    if "衍生品" in title:
        add("derivative_trading", "notice", "涉及衍生品交易", "标题出现衍生品交易，需要区分套保目的与非套保交易。")
    if "期货" in title:
        add("commodity_or_futures", "notice", "涉及期货工具", "标题出现期货，可能涉及商品价格风险管理。")
    if re.search(r"亏损|浮亏|损失|公允价值变动损失", title):
        add("loss_word", "warning", "标题出现亏损相关表述", "标题含亏损/浮亏/损失等词，建议重点核对原文。")
    if source.startswith("fulltext"):
        add("fulltext_hit", "review", "正文检索命中", "该公告来自全文检索，噪音较高，需要二次确认是否真正为套保事项。")
    if not tips:
        add("candidate", "info", "候选公告", "公告由关键词召回，建议查看原文确认。")
    return tips


def infer_event_from_title(r: dict[str, Any]) -> dict[str, Any]:
    """只根据标题做非常轻量的 hedge_events 占位，避免误装成精确抽取。"""
    title = r.get("title") or ""
    hedge_type = None
    instruments: list[str] = []
    risks: list[str] = []
    need_review = True
    confidence = 0.35

    if "外汇" in title or "远期结售汇" in title:
        hedge_type = "外汇套期保值/外汇衍生品"
        risks.append("汇率风险")
        if "远期结售汇" in title:
            instruments.append("远期结售汇")
        confidence = 0.55
    elif "期货" in title or "商品" in title:
        hedge_type = "商品/期货套期保值"
        risks.append("商品价格风险")
        if "期货" in title:
            instruments.append("期货")
        confidence = 0.50
    elif "套期保值" in title or "套保" in title:
        hedge_type = "套期保值"
        confidence = 0.45
    elif "衍生品" in title:
        hedge_type = "衍生品交易，需确认是否套保"
        confidence = 0.35

    return {
        "announcement_id": str(r.get("announcement_id") or ""),
        "hedge_type": hedge_type,
        "instrument_type": instruments or None,
        "underlying_asset": None,
        "risk_type": risks or None,
        "approval_level": None,
        "authorization_period": None,
        "contract_value_limit": None,
        "contract_value_currency": None,
        "contract_value_raw_text": None,
        "confidence": confidence,
        "need_review": need_review,
    }


def upsert_table(client, table: str, rows: list[dict[str, Any]], conflict: str):
    if not rows:
        return 0
    total = 0
    for batch in chunked(rows):
        client.table(table).upsert(batch, on_conflict=conflict).execute()
        total += len(batch)
    return total


def ingest_announcements(records: list[dict[str, Any]]):
    client = get_client()
    rows = [normalize_announcement_row(r) for r in records if r.get("announcement_id")]
    event_rows = [infer_event_from_title(r) for r in records if r.get("announcement_id")]
    tip_rows: list[dict[str, Any]] = []
    for r in records:
        tip_rows.extend(make_basic_tips(r))

    n_ann = upsert_table(client, "announcements", rows, "announcement_id")
    # hedge_events.announcement_id 是 unique
    n_evt = upsert_table(client, "hedge_events", event_rows, "announcement_id")
    n_tip = upsert_table(client, "tips", tip_rows, "announcement_id,tip_type,tip_title")
    return n_ann, n_evt, n_tip


def ingest_annual(records: list[dict[str, Any]], year: int):
    client = get_client()
    rows = [normalize_annual_row(r, report_year=year) for r in records if r.get("announcement_id")]
    return upsert_table(client, "annual_reports", rows, "announcement_id")


def main():
    ap = argparse.ArgumentParser(description="巨潮公告 -> Supabase")
    ap.add_argument("cmd", choices=["daily", "fulltext", "annual", "backfill"])
    ap.add_argument("--days", type=int, default=int(os.getenv("CRAWL_DAYS", "3")))
    ap.add_argument("--keyword", default="套期保值")
    ap.add_argument("--keywords", nargs="+", help="覆盖默认标题关键词")
    ap.add_argument("--year", type=int)
    ap.add_argument("--start", help="backfill 起始月 YYYY-MM")
    ap.add_argument("--end", help="backfill 结束月 YYYY-MM")
    args = ap.parse_args()

    today = beijing_today()

    if args.cmd == "daily":
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        edate = today.isoformat()
        records = fetch_hedging(sdate, edate, keywords=args.keywords)
        n_ann, n_evt, n_tip = ingest_announcements(records)
        print(f"daily {sdate}~{edate}: 抓到 {len(records)} 条；写入公告 {n_ann}、事件占位 {n_evt}、提示 {n_tip}")

    elif args.cmd == "fulltext":
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        edate = today.isoformat()
        records = fetch_fulltext(sdate, edate, keyword=args.keyword)
        n_ann, n_evt, n_tip = ingest_announcements(records)
        print(f"fulltext {sdate}~{edate}: 抓到 {len(records)} 条；写入公告 {n_ann}、事件占位 {n_evt}、提示 {n_tip}")

    elif args.cmd == "annual":
        if not args.year:
            raise SystemExit("annual 需要 --year，例如 --year 2025")
        records = fetch_annual_reports(args.year)
        n = ingest_annual(records, args.year)
        print(f"annual {args.year}: 抓到 {len(records)} 份；写入年报 {n}")

    elif args.cmd == "backfill":
        if not args.start or not args.end:
            raise SystemExit("backfill 需要 --start YYYY-MM --end YYYY-MM")
        total = 0
        for sdate, edate in month_windows(args.start, args.end):
            records = fetch_hedging(sdate, edate, keywords=args.keywords)
            n_ann, n_evt, n_tip = ingest_announcements(records)
            total += n_ann
            print(f"{sdate[:7]}: 抓到 {len(records)}；写入公告 {n_ann}、事件 {n_evt}、提示 {n_tip}；累计公告 {total}")


if __name__ == "__main__":
    main()
