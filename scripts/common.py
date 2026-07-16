#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common.py —— 全项目公共工具
============================
职责：.env 加载 / Supabase PostgREST 封装 / 重试退避 / 运行快照。
所有脚本共享同一套写库行为：幂等 upsert、分页 select、指数退避。

设计约定（沿用 build_companies v4 标准）：
- 自动加载仓库根目录 .env（本地）；Actions 里直接读环境变量。
- 任何网络调用失败都指数退避重试，最终失败抛异常让上层决定。
- 运行时可在 output/ 落 CSV/JSON 快照备查（snapshot_*）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
CN_TZ = ZoneInfo("Asia/Shanghai")

load_dotenv(ROOT / ".env")  # 本地开发自动加载；CI 中无 .env 也不报错

RETRY_BACKOFF = [2, 8, 30, 90]  # 秒


def log(msg: str) -> None:
    ts = dt.datetime.now(CN_TZ).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr, flush=True)


def beijing_now() -> dt.datetime:
    return dt.datetime.now(CN_TZ)


def beijing_today() -> dt.date:
    return beijing_now().date()


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"缺少环境变量 {name}（本地填 .env，Actions 填 repo Secrets）")
    return val


# ----------------------------- Supabase PostgREST -----------------------------
def _sb_base() -> tuple[str, dict]:
    url = env("SUPABASE_URL", required=True).rstrip("/")
    key = env("SUPABASE_SERVICE_ROLE_KEY", required=True)
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    return f"{url}/rest/v1", headers


def sb_request(method: str, path: str, *, params: dict | None = None,
               json_body: Any = None, extra_headers: dict | None = None) -> requests.Response:
    """对 PostgREST 的请求，带指数退避。4xx（除 429）视为逻辑错误立即抛出。"""
    base, headers = _sb_base()
    if extra_headers:
        headers = {**headers, **extra_headers}
    last_err = None
    for i, backoff in enumerate([0] + RETRY_BACKOFF):
        if backoff:
            warn(f"Supabase 请求重试第 {i} 次，先休眠 {backoff}s ...")
            time.sleep(backoff)
        try:
            r = requests.request(method, f"{base}/{path.lstrip('/')}",
                                 params=params, json=json_body,
                                 headers=headers, timeout=60)
            if r.status_code in (200, 201, 204, 206):
                return r
            if 400 <= r.status_code < 500 and r.status_code != 429:
                raise RuntimeError(f"PostgREST {r.status_code}: {r.text[:400]}")
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_err = repr(e)
    raise RuntimeError(f"Supabase 请求最终失败: {method} {path} | {last_err}")


def sb_upsert(table: str, rows: list[dict], on_conflict: str,
              *, resolution: str = "merge-duplicates", chunk: int = 300) -> int:
    """幂等批量 upsert。
    resolution=merge-duplicates：冲突时用 payload 中出现的列覆盖（未出现的列不动）。
    resolution=ignore-duplicates：冲突时跳过（只插新行，用于审计补捞）。
    """
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        sb_request("POST", table,
                   params={"on_conflict": on_conflict},
                   json_body=batch,
                   extra_headers={"Prefer": f"resolution={resolution},return=minimal"})
        total += len(batch)
    return total


def sb_insert(table: str, rows: list[dict], *, chunk: int = 300) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), chunk):
        sb_request("POST", table, json_body=rows[i:i + chunk],
                   extra_headers={"Prefer": "return=minimal"})
        total += len(rows[i:i + chunk])
    return total


def sb_select(table: str, params: dict, *, paginate: bool = False,
              page_size: int = 1000) -> list[dict]:
    """select。paginate=True 时用 limit/offset 翻完全部结果。"""
    if not paginate:
        r = sb_request("GET", table, params=params)
        return r.json()
    out: list[dict] = []
    offset = 0
    while True:
        p = {**params, "limit": page_size, "offset": offset}
        rows = sb_request("GET", table, params=p).json()
        out.extend(rows)
        if len(rows) < page_size:
            return out
        offset += page_size


def sb_update(table: str, filters: dict, patch: dict) -> None:
    sb_request("PATCH", table, params=filters, json_body=patch,
               extra_headers={"Prefer": "return=minimal"})


def sb_delete(table: str, filters: dict) -> None:
    sb_request("DELETE", table, params=filters,
               extra_headers={"Prefer": "return=minimal"})


# ----------------------------- 运行快照 -----------------------------
def snapshot_csv(name: str, rows: list[dict]) -> Path | None:
    """把本次运行结果落 output/ 备查。rows 为空则不落盘。"""
    if not rows:
        return None
    OUTPUT_DIR.mkdir(exist_ok=True)
    ts = beijing_now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{name}_{ts}.csv"
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (list, dict)) else v)
                        for k, v in r.items()})
    log(f"快照已落盘: {path.relative_to(ROOT)}（{len(rows)} 行）")
    return path
