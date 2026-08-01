#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tavily 新闻风险线索 POC；线索不是正式风险案例。"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_FILE = ROOT / "config" / "risk_media_queries.yml"
MAX_QUERIES_PER_RUN = 12
MAX_RESULTS_PER_QUERY = 10
TRACKING_PARAMS = {"spm", "from", "source", "ref", "ref_src"}

DERIVATIVE_TERMS = (
    "商品期货", "外汇期货", "股指期货", "期货", "商品期权", "外汇期权",
    "场外期权", "期权", "外汇远期", "远期外汇", "远期结售汇", "远期",
    "利率掉期", "货币掉期", "掉期", "利率互换", "货币互换", "互换",
    "衍生金融工具", "衍生品", "套期保值", "套保",
)
RISK_TERMS = (
    "重大亏损", "重大损失", "亏损", "损失", "爆仓", "强制平仓", "强平",
    "保证金不足", "未经授权", "超授权", "投机", "违规", "处罚", "问询函",
    "监管问询", "内控缺陷", "追责", "整改", "流动性风险",
)


def bounded_limits(query_limit: int, max_results: int) -> tuple[int, int]:
    return (
        min(MAX_QUERIES_PER_RUN, max(1, query_limit)),
        min(MAX_RESULTS_PER_QUERY, max(1, max_results)),
    )


def build_search_payload(
    query: str,
    *,
    max_results: int,
    time_range: str,
) -> dict[str, Any]:
    return {
        "query": query,
        "topic": "news",
        "search_depth": "basic",
        "max_results": max_results,
        "time_range": time_range,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_usage": True,
    }


def search_tavily(
    api_key: str,
    query: str,
    *,
    max_results: int,
    time_range: str,
    session: Any = None,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("缺少环境变量 TAVILY_API_KEY")
    client = session or requests.Session()
    response = client.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=build_search_payload(
            query,
            max_results=max_results,
            time_range=time_range,
        ),
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Tavily 返回了非对象响应")
    return payload


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or not parts.netloc:
        raise ValueError("媒体线索 URL 必须是 HTTPS")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(("https", parts.netloc.lower(), parts.path, urlencode(query), ""))


def _unique_matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _lead_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return f"tavily:{digest}"


def prepare_leads(
    results: Iterable[dict[str, Any]],
    query_key: str,
) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for result in results:
        title = str(result.get("title") or "").strip()
        snippet = str(result.get("content") or "").strip()
        combined = f"{title}\n{snippet}"
        derivative = _unique_matches(combined, DERIVATIVE_TERMS)
        risk = _unique_matches(combined, RISK_TERMS)
        if not title or not derivative or not risk:
            continue
        try:
            url = normalize_url(str(result.get("url") or ""))
        except ValueError:
            continue
        leads.append({
            "lead_key": _lead_key(url),
            "provider": "TAVILY",
            "url": url,
            "source_domain": urlsplit(url).netloc,
            "title": title,
            "snippet": snippet[:1000] or None,
            "published_at": result.get("published_date"),
            "code": None,
            "company_name": None,
            "query_keys": [query_key],
            "matched_derivative_terms": derivative,
            "matched_risk_terms": risk,
            "provider_score": result.get("score"),
            "status": "new",
            "need_review": True,
            "official_corroborated": False,
            "raw_metadata": {},
        })
    return leads


def merge_leads(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["lead_key"]
        if key not in merged:
            order.append(key)
            merged[key] = dict(row)
            continue
        current = merged[key]
        query_keys = list(dict.fromkeys(current["query_keys"] + row["query_keys"]))
        derivative = list(dict.fromkeys(
            current["matched_derivative_terms"] + row["matched_derivative_terms"]
        ))
        risk = list(dict.fromkeys(
            current["matched_risk_terms"] + row["matched_risk_terms"]
        ))
        current_score = float(current.get("provider_score") or 0)
        new_score = float(row.get("provider_score") or 0)
        if new_score > current_score:
            merged[key] = dict(row)
            current = merged[key]
        current["query_keys"] = query_keys
        current["matched_derivative_terms"] = derivative
        current["matched_risk_terms"] = risk
    return [merged[key] for key in order]


def match_companies(
    rows: Iterable[dict[str, Any]],
    companies: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str]] = []
    for company in companies:
        code = str(company.get("code") or "").strip()
        for field in ("full_name", "name", "company_name"):
            name = str(company.get(field) or "").strip()
            if code and len(name) >= 4:
                candidates.append((name, code))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)

    out: list[dict[str, Any]] = []
    for row in rows:
        clean = dict(row)
        text = f"{clean.get('title') or ''}\n{clean.get('snippet') or ''}"
        code_match = re.search(r"(?<!\d)([0368]\d{5})(?!\d)", text)
        matched_name = None
        matched_code = code_match.group(1) if code_match else None
        if matched_code:
            for name, code in candidates:
                if code == matched_code:
                    matched_name = name
                    break
        if not matched_code:
            for name, code in candidates:
                if name in text:
                    matched_name, matched_code = name, code
                    break
        if matched_code:
            clean["code"] = matched_code
            clean["company_name"] = matched_name
            clean["status"] = "matched"
        out.append(clean)
    return out


def load_queries(path: Path = DEFAULT_QUERY_FILE) -> list[dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    queries = data.get("queries") or []
    if not isinstance(queries, list):
        raise ValueError("risk media queries must be a list")
    out: list[dict[str, str]] = []
    for item in queries:
        key = str(item.get("key") or "").strip()
        query = str(item.get("query") or "").strip()
        if key and query:
            out.append({"key": key, "query": query})
    if not out:
        raise ValueError("risk media query list is empty")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集 Tavily 衍生品风险新闻线索")
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--query-limit", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--time-range", choices=("day", "week", "month"), default="day")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from scripts.common import env, log, sb_select, sb_upsert, snapshot_csv
    except ModuleNotFoundError:
        from common import env, log, sb_select, sb_upsert, snapshot_csv

    query_limit, max_results = bounded_limits(args.query_limit, args.max_results)
    queries = load_queries(args.query_file)[:query_limit]
    api_key = env("TAVILY_API_KEY", required=True)
    rows: list[dict[str, Any]] = []
    credits_used = 0
    for index, item in enumerate(queries, start=1):
        log(f"Tavily news {index}/{len(queries)}: {item['key']}")
        response = search_tavily(
            api_key or "",
            item["query"],
            max_results=max_results,
            time_range=args.time_range,
        )
        credits_used += int((response.get("usage") or {}).get("credits") or 1)
        rows.extend(prepare_leads(response.get("results") or [], item["key"]))
        if credits_used > query_limit:
            raise RuntimeError("Tavily 单次搜索消耗超过免费预算假设，已停止后续查询")

    leads = merge_leads(rows)
    log(f"Tavily 使用 {credits_used} credits；双词门槛线索 {len(leads)} 条")
    snapshot_csv("risk_media_leads", leads)
    if not args.write:
        log("dry-run：未写入 Supabase")
        return

    companies = sb_select(
        "companies",
        {"select": "code,name,full_name"},
        paginate=True,
    )
    leads = match_companies(leads, companies)
    count = sb_upsert(
        "risk_media_leads",
        leads,
        on_conflict="lead_key",
    )
    log(f"已幂等写入 risk_media_leads：{count} 条")


if __name__ == "__main__":
    main()
