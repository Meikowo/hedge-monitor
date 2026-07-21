#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cninfo.py —— 巨潮资讯接口封装（纯传输层）
==========================================
接口参数于 2026-06-12 实测可用、并已在 GitHub Actions 环境验证直连可达。
本模块只负责：查询、翻页、限速、风控识别、字段规整、PDF 下载。
词表应用、排除规则、入库均在上层脚本（fetch_announcements.py 等）完成。
"""
from __future__ import annotations

import datetime as dt
import random
import re
import sys
import time
from typing import Iterator

import requests

from common import CN_TZ, warn

QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"    # 标题层（POST）
FULLTEXT_URL = "https://www.cninfo.com.cn/new/fulltextSearch/full"   # 正文层（GET）
PDF_BASE = "https://static.cninfo.com.cn/"                           # PDF直链 = PDF_BASE + adjunctUrl
STOCK_LIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"  # 实际覆盖沪深北/B股

SLEEP_RANGE = (1.2, 2.5)       # 页间礼貌限速（秒）
MAX_PAGES = 300                # 单查询翻页保险上限
RETRY_BACKOFF = [5, 30, 120]   # 非JSON响应通常意味着被临时风控，退避要够长

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "X-Requested-With": "XMLHttpRequest",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

EM_TAG = re.compile(r"</?em>")  # isHLtitle=true 时标题带 <em> 高亮标签


def polite_sleep() -> None:
    time.sleep(random.uniform(*SLEEP_RANGE))


def _request_json(method: str, url: str, **kw) -> dict:
    last_err = None
    for i, backoff in enumerate([0] + RETRY_BACKOFF):
        if backoff:
            warn(f"巨潮请求重试第 {i} 次，先休眠 {backoff}s ...")
            time.sleep(backoff)
        try:
            r = SESSION.request(method, url, timeout=25, **kw)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue
            if "json" not in r.headers.get("content-type", ""):
                last_err = "非JSON响应，疑似被临时风控"
                continue
            return r.json()
        except requests.RequestException as e:
            last_err = repr(e)
    raise RuntimeError(f"巨潮请求最终失败: {url} | {last_err}")


def _ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    return dt.datetime.fromtimestamp(ms / 1000, tz=CN_TZ).isoformat()


def normalize(ann: dict, source: str) -> dict:
    """把巨潮返回的公告字段规整为库表字段。"""
    title = EM_TAG.sub("", str(ann.get("announcementTitle") or ""))
    adjunct = ann.get("adjunctUrl") or ""
    ptime = _ms_to_iso(ann.get("announcementTime"))
    return {
        "ann_id": str(ann.get("announcementId") or ann.get("id") or ""),
        "code": (ann.get("secCode") or "").strip() or None,
        "name": (ann.get("secName") or "").strip() or None,
        "title": title,
        "publish_time": ptime,
        "ann_date": ptime[:10] if ptime else None,
        "adjunct_url": adjunct or None,
        "pdf_url": (PDF_BASE + adjunct) if adjunct else None,
        "source": source,
    }


def iter_query(searchkey: str = "", category: str = "", se_date: str = "",
               stock: str = "") -> Iterator[dict]:
    """分页迭代 hisAnnouncement/query。翻页以 hasMore 为准（totalpages 语义不可靠）。
    column=szse 且 plate 留空时，沪深北一起返回。"""
    page = 1
    while page <= MAX_PAGES:
        payload = {
            "pageNum": page, "pageSize": 30,
            "column": "szse", "tabName": "fulltext",
            "plate": "", "stock": stock,
            "searchkey": searchkey, "secid": "",
            "category": category, "trade": "",
            "seDate": se_date,
            "sortName": "", "sortType": "", "isHLtitle": "true",
        }
        j = _request_json("POST", QUERY_URL, data=payload)
        anns = j.get("announcements") or []
        if not anns:
            return
        yield from anns
        if not j.get("hasMore"):
            return
        page += 1
        polite_sleep()


def iter_fulltext(keyword: str, sdate: str, edate: str) -> Iterator[dict]:
    """全文检索（正文层）。噪音大：重组报告书、审计报告都会命中，
    只用于月度补捞标题层漏检，入库后由 LLM 判 is_hedge_related 兜底。"""
    page = 1
    while page <= MAX_PAGES:
        j = _request_json("GET", FULLTEXT_URL, params={
            "searchkey": keyword, "sdate": sdate, "edate": edate,
            "isfulltext": "true", "sortName": "pubdate", "sortType": "desc",
            "pageNum": page,
        })
        anns = j.get("announcements") or []
        if not anns:
            return
        yield from anns
        if not j.get("hasMore"):
            return
        page += 1
        polite_sleep()


def download_pdf(pdf_url: str) -> bytes | None:
    """下载 PDF，校验文件头。失败返回 None（上层决定标记 failed/skipped）。"""
    for attempt, backoff in enumerate([0, 5, 20]):
        if backoff:
            time.sleep(backoff)
        try:
            r = SESSION.get(pdf_url, timeout=60)
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                return r.content
        except requests.RequestException as e:
            warn(f"PDF 下载异常({attempt}): {repr(e)[:80]}")
    return None


def stock_org_map() -> dict[str, str]:
    """证券代码 → 巨潮 orgId；定向查公告必须传 `code,orgId`。"""
    data = _request_json("GET", STOCK_LIST_URL)
    return {str(x.get("code") or "").zfill(6): str(x.get("orgId") or "")
            for x in (data.get("stockList") or []) if x.get("code") and x.get("orgId")}


# ----------------------------- 时间窗切分 -----------------------------
def quarter_windows(start_date: str, end_date: str) -> Iterator[tuple[str, str]]:
    """按自然季度切窗，避免单查询深翻页被截断。"""
    cur = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    while cur <= end:
        q = (cur.month - 1) // 3 + 1
        q_end = dt.date(cur.year, q * 3, 1)
        q_end = (dt.date(q_end.year + (q_end.month == 12), q_end.month % 12 + 1, 1)
                 - dt.timedelta(days=1))
        win_end = min(q_end, end)
        yield cur.isoformat(), win_end.isoformat()
        cur = win_end + dt.timedelta(days=1)
