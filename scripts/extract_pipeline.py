#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套保公告抽取编排
================
流程: Supabase 取待抽取公告 -> 下载PDF -> 上传Supabase Storage留档 -> LLM抽取 -> 回写

"待抽取"的定义: announcements 表里 is_candidate=true 的公告,
其 hedge_events 行 extracted_at 为空(从未真抽过) 或 need_review=true 且要求重试。
本脚本默认只处理"从未真抽过"的,避免重复花钱。

用法:
  python scripts/extract_pipeline.py --limit 30           # 抽最近30条待抽公告
  python scripts/extract_pipeline.py --limit 30 --dry-run # 抽但不回写,只打印
  python scripts/extract_pipeline.py --since 2026-06-01   # 只抽该日期后发布的
  python scripts/extract_pipeline.py --no-storage         # 不上传PDF到Storage

环境变量: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / DEEPSEEK_API_KEY
          STORAGE_BUCKET 默认 announcements-pdf
依赖: pip install requests pymupdf openai supabase python-dotenv
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_core as ec  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BUCKET = os.getenv("STORAGE_BUCKET", "announcements-pdf")


def get_client():
    load_dotenv(ROOT / ".env")
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    from supabase import create_client
    return create_client(url, key)


def fetch_pending(client, limit: int, since: str | None) -> list[dict]:
    """取 is_candidate 且尚未真抽取(extracted_at is null)的公告。
    依赖 hedge_events.extracted_at 列(见 03_extraction.sql)。"""
    q = (client.table("announcements")
         .select("announcement_id, sec_code, sec_name, title, pdf_url, "
                 "hedge_events(extracted_at)")
         .eq("is_candidate", True)
         .order("publish_time", desc=True)
         .limit(limit * 3))  # 多取些,过滤掉已抽的后再截断
    if since:
        q = q.gte("publish_time", since)
    rows = q.execute().data or []
    pending = []
    for r in rows:
        he = r.get("hedge_events")
        # he 可能是 list / dict / None,取决于关系基数;统一判断 extracted_at
        already = False
        if isinstance(he, list):
            already = any((x or {}).get("extracted_at") for x in he)
        elif isinstance(he, dict):
            already = bool(he.get("extracted_at"))
        if not already and r.get("pdf_url"):
            pending.append(r)
        if len(pending) >= limit:
            break
    return pending


def download_pdf(pdf_url: str) -> bytes | None:
    r = requests.get(pdf_url, headers={"User-Agent": UA}, timeout=60)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    return r.content


def upload_storage(client, announcement_id: str, content: bytes) -> str | None:
    """上传到 Supabase Storage 留档,返回存储路径。已存在则忽略错误。"""
    path = f"{announcement_id}.pdf"
    try:
        client.storage.from_(BUCKET).upload(
            path, content,
            {"content-type": "application/pdf", "upsert": "true"},
        )
        return path
    except Exception as e:
        # 桶不存在 / 重复等;不阻断主流程
        print(f"    [storage] 上传 {path} 失败(不影响抽取): {repr(e)[:80]}", file=sys.stderr)
        return None


def write_back(client, event_row: dict, evidence_rows: list[dict], storage_path: str | None):
    """回写 hedge_events(带 extracted_at)和 extraction_evidence。"""
    import datetime as dt
    # 只保留 hedge_events 实际存在的列(下划线开头的扩展字段需 schema 支持,否则丢弃)
    core_cols = {
        "announcement_id", "hedge_type", "instrument_type", "underlying_asset",
        "risk_type", "approval_level", "authorization_period", "contract_value_limit",
        "contract_value_currency", "contract_value_raw_text", "confidence", "need_review",
        # 扩展列(在 03_extraction.sql 中添加):
        "trade_venue", "contract_value_basis", "is_revolving", "use_own_funds",
        "is_hedging_announcement", "extracted_at", "pdf_storage_path",
    }
    row = {k: v for k, v in event_row.items() if not k.startswith("_")}
    # 把下划线扩展字段改名为正式列名
    for ext in ("trade_venue", "contract_value_basis", "is_revolving",
                "use_own_funds", "is_hedging_announcement"):
        if f"_{ext}" in event_row:
            row[ext] = event_row[f"_{ext}"]
    row["extracted_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    row["pdf_storage_path"] = storage_path
    row = {k: v for k, v in row.items() if k in core_cols}

    client.table("hedge_events").upsert(row, on_conflict="announcement_id").execute()
    if evidence_rows:
        # 先删旧证据再插,避免重复
        client.table("extraction_evidence").delete().eq(
            "announcement_id", row["announcement_id"]).execute()
        client.table("extraction_evidence").insert(evidence_rows).execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--since", help="只抽该日期后发布的公告 YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="抽取但不回写,只打印结果")
    ap.add_argument("--no-storage", action="store_true", help="不上传PDF到Storage")
    args = ap.parse_args()

    if not (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
        raise SystemExit("缺少 LLM_API_KEY(MiniMax 等厂商的 API key)")

    client = get_client()
    pending = fetch_pending(client, args.limit, args.since)
    print(f"待抽取公告 {len(pending)} 条\n")

    ok = fail = review = 0
    for i, r in enumerate(pending, 1):
        aid, title = r["announcement_id"], r.get("title", "")
        print(f"[{i}/{len(pending)}] {r.get('sec_name')} | {title[:40]}")
        try:
            content = download_pdf(r["pdf_url"])
            if not content:
                print("    PDF下载失败或非PDF,跳过"); fail += 1; continue

            storage_path = None
            if not args.no_storage and not args.dry_run:
                storage_path = upload_storage(client, aid, content)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tf:
                tf.write(content); tf.flush()
                body = ec.extract_pdf_text(tf.name)

            if len(body) < 50:
                print("    正文过短(疑似扫描件),跳过抽取"); fail += 1; continue

            extracted = ec.call_deepseek(ec.build_messages(title, body))
            event_row = ec.to_hedge_event_row(aid, extracted)
            evidence_rows = ec.to_evidence_rows(aid, extracted)

            limit_str = (f"{event_row['contract_value_limit']:,.0f}"
                         if event_row['contract_value_limit'] else "—")
            print(f"    {event_row['hedge_type']} | 额度 {limit_str} "
                  f"{event_row.get('contract_value_currency') or ''} | "
                  f"品种 {event_row.get('underlying_asset') or '—'} | "
                  f"置信 {event_row.get('confidence')} | 复核 {event_row['need_review']}")

            if event_row["need_review"]:
                review += 1
            if not args.dry_run:
                write_back(client, event_row, evidence_rows, storage_path)
            ok += 1
        except Exception as e:
            print(f"    抽取异常: {repr(e)[:100]}", file=sys.stderr)
            traceback.print_exc()
            fail += 1
        time.sleep(0.5)  # 礼貌限速

    print(f"\n完成: 成功 {ok}、失败 {fail}、其中需人工复核 {review}")
    if args.dry_run:
        print("(dry-run 未回写数据库)")


if __name__ == "__main__":
    main()
