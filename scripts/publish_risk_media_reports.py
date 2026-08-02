#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将私有 Tavily 线索筛选为可公开、可追溯的媒体风险记录。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

try:
    from scripts.fetch_risk_media_leads import normalize_url, relevant_contexts
except ModuleNotFoundError:
    from fetch_risk_media_leads import normalize_url, relevant_contexts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_FILE = ROOT / "config" / "risk_media_publishers.yml"


@dataclass(frozen=True)
class PublisherPolicy:
    publishers: dict[str, str]
    blocked_hosts: tuple[str, ...]
    blocked_path_terms: tuple[str, ...]
    official_hosts: tuple[str, ...]


@dataclass
class PublicationBatch:
    reports: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    lead_updates: list[dict[str, Any]]
    rejections: dict[str, str]


def _normalize_host(value: str | None) -> str:
    return str(value or "").strip().lower().rstrip(".")


def _matches_host(host: str, configured: str) -> bool:
    configured = _normalize_host(configured)
    return bool(configured) and (host == configured or host.endswith(f".{configured}"))


def _matches_any_host(host: str, configured_hosts: tuple[str, ...]) -> bool:
    return any(_matches_host(host, configured) for configured in configured_hosts)


def load_publisher_policy(path: Path = DEFAULT_POLICY_FILE) -> PublisherPolicy:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    publishers = {
        _normalize_host(host): str(name).strip()
        for host, name in (payload.get("publishers") or {}).items()
        if _normalize_host(host) and str(name).strip()
    }
    return PublisherPolicy(
        publishers=publishers,
        blocked_hosts=tuple(
            _normalize_host(host) for host in payload.get("blocked_hosts") or []
        ),
        blocked_path_terms=tuple(
            str(term).strip().lower()
            for term in payload.get("blocked_path_terms") or []
            if str(term).strip()
        ),
        official_hosts=tuple(
            _normalize_host(host) for host in payload.get("official_hosts") or []
        ),
    )


