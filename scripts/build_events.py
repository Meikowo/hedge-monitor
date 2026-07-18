#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_events.py —— 事件层聚合（去重的核心）
=============================================
一次套保决策会产生董事会决议、可行性分析、股东大会决议、进展等多份公告；
不做事件层，所有统计都会重复计数。本脚本把「抽取层」确定性地聚合为
「事件层」：hedge_events（一行=一次套保决策）+ event_members（公告挂靠）。

分组启发式（v1，确定性、可无限重跑）：
  1. 计划/可行性/制度类公告：锚定年 = plan_label 中的年份，缺省用公告年份；
     同公司、同锚定年、scope 有交集（或一方为空）→ 归入同一事件，否则新建。
  2. 进展/平仓/风险提示类：挂到同公司 scope 有交集、且 450 天内有计划公告的
     最近事件；找不到则单独成事件并标注「进展(未见计划公告)」。
  3. 事件额度取自审批层级最高的计划公告（股东大会 > 董事会），
     记录 quota_source_ann_id 保证证据链可追溯。
已知局限（记录在 PROJECT.md 风险节）：跨年多期计划、同年追加额度会并入
同一事件；待真实数据验证后在 v2 细化。

运行方式：全量重建（先清空事件层再重算），天然幂等。
未匹配计划的进展类公告使用 ann_id 作为稳定后缀，避免同公司、同年度、同类别的多条进展公告生成相同主键。
  python scripts/build_events.py
  python scripts/build_events.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log, sb_delete, sb_insert, sb_select, snapshot_csv

PLAN_ROLES = {"计划-董事会", "计划-股东大会"}
PRE_ROLES = {"可行性分析", "管理制度"}
FOLLOW_MAX_DAYS = 450
YEAR_RE = re.compile(r"(20\d{2})")


def load_rows() -> list[dict]:
    rows = sb_select("announcements", {
        "select": ("ann_id,code,name,ann_date,"
                   "extractions(is_hedge_related,ann_role,scope,instruments,"
                   "underlyings,venue,approval_level,plan_label,period_text,"
                   "is_revolving,use_own_funds)"),
        "status": "eq.extracted",
        "order": "code.asc,ann_date.asc,ann_id.asc",
    }, paginate=True)
    out = []
    for r in rows:
        ext = r.get("extractions")
        if isinstance(ext, list):
            ext = ext[0] if ext else None
        if not ext or not ext.get("is_hedge_related") or not r.get("code"):
            continue
        out.append({**r, "ext": ext})
    return out


def anchor_year(ann: dict) -> int:
    label = ann["ext"].get("plan_label") or ""
    m = YEAR_RE.search(label)
    if m:
        return int(m.group(1))
    return int((ann.get("ann_date") or "1900")[:4])


def scopes_of(ann: dict) -> set[str]:
    return set(ann["ext"].get("scope") or [])


def overlap(a: set, b: set) -> bool:
    return (not a) or (not b) or bool(a & b)


class Event:
    def __init__(self, ann: dict, year: int, standalone_progress: bool = False):
        scope_key = "+".join(sorted(scopes_of(ann))) or "未披露"
        self.key = f"{ann['code']}|{year}|{scope_key}"
        if standalone_progress:
            # 同一公司/年度/类别可能有多条未匹配计划的进展公告；
            # 仅使用 |p 会让多个 Event 共享 event_key，最终在写库时触发 23505。
            # ann_id 是公告层主键，作为后缀可保证稳定且可重跑。
            self.key += f"|p|{ann['ann_id']}"
        self.code, self.year = ann["code"], year
        self.scopes: set[str] = set()
        self.members: list[dict] = []
        self.standalone_progress = standalone_progress
        self.add(ann)

    def add(self, ann: dict) -> None:
        self.members.append(ann)
        self.scopes |= scopes_of(ann)

    @property
    def last_plan_date(self) -> str | None:
        dates = [m["ann_date"] for m in self.members
                 if m["ext"]["ann_role"] in (PLAN_ROLES | PRE_ROLES) and m.get("ann_date")]
        return max(dates) if dates else None


def group(rows: list[dict]) -> list[Event]:
    by_code: dict[str, list[Event]] = {}
    for ann in rows:
        code = ann["code"]
        events = by_code.setdefault(code, [])
        role = ann["ext"]["ann_role"]
        if role in PLAN_ROLES or role in PRE_ROLES:
            y = anchor_year(ann)
            home = next((e for e in events
                         if e.year == y and not e.standalone_progress
                         and overlap(e.scopes, scopes_of(ann))), None)
            (home.add(ann) if home else events.append(Event(ann, y)))
        else:  # 进展/平仓/风险提示/其他
            cands = []
            for e in events:
                lp = e.last_plan_date
                if not lp or not overlap(e.scopes, scopes_of(ann)):
                    continue
                gap = (dt.date.fromisoformat(ann["ann_date"])
                       - dt.date.fromisoformat(lp)).days
                if 0 <= gap <= FOLLOW_MAX_DAYS:
                    cands.append((lp, e))
            if cands:
                max(cands, key=lambda x: x[0])[1].add(ann)
            else:
                events.append(Event(ann, anchor_year(ann), standalone_progress=True))
    return [e for evs in by_code.values() for e in evs]


