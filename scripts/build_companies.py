#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_companies.py -- 构建 / 刷新 companies 维表 (v3, 海外 Runner 友好版)
=========================================================================

v2 -> v3 改动背景
-----------------
v2 的基础列表用 ak.stock_info_a_code_name(), 该接口逐个请求深交所 / 上交所 /
北交所官网。交易所官网对海外 IP (GitHub Actions runner 在 Azure 美国机房)
经常在 TLS 握手阶段直接重置连接, 表现为:
    ConnectionResetError(104, 'Connection reset by peer')
本地 (国内网络) 无法复现, 只在 Actions 上暴露。

v3 数据源与写库策略
-------------------
1. 基础列表: 东方财富为主源 (海外可达, 与巨潮同属放行侧);
   交易所官网降级为兜底 (本地国内网络运行时仍可用)。
2. 行业口径: 东方财富行业板块 (细分, 约 86 个)。东财覆盖不到的
   (主要是部分北交所) 保留库中已有门类 —— 补空不覆盖, 绝不用空值回写。
3. 写库: Supabase PostgREST 批量 upsert (on_conflict=sec_code)。
   写之前自动探测 companies 表实际存在的列, 只写交集, 避免列名不符导致 400。
4. 全部网络调用带指数退避重试; 读库用深分页 (规避 PostgREST 1000 行上限)。

用法
----
    python scripts/build_companies.py               # 全量 (基础列表 + 东财行业)
    python scripts/build_companies.py --skip-em     # 跳过东财行业, 仅同步代码/名称
    python scripts/build_companies.py --dry-run     # 不写库, 输出 companies_preview.csv

环境变量
--------
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY  (或 SUPABASE_KEY)
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

import pandas as pd
import requests

try:
    import akshare as ak
except ImportError:  # pragma: no cover
    print("缺少依赖 akshare: pip install akshare", file=sys.stderr)
    raise

# GitHub Actions 上让日志实时刷出来, 方便盯进度
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