def publisher_for_domain(domain: str | None, policy: PublisherPolicy) -> str | None:
    host = _normalize_host(domain)
    matches = [
        (configured, name)
        for configured, name in policy.publishers.items()
        if _matches_host(host, configured)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def publication_rejection_reason(
    lead: dict[str, Any], policy: PublisherPolicy
) -> str | None:
    if not str(lead.get("code") or "").strip() or not str(
        lead.get("company_name") or ""
    ).strip():
        return "缺少上市公司代码或名称"
    if not lead.get("published_at"):
        return "缺少媒体发布日期"

    raw_url = str(lead.get("url") or "").strip()
    parts = urlsplit(raw_url)
    if parts.scheme.lower() != "https" or not parts.netloc:
        return "来源 URL 不是 HTTPS"

    host = _normalize_host(lead.get("source_domain") or parts.netloc)
    if not host:
        return "缺少具名媒体来源"
    if _matches_any_host(host, policy.official_hosts):
        return "来源属于官方证据渠道"
    if _matches_any_host(host, policy.blocked_hosts):
        return "来源属于论坛、股吧或社交平台"

    normalized_path = parts.path.lower()
    if any(term in normalized_path for term in policy.blocked_path_terms):
        return "来源路径属于自媒体或社区内容"
    if publisher_for_domain(host, policy) is None:
        return "来源不在具名媒体白名单"

    contexts = relevant_contexts(
        str(lead.get("title") or ""),
        str(lead.get("snippet") or ""),
    )
    if not contexts:
        return "未找到同一语境内已发生的衍生品风险"
    return None


def risk_family(terms: list[str] | tuple[str, ...] | None) -> str:
    joined = " ".join(str(term) for term in (terms or ()))
    families = (
        ("margin_liquidity", ("保证金不足", "爆仓", "强制平仓", "强平", "流动性风险")),
        ("unauthorized", ("未经授权", "超授权")),
        ("speculation", ("投机",)),
        ("regulatory", ("处罚", "监管问询", "问询函", "追责", "整改", "违规")),
        ("internal_control", ("内控缺陷", "审批缺陷", "授权缺陷")),
        ("disclosure", ("信息披露", "披露违规", "会计差错")),
        ("loss", ("重大亏损", "重大损失", "亏损", "损失")),
    )
    for family, needles in families:
        if any(needle in joined for needle in needles):
            return family
    return "other"


def derivative_families(
    terms: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    found: set[str] = set()
    for raw_term in terms or ():
        term = str(raw_term)
        if "期权" in term:
            found.add("option")
        if "掉期" in term or "互换" in term:
            found.add("swap")
        if "外汇" in term or "结售汇" in term or "远期" in term:
            found.add("fx")
        if "商品" in term or "期货" in term:
            found.add("commodity_futures")
        if "衍生" in term or "套保" in term or "套期保值" in term:
            found.add("generic_derivatives")
    return tuple(sorted(found))


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _report_derivative_families(report: dict[str, Any]) -> set[str]:
    explicit = report.get("derivative_families")
    if explicit:
        return {str(item) for item in explicit}
    return set(derivative_families(report.get("instruments") or ()))


def find_matching_report(
    lead: dict[str, Any], existing_reports: list[dict[str, Any]]
) -> str | None:
    lead_date = _as_date(lead.get("published_at"))
    lead_code = str(lead.get("code") or "").strip()
    lead_risk = risk_family(lead.get("matched_risk_terms"))
    lead_derivatives = set(derivative_families(lead.get("matched_derivative_terms")))
    if not lead_date or not lead_code or not lead_derivatives:
        return None

    for report in existing_reports:
        report_date = _as_date(report.get("event_date"))
        if str(report.get("code") or "").strip() != lead_code or not report_date:
            continue
        if abs((lead_date - report_date).days) > 14:
            continue
        if str(report.get("risk_type") or "other") != lead_risk:
            continue
        if not lead_derivatives.intersection(_report_derivative_families(report)):
            continue
        return str(report.get("media_key") or "") or None
    return None


def _media_key(lead_key: str) -> str:
    digest = hashlib.sha256(lead_key.encode("utf-8")).hexdigest()[:32]
    return f"media:{digest}"


def _source_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return f"source:{digest}"


def _attributed_excerpt(lead: dict[str, Any], publisher_name: str) -> str:
    contexts = relevant_contexts(
        str(lead.get("title") or ""), str(lead.get("snippet") or "")
    )
    context = contexts[0] if contexts else str(lead.get("title") or "").strip()
    return f"据{publisher_name}报道：{context}"[:500]


def prepare_public_rows(
    lead: dict[str, Any], publisher_name: str, media_key: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_url = normalize_url(str(lead.get("url") or ""))
    event_date = _as_date(lead.get("published_at"))
    if event_date is None:
        raise ValueError("媒体发布日期无效")
    excerpt = _attributed_excerpt(lead, publisher_name)
    instruments = list(dict.fromkeys(lead.get("matched_derivative_terms") or []))
    report = {
        "media_key": media_key,
        "code": str(lead.get("code") or "").strip(),
        "company_name": str(lead.get("company_name") or "").strip(),
        "event_date": event_date.isoformat(),
        "risk_type": risk_family(lead.get("matched_risk_terms")),
        "instruments": instruments,
        "underlyings": [],
        "summary": excerpt[:300],
        "verification_status": "media_unverified",
        "official_case_key": None,
        "publish_status": "published",
    }
    source = {
        "source_key": _source_key(normalized_url),
        "media_key": media_key,
        "publisher_name": publisher_name,
        "source_domain": _normalize_host(
            lead.get("source_domain") or urlsplit(normalized_url).netloc
        ),
        "title": str(lead.get("title") or "").strip(),
        "published_at": lead.get("published_at"),
        "url": normalized_url,
        "short_excerpt": excerpt,
        "matched_derivative_terms": list(
            dict.fromkeys(lead.get("matched_derivative_terms") or [])
        ),
        "matched_risk_terms": list(
            dict.fromkeys(lead.get("matched_risk_terms") or [])
        ),
    }
    return report, source


def publish_candidates(
    leads: list[dict[str, Any]],
    existing_reports: list[dict[str, Any]],
    policy: PublisherPolicy,
) -> PublicationBatch:
    reports: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    lead_updates: list[dict[str, Any]] = []
    rejections: dict[str, str] = {}
    working_reports = [dict(report) for report in existing_reports]
    known_source_keys: set[str] = set()

    for lead in leads:
        lead_key = str(lead.get("lead_key") or "")
        if lead.get("official_corroborated") or lead.get("status") == "corroborated":
            rejections[lead_key] = "已进入官方案例路径"
            continue
        if lead.get("status") == "dismissed":
            rejections[lead_key] = "线索已排除"
            continue

        reason = publication_rejection_reason(lead, policy)
        if reason:
            rejections[lead_key] = reason
            continue
        publisher_name = publisher_for_domain(lead.get("source_domain"), policy)
        if publisher_name is None:
            rejections[lead_key] = "缺少具名媒体来源"
            continue

        media_key = find_matching_report(lead, working_reports)
        is_new_report = media_key is None
        media_key = media_key or _media_key(lead_key)
        report, source = prepare_public_rows(lead, publisher_name, media_key)
        if is_new_report:
            reports.append(report)
            working_reports.append(report)
        if source["source_key"] not in known_source_keys:
            sources.append(source)
            known_source_keys.add(source["source_key"])

        raw_metadata = dict(lead.get("raw_metadata") or {})
        raw_metadata["public_media_key"] = media_key
        lead_updates.append({"lead_key": lead_key, "raw_metadata": raw_metadata})

    return PublicationBatch(reports, sources, lead_updates, rejections)


def persist_batch(batch: PublicationBatch, sb_upsert, sb_request) -> tuple[int, int]:
    report_count = sb_upsert(
        "risk_media_reports", batch.reports, "media_key"
    )
    source_count = sb_upsert(
        "risk_media_report_sources", batch.sources, "source_key"
    )
    for update in batch.lead_updates:
        sb_request(
            "PATCH",
            "risk_media_leads",
            params={"lead_key": f"eq.{update['lead_key']}"},
            json_body={"raw_metadata": update["raw_metadata"]},
            extra_headers={"Prefer": "return=minimal"},
        )
    return report_count, source_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish sanitized media risk reports from private Tavily leads"
    )
    parser.add_argument("--policy-file", type=Path, default=DEFAULT_POLICY_FILE)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def run_publication(
    *,
    write: bool,
    policy: PublisherPolicy,
    sb_select,
    sb_upsert,
    sb_request,
    snapshot_csv,
    log,
) -> PublicationBatch:
    leads = sb_select(
        "risk_media_leads",
        {
            "select": (
                "lead_key,url,source_domain,title,snippet,published_at,code,"
                "company_name,matched_derivative_terms,matched_risk_terms,status,"
                "need_review,official_corroborated,raw_metadata"
            ),
            "status": "in.(new,matched)",
            "official_corroborated": "eq.false",
            "order": "published_at.asc.nullslast,lead_key.asc",
        },
        paginate=True,
    )
    existing_reports = sb_select(
        "risk_media_reports",
        {
            "select": "media_key,code,event_date,risk_type,instruments,publish_status",
            "publish_status": "in.(published,corroborated)",
            "order": "event_date.asc,media_key.asc",
        },
        paginate=True,
    )
    batch = publish_candidates(leads, existing_reports, policy)

    report_by_key = {row["media_key"]: row for row in batch.reports}
    preview_rows = []
    for source in batch.sources:
        report = report_by_key.get(source["media_key"], {})
        preview_rows.append(
            {
                "media_key": source["media_key"],
                "code": report.get("code"),
                "company_name": report.get("company_name"),
                "event_date": report.get("event_date"),
                "risk_type": report.get("risk_type"),
                "publisher_name": source["publisher_name"],
                "title": source["title"],
                "url": source["url"],
                "short_excerpt": source["short_excerpt"],
            }
        )
    snapshot_csv("risk_media_public_preview", preview_rows)
    snapshot_csv(
        "risk_media_public_rejections",
        [
            {"lead_key": lead_key, "rejection_reason": reason}
            for lead_key, reason in sorted(batch.rejections.items())
        ],
    )
    log(
        "公开媒体筛选完成："
        f"候选线索 {len(leads)}，新报告 {len(batch.reports)}，"
        f"来源 {len(batch.sources)}，排除 {len(batch.rejections)}"
    )
    if write:
        report_count, source_count = persist_batch(batch, sb_upsert, sb_request)
        log(f"公开媒体投影已写入：报告 {report_count}，来源 {source_count}")
    else:
        log("当前为 dry-run，未写入公开投影表")
    return batch


def main() -> None:
    args = parse_args()
    try:
        from scripts.common import log, sb_request, sb_select, sb_upsert, snapshot_csv
    except ModuleNotFoundError:
        from common import log, sb_request, sb_select, sb_upsert, snapshot_csv

    policy = load_publisher_policy(args.policy_file)
    run_publication(
        write=args.write,
        policy=policy,
        sb_select=sb_select,
        sb_upsert=sb_upsert,
        sb_request=sb_request,
        snapshot_csv=snapshot_csv,
        log=log,
    )


if __name__ == "__main__":
    main()
