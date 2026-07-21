#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从事件池确定性选取 2025FY 年报 POC 的 30 家公司。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, log, sb_select

GROUPS = ("商品", "外汇", "商品+外汇")


def classify(scopes: set[str]) -> str:
    if "商品" in scopes and "外汇" in scopes:
        return "商品+外汇"
    if "商品" in scopes:
        return "商品"
    return "外汇"


def aggregate() -> list[dict]:
    rows = sb_select("v_events", {
        "select": "code,name,scope,instruments,underlyings,latest_ann_date,ind_l1,ent_type",
        "order": "latest_ann_date.desc",
    }, paginate=True)
    bag: dict[str, dict] = {}
    for row in rows:
        code = row.get("code")
        # 首轮 POC 只覆盖 A 股；B 股代码/组织号映射单独留到扩量阶段处理。
        if not code or str(code).startswith(("2", "9")):
            continue
        item = bag.setdefault(code, {
            "code": code, "name": row.get("name") or "", "industry": row.get("ind_l1") or "未分类",
            "ent_type": row.get("ent_type") or "其他", "event_count": 0,
            "latest_ann_date": "", "scopes": set(), "terms": set(),
        })
        item["event_count"] += 1
        item["latest_ann_date"] = max(item["latest_ann_date"], row.get("latest_ann_date") or "")
        item["scopes"].update(row.get("scope") or [])
        item["terms"].update(row.get("instruments") or [])
        item["terms"].update(row.get("underlyings") or [])
    return list(bag.values())


def choose(candidates: list[dict], per_group: int = 10) -> list[dict]:
    selected: list[dict] = []
    for group in GROUPS:
        pool = [x for x in candidates if classify(x["scopes"]) == group]
        pool.sort(key=lambda x: (-x["event_count"], x["industry"], x["ent_type"], x["code"]))
        used_industries: defaultdict[str, int] = defaultdict(int)
        used_types: defaultdict[str, int] = defaultdict(int)
        chosen: list[dict] = []
        while pool and len(chosen) < per_group:
            best = min(pool, key=lambda x: (
                used_industries[x["industry"]], used_types[x["ent_type"]],
                -x["event_count"], x["code"],
            ))
            pool.remove(best)
            chosen.append(best)
            used_industries[best["industry"]] += 1
            used_types[best["ent_type"]] += 1
        selected.extend(chosen)
    return selected


def main() -> None:
    ap = argparse.ArgumentParser(description="选择 M4a 2025FY POC 公司")
    ap.add_argument("--per-group", type=int, default=10)
    ap.add_argument("--output", default=str(ROOT / "config" / "annual_poc_2025.csv"))
    args = ap.parse_args()
    rows = choose(aggregate(), args.per_group)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "code", "name", "scope_group", "industry", "ent_type", "event_count",
            "latest_ann_date", "locator_terms",
        ])
        writer.writeheader()
        for item in rows:
            writer.writerow({
                "code": item["code"], "name": item["name"],
                "scope_group": classify(item["scopes"]), "industry": item["industry"],
                "ent_type": item["ent_type"], "event_count": item["event_count"],
                "latest_ann_date": item["latest_ann_date"],
                "locator_terms": json.dumps(sorted(item["terms"]), ensure_ascii=False),
            })
    log(f"POC 样本已生成: {out}（{len(rows)} 家）")


if __name__ == "__main__":
    main()
