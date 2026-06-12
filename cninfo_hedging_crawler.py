#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
巨潮资讯网 · A股套期保值公告 + 年报 采集脚本(骨架)
====================================================
接口于 2026-06-12 实测可用。依赖: pip install requests

用法示例:
  python cninfo_hedging_crawler.py daily                       # 抓近3天套保公告并下载PDF
  python cninfo_hedging_crawler.py daily --days 7 --no-pdf     # 只抓元数据不下PDF
  python cninfo_hedging_crawler.py backfill --start 2021-07 --end 2026-06
  python cninfo_hedging_crawler.py annual --year 2025          # 抓"2025年年度报告"(2026年披露)
  python cninfo_hedging_crawler.py fulltext --days 7           # 第二层筛网:正文含关键词的公告清单

输出:
  data/announcements.jsonl    套保公告元数据(按 announcementId 增量去重)
  data/annual_reports.jsonl   年报元数据
  data/fulltext_hits.jsonl    正文命中的公告清单(噪音较大,供二次筛选)
  data/pdfs/<announcementId>.pdf

接入生产时:把 save_jsonl() 换成 PostgreSQL upsert(主键 announcement_id)即可。
"""
import argparse
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ----------------------------- 常量与配置 -----------------------------
QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"   # 公告查询(POST, 搜标题)
FULLTEXT_URL = "https://www.cninfo.com.cn/new/fulltextSearch/full"  # 全文检索(GET, 可搜正文)
PDF_BASE = "https://static.cninfo.com.cn/"                          # PDF直链 = PDF_BASE + adjunctUrl
STOCKLIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"  # 代码->orgId 全量映射

CN_TZ = ZoneInfo("Asia/Shanghai")

# 标题层关键词:逐个查询后按 announcementId 去重(关键词间命中有重叠,无妨)
KEYWORDS = ["套期保值", "套保", "远期结售汇", "外汇衍生品", "衍生品交易"]

# 标题排除规则:股权激励类"期权"、已取消公告等
EXCLUDE_TITLE_PAT = re.compile(r"期权激励|股票期权|限制性股票|已取消")

# 期货公司自身的公告会大量命中关键词,按证券代码排除(自行维护)
# 002961瑞达期货 603093南华期货 600927永安期货 001236弘业期货
EXCLUDE_SEC_CODES = {"002961", "603093", "600927", "001236"}

SLEEP_RANGE = (1.2, 2.5)      # 每次请求之间的随机休眠(秒),请保持礼貌
MAX_PAGES = 300               # 单查询翻页保险上限
RETRY_BACKOFF = [5, 30, 120]  # 失败重试退避(秒);非JSON响应通常意味着被临时风控

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "X-Requested-With": "XMLHttpRequest",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

EM_TAG = re.compile(r"</?em>")  # isHLtitle=true 时标题里带 <em> 高亮标签,需清洗


# ----------------------------- 基础工具 -----------------------------
def polite_sleep():
    time.sleep(random.uniform(*SLEEP_RANGE))


def beijing_today() -> dt.date:
    return dt.datetime.now(CN_TZ).date()


def ms_to_beijing_iso(ms) -> str:
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, tz=CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def request_json(method: str, url: str, **kw):
    """带重试与风控识别的请求。返回 dict;多次失败抛异常(上层应告警)。"""
    last_err = None
    for i, backoff in enumerate([0] + RETRY_BACKOFF):
        if backoff:
            print(f"  [retry] 第{i}次重试,先休眠 {backoff}s ...", file=sys.stderr)
            time.sleep(backoff)
        try:
            r = SESSION.request(method, url, timeout=25, **kw)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue
            ctype = r.headers.get("content-type", "")
            if "json" not in ctype:
                # 返回了HTML/验证页 => 大概率被临时限流
                last_err = f"非JSON响应(content-type={ctype}),疑似被风控"
                continue
            return r.json()
        except Exception as e:  # 网络抖动等
            last_err = repr(e)
    raise RuntimeError(f"请求失败: {url} | {last_err}")


def save_jsonl(path: Path, records: list, key: str = "announcement_id") -> int:
    """按主键增量追加,返回新增条数。生产环境替换为 PostgreSQL upsert。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get(key))
                except json.JSONDecodeError:
                    pass
    new = [r for r in records if r.get(key) not in seen]
    with path.open("a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new)


# ----------------------------- 公告查询(标题层) -----------------------------
def iter_query(searchkey: str = "", category: str = "", se_date: str = ""):
    """分页迭代 hisAnnouncement/query。翻页以 hasMore 为准(totalpages 字段语义不可靠)。"""
    page = 1
    while page <= MAX_PAGES:
        payload = {
            "pageNum": page, "pageSize": 30,
            "column": "szse",          # 留空 plate 时沪深北一起返回
            "tabName": "fulltext",
            "plate": "", "stock": "",  # 按单家公司查询时 stock="000001,gssz0000001"(orgId见STOCKLIST_URL)
            "searchkey": searchkey, "secid": "",
            "category": category, "trade": "",
            "seDate": se_date,
            "sortName": "", "sortType": "", "isHLtitle": "true",
        }
        j = request_json("POST", QUERY_URL, data=payload)
        anns = j.get("announcements") or []
        if not anns:
            return
        yield from anns
        if not j.get("hasMore"):
            return
        page += 1
        polite_sleep()


def normalize(ann: dict, source: str) -> dict:
    title = EM_TAG.sub("", ann.get("announcementTitle") or "")
    adjunct = ann.get("adjunctUrl") or ""
    return {
        "announcement_id": str(ann.get("announcementId")),
        "sec_code": ann.get("secCode"),
        "sec_name": (ann.get("secName") or "").strip(),
        "title": title,
        "publish_time": ms_to_beijing_iso(ann.get("announcementTime")),
        "adjunct_url": adjunct,
        "pdf_url": PDF_BASE + adjunct if adjunct else "",
        "source": source,   # 命中来源:哪个关键词 / annual / fulltext
    }


def fetch_hedging(sdate: str, edate: str, keywords=None) -> list:
    """标题层:逐关键词查询 -> 去重 -> 排除规则。"""
    keywords = keywords or KEYWORDS
    bag = {}
    for kw in keywords:
        print(f"[标题层] 关键词「{kw}」 {sdate}~{edate}")
        for ann in iter_query(searchkey=kw, se_date=f"{sdate}~{edate}"):
            rec = normalize(ann, source=kw)
            if rec["announcement_id"] in bag:
                continue
            if rec["sec_code"] in EXCLUDE_SEC_CODES:
                continue
            if EXCLUDE_TITLE_PAT.search(rec["title"]):
                continue
            bag[rec["announcement_id"]] = rec
        polite_sleep()
    return list(bag.values())


# ----------------------------- 全文检索(正文层,第二层筛网) -----------------------------
def fetch_fulltext(sdate: str, edate: str, keyword: str = "套期保值") -> list:
    """正文含关键词的公告清单。噪音大(重组报告书、审计报告都会命中),
    建议只用来补捞标题层漏掉的董事会决议类公告,入库前再做正文/LLM二次判别。"""
    page, out = 1, []
    while page <= MAX_PAGES:
        j = request_json("GET", FULLTEXT_URL, params={
            "searchkey": keyword, "sdate": sdate, "edate": edate,
            "isfulltext": "true", "sortName": "pubdate", "sortType": "desc",
            "pageNum": page,
        })
        anns = j.get("announcements") or []
        if not anns:
            break
        for a in anns:
            out.append({
                "announcement_id": str(a.get("announcementId") or a.get("id") or ""),
                "sec_code": a.get("secCode"),
                "sec_name": (a.get("secName") or "").strip(),
                "title": EM_TAG.sub("", str(a.get("announcementTitle") or "")),
                "publish_time": ms_to_beijing_iso(a.get("announcementTime")),
                "adjunct_url": a.get("adjunctUrl") or "",
                "pdf_url": PDF_BASE + (a.get("adjunctUrl") or ""),
                "source": f"fulltext:{keyword}",
            })
        if not j.get("hasMore"):
            break
        page += 1
        polite_sleep()
    return out


# ----------------------------- 年报抓取 -----------------------------
def fetch_annual_reports(report_year: int) -> list:
    """抓"{report_year}年年度报告"。披露窗口为次年1月~4月底,查询窗口放宽到6月底兜住补披露。
    category_ndbg_szsh 会同时返回正文/摘要/英文版/更正版,需按标题过滤。"""
    se = f"{report_year + 1}-01-01~{report_year + 1}-06-30"
    print(f"[年报] {report_year}年报, 窗口 {se}")
    bag = {}
    for ann in iter_query(category="category_ndbg_szsh", se_date=se):
        rec = normalize(ann, source="annual")
        t = rec["title"]
        if "年度报告" not in t or "半年度" in t:
            continue
        if re.search(r"摘要|英文|已取消", t):
            continue
        # 可选的严格过滤:标题须含目标年份(防止窗口内补披露的往年年报混入)
        if str(report_year) not in t:
            continue
        rec["is_revised"] = bool(re.search(r"更正后|更新后|修订", t))
        bag[rec["announcement_id"]] = rec
    return list(bag.values())


# ----------------------------- PDF 下载 -----------------------------
def download_pdf(rec: dict, dest_dir: Path) -> bool:
    """幂等下载:文件已存在且非空则跳过;校验 %PDF 文件头。"""
    if not rec.get("pdf_url"):
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{rec['announcement_id']}.pdf"
    if path.exists() and path.stat().st_size > 1024:
        return False
    r = SESSION.get(rec["pdf_url"], timeout=60, stream=True)
    r.raise_for_status()
    buf = b""
    with path.open("wb") as f:
        for chunk in r.iter_content(65536):
            if not buf:
                buf = chunk[:5]
            f.write(chunk)
    if not buf.startswith(b"%PDF"):
        path.unlink(missing_ok=True)
        print(f"  [warn] {rec['announcement_id']} 非PDF内容,已丢弃", file=sys.stderr)
        return False
    polite_sleep()
    return True


# ----------------------------- 历史回填 -----------------------------
def month_windows(start_ym: str, end_ym: str):
    """按自然月切窗,避免单查询深翻页。"""
    y, m = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))
    while (y, m) <= (ey, em):
        first = dt.date(y, m, 1)
        last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        yield first.isoformat(), last.isoformat()
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