# --------------------------------------------------------------------------- #
# 通用重试
# --------------------------------------------------------------------------- #
def with_retry(fn, *args, _what: str = "", _tries: int = 4, _base: float = 4.0, **kwargs):
    """指数退避重试。海外访问国内数据源, 偶发 RST / 超时属常态, 必须兜住。"""
    last_err = None
    for attempt in range(1, _tries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # akshare 抛出的异常类型五花八门, 一律接住
            last_err = e
            if attempt == _tries:
                break
            wait = _base * (2 ** (attempt - 1)) + random.uniform(0.0, 2.0)
            print(f"  [retry {attempt}/{_tries}] {_what} 失败: "
                  f"{type(e).__name__}: {e} -> {wait:.0f}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"{_what} 重试 {_tries} 次仍失败: {last_err}") from last_err


# --------------------------------------------------------------------------- #
# 基础列表 (代码 + 名称)
# --------------------------------------------------------------------------- #
def _clean_base(df: pd.DataFrame, code_col: str, name_col: str) -> pd.DataFrame:
    out = df[[code_col, name_col]].copy()
    out.columns = ["sec_code", "name"]
    out["sec_code"] = out["sec_code"].astype(str).str.strip().str.zfill(6)
    out["name"] = out["name"].astype(str).str.strip()
    out = out[out["sec_code"].str.fullmatch(r"\d{6}")]
    out = out[out["name"] != ""]
    return out.drop_duplicates(subset="sec_code").reset_index(drop=True)


def fetch_base_list() -> pd.DataFrame:
    """全 A 股列表。东财为主 (Actions 可达), 交易所官网兜底 (仅国内网络可达)。"""
    try:
        print("[base] 东方财富 沪深京 A 股列表 ...")
        df = with_retry(ak.stock_zh_a_spot_em, _what="东财A股列表", _tries=3)
        base = _clean_base(df, "代码", "名称")
        # 个别 akshare 版本的合并快照不含北交所, 缺了就单独补一刀
        if not base["sec_code"].str.startswith(("43", "83", "87", "88", "92")).any():
            try:
                print("[base] 快照未含北交所, 追加 stock_bj_a_spot_em ...")
                bj = with_retry(ak.stock_bj_a_spot_em, _what="东财北交所列表", _tries=2)
                base = pd.concat(
                    [base, _clean_base(bj, "代码", "名称")], ignore_index=True
                ).drop_duplicates(subset="sec_code").reset_index(drop=True)
            except Exception as e:
                print(f"  [warn] 北交所补充失败 (不阻断): {e}")
        if len(base) < 4000:
            raise RuntimeError(f"东财仅返回 {len(base)} 条, 疑似不完整")
        print(f"[base] 东财 OK: {len(base)} 家")
        return base
    except Exception as e:
        print(f"[base] 东财失败: {e}")

    print("[base] 回退交易所官网接口 (注意: GitHub Actions 海外 IP 通常不可达) ...")
    df = with_retry(ak.stock_info_a_code_name, _what="交易所官网列表", _tries=2)
    base = _clean_base(df, "code", "name")
    print(f"[base] 官网 OK: {len(base)} 家")
    return base


def classify_board(code: str):
    """按代码前缀推断交易所 / 板块 (表里没有这两列时会被自动丢弃, 无副作用)。"""
    if code.startswith(("600", "601", "603", "605")):
        return "SH", "主板"
    if code.startswith(("688", "689")):
        return "SH", "科创板"
    if code.startswith(("000", "001", "002", "003")):
        return "SZ", "主板"
    if code.startswith(("300", "301", "302")):
        return "SZ", "创业板"
    if code.startswith(("43", "83", "87", "88", "92")):
        return "BJ", "北交所"
    return None, None


# --------------------------------------------------------------------------- #
# 东财行业 (细分口径)
# --------------------------------------------------------------------------- #
def fetch_em_industry_map() -> dict:
    boards = with_retry(ak.stock_board_industry_name_em,
                        _what="东财行业板块列表", _tries=3)
    names = boards["板块名称"].dropna().astype(str).tolist()
    print(f"[industry] 东财行业板块 {len(names)} 个, 逐个拉成分 ...")
    mapping: dict = {}
    failed: list = []
    for i, bname in enumerate(names, 1):
        try:
            cons = with_retry(ak.stock_board_industry_cons_em, symbol=bname,
                              _what=f"行业成分[{bname}]", _tries=3, _base=3.0)
            for c in cons["代码"].astype(str):
                mapping[c.strip().zfill(6)] = bname
        except Exception as e:
            failed.append(bname)
            print(f"  [warn] 行业 [{bname}] 拉取失败, 跳过: {e}")
        if i % 10 == 0 or i == len(names):
            print(f"  [industry] 进度 {i}/{len(names)}, 已映射 {len(mapping)} 家")
        time.sleep(0.6 + random.uniform(0.0, 0.6))  # 温和限速, 别惹东财风控
    if failed:
        print(f"[industry] {len(failed)} 个板块失败: {', '.join(failed[:8])} ...")
    if len(mapping) < 4000:
        raise RuntimeError(
            f"东财行业映射仅覆盖 {len(mapping)} 家, 明显异常; "
            "为避免写入半套口径, 本次中止 (直接重跑即可, 不会破坏现有数据)")
    return mapping


# --------------------------------------------------------------------------- #
# Supabase
# --------------------------------------------------------------------------- #
def sb_env():
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_KEY") or "")
    if not url or not key:
        raise SystemExit("缺少环境变量 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    return url, key


def sb_headers(key: str) -> dict:
    return {"apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def sb_table_columns(url: str, key: str, table: str = "companies"):
    """取 1 行推断表列。表为空时返回 None, 调用方退回默认三列。"""
    r = requests.get(f"{url}/rest/v1/{table}", headers=sb_headers(key),
                     params={"select": "*", "limit": 1}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return set(rows[0].keys()) if rows else None


def sb_fetch_existing(url: str, key: str) -> dict:
    """深分页拉全量 sec_code -> industry (规避 PostgREST 单次 1000 行上限)。"""
    out: dict = {}
    offset, page = 0, 1000
    while True:
        r = requests.get(f"{url}/rest/v1/companies", headers=sb_headers(key),
                         params={"select": "sec_code,industry",
                                 "order": "sec_code.asc",
                                 "limit": page, "offset": offset},
                         timeout=60)
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            out[str(row["sec_code"])] = row.get("industry")
        if len(rows) < page:
            break
        offset += page
    return out


def sb_upsert(url: str, key: str, records: list, batch: int = 500) -> None:
    hdrs = dict(sb_headers(key))
    hdrs["Prefer"] = "resolution=merge-duplicates,return=minimal"
    total = len(records)
    for i in range(0, total, batch):
        chunk = records[i:i + batch]

        def _post():
            r = requests.post(f"{url}/rest/v1/companies?on_conflict=sec_code",
                              headers=hdrs, json=chunk, timeout=120)
            if r.status_code >= 300:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

        with_retry(_post, _what=f"upsert 第 {i}-{i + len(chunk)} 行",
                   _tries=3, _base=5.0)
        print(f"[upsert] {min(i + batch, total)}/{total}")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="构建 / 刷新 companies 维表 (v3)")
    ap.add_argument("--skip-em", action="store_true",
                    help="跳过东财行业, 仅同步代码 / 名称")
    ap.add_argument("--dry-run", action="store_true",
                    help="不写库, 输出 companies_preview.csv")
    args = ap.parse_args()

    base = fetch_base_list()

    em_map: dict = {}
    if not args.skip_em:
        em_map = fetch_em_industry_map()

    if args.dry_run:
        url = key = None
        cols = None
        existing: dict = {}
    else:
        url, key = sb_env()
        cols = sb_table_columns(url, key)
        existing = sb_fetch_existing(url, key)
        print(f"[db] companies 现有 {len(existing)} 行; "
              f"表列: {sorted(cols) if cols else '空表, 使用默认三列'}")

    records: list = []
    n_new = n_upgraded = n_kept = n_null = 0
    for _, row in base.iterrows():
        code, name = row["sec_code"], row["name"]
        old_ind = existing.get(code)
        em_ind = em_map.get(code)
        if em_ind:
            industry = em_ind
            if old_ind != em_ind:
                n_upgraded += 1
        else:
            industry = old_ind  # 东财没有 -> 保留库中原值, 绝不用空覆盖
            if old_ind:
                n_kept += 1
            else:
                n_null += 1
        if code not in existing:
            n_new += 1
        exch, board = classify_board(code)
        rec = {"sec_code": code, "name": name, "industry": industry,
               "exchange": exch, "board": board}
        if cols is not None:
            rec = {k: v for k, v in rec.items() if k in cols}
        elif not args.dry_run:
            rec = {"sec_code": code, "name": name, "industry": industry}
        records.append(rec)

    print(f"[stats] 列表 {len(records)} 家 | 新增 {n_new} | "
          f"行业升级为东财口径 {n_upgraded} | 保留原口径 {n_kept} | 仍无行业 {n_null}")

    if args.dry_run:
        out = "companies_preview.csv"
        pd.DataFrame(records).to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[dry-run] 已写 {out}, 未触库")
        return

    sb_upsert(url, key, records)
    print("[done] companies 维表已更新")


if __name__ == "__main__":
    main()
