#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 akshare 拉取 A 股公司基础信息，灌入 Supabase companies 表。
v2 修复与增强（2026-07-07）：
  1) 行业覆盖：原版只有深市/北交所有行业（沪市+科创板 ~2300 家为空）。
     现在用东方财富行业板块（~86 个一级行业）给【全市场】统一打行业标签，
     粒度远优于证监会门类（"C 制造业"一类占全市场 4 成，筛选没有意义）；
     东财缺失的个股回落到交易所接口的证监会行业。
  2) 幂等语义：原版 on conflict do nothing —— 表里已有行（哪怕字段是空的）
     永远不会被更新，导致先跑过数据 SQL 后脚本形同虚设。
     现在改为 do update，且【无行业的行分组单独写】，绝不会用 None 把已有值洗掉；
     ent_type / org_id / market_cap 不在写入列里，永远不会被本脚本触碰。
  3) 日期序列化：date 对象直接传 supabase-py 会抛 "not JSON serializable"，
     现在统一转 ISO 字符串。
  4) 新增 --emit-sql：把结果导出成幂等 SQL 文件（ON CONFLICT 补空不覆盖），
     供无法跑 Python 时在 Supabase SQL Editor 手工执行。

用法:
  python scripts/build_companies.py                       # 拉数据并写入 Supabase
  python scripts/build_companies.py --dry-run             # 只打印统计，不写库
  python scripts/build_companies.py --emit-sql out.sql    # 另存为幂等 SQL
  python scripts/build_companies.py --skip-em             # 跳过东财行业(网络差时)

依赖: pip install akshare pandas supabase python-dotenv
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ----------------------------- Supabase -----------------------------
def get_client():
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")
    from supabase import create_client
    return create_client(url, key)


# ----------------------------- 板块推断 -----------------------------
def infer_plate_from_code(code: str) -> str | None:
    """根据代码前缀推断板块（上海/北京无板块列时兜底）。"""
    c = str(code).strip()
    if c.startswith("688"):
        return "科创板"
    if c.startswith("60"):
        return "主板"
    if c.startswith(("300", "301", "302")):
        return "创业板"
    if c.startswith("00"):
        return "主板"
    if c.startswith(("43", "83", "87", "88", "92")):
        return "北交所"
    return None


# ----------------------------- 东财行业（全市场统一口径） -----------------------------
def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def fetch_em_industry_map(sleep_sec: float = 0.4) -> dict[str, str]:
    """东方财富行业板块 -> {股票代码: 行业名}。约 86 个板块、逐板块取成分。
    单板块失败只警告不中断；整体失败返回空 dict（上层回落到证监会行业）。"""
    code2ind: dict[str, str] = {}
    try:
        boards = ak.stock_board_industry_name_em()
    except Exception as e:
        print(f"  [warn] 东财行业板块列表拉取失败，将只用证监会行业: {e}")
        return code2ind

    name_col = _pick_col(boards, ["板块名称", "板块名"])
    if not name_col:
        print(f"  [warn] 东财板块列缺失(实际列: {list(boards.columns)})，跳过")
        return code2ind

    names = [str(x).strip() for x in boards[name_col].dropna().tolist()]
    print(f"[akshare] 东财行业板块共 {len(names)} 个，逐个取成分（约 1 分钟）...")
    for i, name in enumerate(names, 1):
        try:
            cons = ak.stock_board_industry_cons_em(symbol=name)
            ccol = _pick_col(cons, ["代码", "股票代码"])
            if not ccol:
                continue
            for code in cons[ccol].astype(str).str.strip().str.zfill(6):
                # 个股可能出现在多个口径里；先到先得即可（东财一级行业互斥）
                code2ind.setdefault(code, name)
        except Exception as e:
            print(f"  [warn] 板块「{name}」成分失败: {repr(e)[:60]}")
        if i % 20 == 0:
            print(f"  ... {i}/{len(names)}，已覆盖 {len(code2ind)} 只")
        time.sleep(sleep_sec)
    print(f"  东财行业覆盖 {len(code2ind)} 只个股")
    return code2ind