# ----------------------------- 命令入口 -----------------------------
def main():
    ap = argparse.ArgumentParser(description="巨潮套保公告/年报采集")
    ap.add_argument("cmd", choices=["daily", "backfill", "annual", "fulltext"])
    ap.add_argument("--days", type=int, default=3, help="daily/fulltext: 抓最近N天")
    ap.add_argument("--start", help="backfill: 起始月 YYYY-MM")
    ap.add_argument("--end", help="backfill: 结束月 YYYY-MM")
    ap.add_argument("--year", type=int, help="annual: 年报年份(如2025=2026年披露)")
    ap.add_argument("--keywords", nargs="+", help="覆盖默认关键词列表")
    ap.add_argument("--no-pdf", action="store_true", help="只存元数据,不下载PDF")
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()

    out = Path(args.outdir)
    pdf_dir = out / "pdfs"
    today = beijing_today()

    if args.cmd == "daily":
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        recs = fetch_hedging(sdate, today.isoformat(), keywords=args.keywords)
        n = save_jsonl(out / "announcements.jsonl", recs)
        print(f"命中 {len(recs)} 条,新增入库 {n} 条")
        if not args.no_pdf:
            got = sum(download_pdf(r, pdf_dir) for r in recs)
            print(f"新下载 PDF {got} 份 -> {pdf_dir}")

    elif args.cmd == "backfill":
        assert args.start and args.end, "需要 --start YYYY-MM --end YYYY-MM"
        total = 0
        for sdate, edate in month_windows(args.start, args.end):
            recs = fetch_hedging(sdate, edate, keywords=args.keywords)
            n = save_jsonl(out / "announcements.jsonl", recs)
            total += n
            print(f"  {sdate[:7]}: 命中 {len(recs)}, 新增 {n}(累计新增 {total})")
            if not args.no_pdf:
                for r in recs:
                    download_pdf(r, pdf_dir)
        print(f"回填完成,共新增 {total} 条")

    elif args.cmd == "annual":
        assert args.year, "需要 --year,如 --year 2025"
        recs = fetch_annual_reports(args.year)
        n = save_jsonl(out / "annual_reports.jsonl", recs)
        print(f"{args.year}年报命中 {len(recs)} 份(去重后),新增 {n} 份")
        if not args.no_pdf:
            print("提示: 全市场年报体量大(约5000+份/年,单份2~10MB),建议先用 fulltext 预筛后按需下载")
            for r in recs:
                download_pdf(r, pdf_dir)

    elif args.cmd == "fulltext":
        sdate = (today - dt.timedelta(days=args.days - 1)).isoformat()
        recs = fetch_fulltext(sdate, today.isoformat())
        n = save_jsonl(out / "fulltext_hits.jsonl", recs)
        print(f"正文命中 {len(recs)} 条,新增 {n} 条(注意:此清单噪音大,需二次判别)")


if __name__ == "__main__":
    main()