def pick_quota_source(ev: Event) -> dict | None:
    for role in ("计划-股东大会", "计划-董事会"):
        cands = [m for m in ev.members if m["ext"]["ann_role"] == role]
        if cands:
            return max(cands, key=lambda m: m["ann_date"] or "")
    return None


def fetch_quotas(ann_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for i in range(0, len(ann_ids), 80):
        chunk = ann_ids[i:i + 80]
        rows = sb_select("quota_items", {
            "select": "ann_id,scope,basis,amount,currency,raw_text,amount_verified",
            "ann_id": f"in.({','.join(chunk)})",
        }, paginate=True)
        for r in rows:
            out.setdefault(r["ann_id"], []).append(
                {k: v for k, v in r.items() if k != "ann_id"})
    return out


def stage_of(roles: set[str]) -> str:
    if "计划-股东大会" in roles:
        return "股东大会通过"
    if "计划-董事会" in roles:
        return "董事会通过"
    if roles & PRE_ROLES:
        return "仅制度/可行性"
    return "进展(未见计划公告)"


def build_rows(events: list[Event]) -> tuple[list[dict], list[dict]]:
    src_map = {e.key: pick_quota_source(e) for e in events}
    quota_map = fetch_quotas([m["ann_id"] for m in src_map.values() if m])
    ev_rows, member_rows = [], []
    for e in events:
        roles = {m["ext"]["ann_role"] for m in e.members}
        dates = sorted(m["ann_date"] for m in e.members if m.get("ann_date"))
        src = src_map[e.key]
        base = (src or e.members[0])["ext"]
        union = lambda field: sorted({x for m in e.members
                                      for x in (m["ext"].get(field) or [])})
        venues = [m["ext"].get("venue") for m in e.members
                  if m["ext"].get("venue") and m["ext"]["venue"] != "未披露"]
        ev_rows.append({
            "event_key": e.key, "code": e.code,
            "name": e.members[-1].get("name"),
            "anchor_year": e.year,
            "scope": sorted(e.scopes) or ["未披露"],
            "plan_label": base.get("plan_label"),
            "stage": stage_of(roles),
            "approval_level": base.get("approval_level") or "未披露",
            "first_ann_date": dates[0] if dates else None,
            "latest_ann_date": dates[-1] if dates else None,
            "ann_count": len(e.members),
            "ann_roles": sorted(roles),
            "instruments": union("instruments"),
            "underlyings": union("underlyings"),
            "venue": base.get("venue") if base.get("venue") != "未披露"
                     else (venues[0] if venues else "未披露"),
            "period_text": base.get("period_text"),
            "is_revolving": base.get("is_revolving"),
            "use_own_funds": base.get("use_own_funds"),
            "quota": quota_map.get(src["ann_id"], []) if src else [],
            "quota_source_ann_id": src["ann_id"] if src else None,
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        member_rows += [{"event_key": e.key, "ann_id": m["ann_id"]} for m in e.members]
    return ev_rows, member_rows


def main() -> None:
    ap = argparse.ArgumentParser(description="事件层全量重建")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = load_rows()
    log(f"参与聚合的套保相关公告 {len(rows)} 条")
    events = group(rows)
    ev_rows, member_rows = build_rows(events)
    keys = [row["event_key"] for row in ev_rows]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        raise RuntimeError(f"聚合生成重复 event_key：{duplicate_keys[:5]}")
    log(f"聚合为 {len(ev_rows)} 个事件；多公告事件 "
        f"{sum(1 for e in ev_rows if e['ann_count'] > 1)} 个")

    snapshot_csv("events_build", [{k: v for k, v in e.items() if k != 'quota'}
                                  for e in ev_rows])
    if args.dry_run:
        log("dry-run：未写库")
        return
    # 全量重建：先清空再插入（派生表，确定性键保证跨次运行稳定）
    sb_delete("event_members", {"ann_id": "not.is.null"})
    sb_delete("hedge_events", {"event_key": "not.is.null"})
    sb_insert("hedge_events", ev_rows)
    sb_insert("event_members", member_rows)
    log("事件层重建完成")


if __name__ == "__main__":
    main()