# ----------------------------- 交易所基础信息 -----------------------------
def fetch_a_stock_info(skip_em: bool = False) -> pd.DataFrame:
    print("[akshare] 拉取 A 股基础列表...")
    df_main = ak.stock_info_a_code_name()
    df_main.rename(columns={"code": "sec_code", "name": "sec_name"}, inplace=True)
    df_main["sec_code"] = df_main["sec_code"].astype(str).str.strip().str.zfill(6)
    df_main["sec_name"] = df_main["sec_name"].astype(str).str.strip()

    # 上海：补充上市日期
    print("[akshare] 拉取上海上市日期...")
    try:
        df_sh = ak.stock_info_sh_name_code()
        df_sh = df_sh[["证券代码", "上市日期"]].copy()
        df_sh.rename(columns={"证券代码": "sec_code", "上市日期": "list_date"}, inplace=True)
        df_sh["sec_code"] = df_sh["sec_code"].astype(str).str.strip().str.zfill(6)
        df_sh["list_date"] = pd.to_datetime(df_sh["list_date"], errors="coerce").dt.date
        df_main = df_main.merge(df_sh, on="sec_code", how="left")
    except Exception as e:
        print(f"  [warn] 上海数据失败: {e}")
        df_main["list_date"] = None

    # 深圳：补充板块、证监会行业、上市日期
    print("[akshare] 拉取深圳板块/行业/上市日期...")
    try:
        df_sz = ak.stock_info_sz_name_code()
        df_sz = df_sz[["板块", "A股代码", "A股上市日期", "所属行业"]].copy()
        df_sz.rename(columns={
            "板块": "plate",
            "A股代码": "sec_code",
            "A股上市日期": "list_date_sz",
            "所属行业": "csrc_industry",
        }, inplace=True)
        df_sz["sec_code"] = df_sz["sec_code"].astype(str).str.strip().str.zfill(6)
        df_sz["list_date_sz"] = pd.to_datetime(df_sz["list_date_sz"], errors="coerce").dt.date
        df_main = df_main.merge(df_sz, on="sec_code", how="left")
        df_main["list_date"] = df_main["list_date_sz"].combine_first(df_main["list_date"])
        df_main.drop(columns=["list_date_sz"], inplace=True, errors="ignore")
    except Exception as e:
        print(f"  [warn] 深圳数据失败: {e}")
        df_main["plate"] = None
        df_main["csrc_industry"] = None

    # 北交所：补充证监会行业、上市日期
    print("[akshare] 拉取北交所行业/上市日期...")
    try:
        df_bj = ak.stock_info_bj_name_code()
        df_bj = df_bj[["证券代码", "所属行业", "上市日期"]].copy()
        df_bj.rename(columns={
            "证券代码": "sec_code",
            "所属行业": "csrc_industry_bj",
            "上市日期": "list_date_bj",
        }, inplace=True)
        df_bj["sec_code"] = df_bj["sec_code"].astype(str).str.strip().str.zfill(6)
        df_bj["list_date_bj"] = pd.to_datetime(df_bj["list_date_bj"], errors="coerce").dt.date
        df_main = df_main.merge(df_bj, on="sec_code", how="left")
        df_main["csrc_industry"] = df_main["csrc_industry"].combine_first(df_main["csrc_industry_bj"])
        df_main["list_date"] = df_main["list_date"].combine_first(df_main["list_date_bj"])
        df_main.drop(columns=["csrc_industry_bj", "list_date_bj"], inplace=True, errors="ignore")
    except Exception as e:
        print(f"  [warn] 北交所数据失败: {e}")

    # 行业主口径：东财一级行业（全市场统一）；缺失回落证监会行业
    if skip_em:
        em_map: dict[str, str] = {}
        print("[skip] 按参数跳过东财行业")
    else:
        em_map = fetch_em_industry_map()
    df_main["sw_industry"] = df_main["sec_code"].map(em_map)
    df_main["sw_industry"] = df_main["sw_industry"].combine_first(df_main["csrc_industry"])
    df_main.drop(columns=["csrc_industry"], inplace=True, errors="ignore")

    # 板块兜底
    mask_no_plate = df_main["plate"].isna()
    df_main.loc[mask_no_plate, "plate"] = df_main.loc[mask_no_plate, "sec_code"].apply(infer_plate_from_code)

    # 清理 'nan' 字符串
    for col in ("plate", "sw_industry"):
        df_main[col] = df_main[col].astype(str).str.strip()
        df_main.loc[df_main[col].isin(("nan", "None", "")), col] = None

    return df_main


