#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固化指定锚定年度的年报正式公司池。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, log, sb_select

SUPPORTED_CODE_INITIALS = set("0234689")


def classify_scope(scopes: set[str]) -> str:
    if "商品" in scopes and "外汇" in scopes:
        return "商品+外汇"
    if "商品" in scopes:
        return "商品"
    if "外汇" in scopes:
        return "外汇"
    return "其他"


def aggregate_formal(
    event_rows: list[dict],
    company_codes: set[str],
    anchor_year: int = 2025,
) -> list[dict]:
    """按公司聚合指定年度事件；正式分母不因主表缺失或 B 股而缩小。"""
    del company_codes  # 主表完整性由元数据写入阶段修复，不改变固定事件分母。
    bag: dict[str, dict] = {}
    for row in event_rows:
        raw_code = str(row.get("code") or "").strip()
        if not raw_code or not raw_code.isdigit():
            continue
        code = raw_code.zfill(6)
        if (
            len(code) != 6
            or code == "000000"
            or code[0] not in SUPPORTED_CODE_INITIALS
            or row.get("anchor_year") != anchor_year
        ):
            continue
        item = bag.setdefault(code, {
            "code": code,
            "name": row.get("name") or "",
            "industry": row.get("ind_l1") or "未分类",
            "ent_type": row.get("ent_type") or "其他",
            "event_count": 0,
            "latest_ann_date": "",
            "scopes": set(),
            "terms": set(),
        })
        item["event_count"] += 1
        item["latest_ann_date"] = max(
            item["latest_ann_date"], row.get("latest_ann_date") or ""
        )
        item["scopes"].update(row.get("scope") or [])
        item["terms"].update(row.get("instruments") or [])
        item["terms"].update(row.get("underlyings") or [])

    return [
        {
            "code": item["code"],
            "name": item["name"],
            "scope_group": classify_scope(item["scopes"]),
            "industry": item["industry"],
            "ent_type": item["ent_type"],
            "event_count": item["event_count"],
            "latest_ann_date": item["latest_ann_date"],
            "locator_terms": sorted(item["terms"]),
        }
        for item in sorted(bag.values(), key=lambda value: value["code"])
    ]


def fetch_formal_pool(anchor_year: int) -> list[dict]:
    event_rows = sb_select("v_events", {
        "select": (
            "code,name,anchor_year,scope,instruments,underlyings,"
            "latest_ann_date,ind_l1,ent_type"
        ),
        "anchor_year": f"eq.{anchor_year}",
        "order": "code.asc",
    }, paginate=True)
    company_codes = {
        str(row["code"]).zfill(6)
        for row in sb_select("companies", {"select": "code"}, paginate=True)
    }
    rows = aggregate_formal(event_rows, company_codes, anchor_year)
    missing = sum(row["code"] not in company_codes for row in rows)
    if missing:
        log(f"正式池有 {missing} 家尚未进入 companies；元数据写入前将补齐最小主表记录")
    return rows


def validate_pool(rows: list[dict], expected_count: int) -> None:
    codes = [row.get("code") for row in rows]
    if len(rows) != expected_count:
        raise SystemExit(
            f"正式池数量不符：期望 {expected_count}，实际 {len(rows)}；未写入快照"
        )
    if any(not code for code in codes):
        raise SystemExit("正式池包含空代码；未写入快照")
    if any(
        len(str(code)) != 6
        or not str(code).isdigit()
        or str(code) == "000000"
        or str(code)[0] not in SUPPORTED_CODE_INITIALS
        for code in codes
    ):
        raise SystemExit("正式池包含无效或不受支持的证券代码；未写入快照")
    if len(set(codes)) != len(codes):
        raise SystemExit("正式池包含重复代码；未写入快照")
    if any(int(row.get("event_count") or 0) < 1 for row in rows):
        raise SystemExit("正式池包含没有目标年度事件的公司；未写入快照")


def write_pool(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "code", "name", "scope_group", "industry", "ent_type",
            "event_count", "latest_ann_date", "locator_terms",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "locator_terms": json.dumps(
                    row.get("locator_terms") or [], ensure_ascii=False
                ),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="生成年报正式公司池快照")
    parser.add_argument("--anchor-year", type=int, default=2025)
    parser.add_argument("--expected-count", type=int, default=1812)
    parser.add_argument(
        "--output",
        default=str(ROOT / "config" / "annual_formal_2025.csv"),
    )
    args = parser.parse_args()

    rows = fetch_formal_pool(args.anchor_year)
    validate_pool(rows, args.expected_count)
    output = Path(args.output)
    write_pool(output, rows)
    log(f"正式公司池已固化: {output}（{len(rows)} 家）")


if __name__ == "__main__":
    main()