# ----------------------------- 行构造与写入 -----------------------------
def build_rows(df: pd.DataFrame) -> list[dict]:
    """转成 dict 列表。list_date 转 ISO 字符串（date 对象无法 JSON 序列化）。
    只包含本脚本有数据来源的列，ent_type/org_id/market_cap 永不触碰。"""
    rows = []
    for _, r in df.iterrows():
        ld = r.get("list_date")
        rows.append({
            "sec_code": r["sec_code"],
            "sec_name": r["sec_name"],
            "sw_industry": r["sw_industry"] if pd.notna(r["sw_industry"]) else None,
            "plate": r["plate"] if pd.notna(r["plate"]) else None,
            "list_date": ld.isoformat() if (ld is not None and pd.notna(ld)) else None,
        })
    return rows


def upsert_companies(client, rows: list[dict], batch_size: int = 500) -> int:
    """按「非空字段集合」分组提交 do-update：
    None 的字段直接不进 payload，于是 upsert 的 SET 列表里就没有它——
    从机制上杜绝用空值覆盖库里已有的行业/板块/日期。
    （PostgREST 要求同一请求内各行列一致，所以必须按字段集合分组分别提交。）"""
    groups: dict[frozenset, list[dict]] = {}
    for r in rows:
        payload = {k: v for k, v in r.items() if v is not None}
        groups.setdefault(frozenset(payload.keys()), []).append(payload)

    total = 0
    for keys, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        label = "+".join(sorted(k for k in keys if k not in ("sec_code", "sec_name")))
        for i in range(0, len(group), batch_size):
            batch = group[i:i + batch_size]
            client.table("companies").upsert(batch, on_conflict="sec_code").execute()
            total += len(batch)
        print(f"  [{label or '仅代码+名称'}] 共 {len(group)} 行 已写入")
    return total


def emit_sql(rows: list[dict], path: Path):
    """导出幂等 SQL（补空不覆盖），供 SQL Editor 手工执行。"""
    def lit(v):
        return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"
    parts = [
        "-- companies 数据导入（build_companies.py --emit-sql 生成）",
        f"-- 生成时间: {dt.date.today().isoformat()} · 幂等，可重复执行",
        "",
    ]
    conflict = (
        "ON CONFLICT (sec_code) DO UPDATE SET\n"
        "    sec_name    = excluded.sec_name,\n"
        "    sw_industry = coalesce(excluded.sw_industry, companies.sw_industry),\n"
        "    plate       = coalesce(excluded.plate, companies.plate),\n"
        "    list_date   = coalesce(excluded.list_date, companies.list_date),\n"
        "    updated_at  = now();"
    )
    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        parts.append("INSERT INTO public.companies (sec_code, sec_name, sw_industry, plate, list_date) VALUES")
        parts.append(",\n".join(
            f"    ({lit(r['sec_code'])}, {lit(r['sec_name'])}, {lit(r['sw_industry'])}, "
            f"{lit(r['plate'])}, {lit(r['list_date'])})" for r in chunk))
        parts.append(conflict)
        parts.append("")
    path.write_text("\n".join(parts), encoding="utf-8")
    print(f"SQL 已导出: {path}")


def main():
    ap = argparse.ArgumentParser(description="灌入 A 股公司基础信息到 Supabase")
    ap.add_argument("--dry-run", action="store_true", help="只打印统计与前 5 条，不写库")
    ap.add_argument("--emit-sql", metavar="PATH", help="另存为幂等 SQL 文件")
    ap.add_argument("--skip-em", action="store_true", help="跳过东财行业板块（网络受限时）")
    args = ap.parse_args()

    df = fetch_a_stock_info(skip_em=args.skip_em)
    rows = build_rows(df)
    n_ind = sum(1 for r in rows if r["sw_industry"])
    print(f"\n共 {len(rows)} 条 · 行业覆盖 {n_ind} 条（{n_ind * 100 // max(len(rows), 1)}%）")

    if args.emit_sql:
        emit_sql(rows, Path(args.emit_sql))

    if args.dry_run:
        for r in rows[:5]:
            print(r)
        print("(dry-run 未写库)")
        return

    client = get_client()
    total = upsert_companies(client, rows)
    print(f"\n完成：共写入 {total} 条")


if __name__ == "__main__":
    main()
