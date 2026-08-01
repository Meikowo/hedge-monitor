#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resumable historical Tavily search for private derivatives-risk media leads."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.fetch_risk_media_leads import (
        DEFAULT_QUERY_FILE,
        load_queries,
        match_companies,
        merge_leads,
        persist_leads,
        prepare_leads,
        search_tavily,
    )
except ModuleNotFoundError:
    from fetch_risk_media_leads import (
        DEFAULT_QUERY_FILE,
        load_queries,
        match_companies,
        merge_leads,
        persist_leads,
        prepare_leads,
        search_tavily,
    )


MAX_WINDOWS_PER_RUN = 12
MAX_RESULTS_PER_WINDOW = 10
MAX_ATTEMPTS = 3
STALE_AFTER = dt.timedelta(hours=3)


def bounded_backfill_limits(window_limit: int, max_results: int) -> tuple[int, int]:
    return (
        min(MAX_WINDOWS_PER_RUN, max(1, window_limit)),
        min(MAX_RESULTS_PER_WINDOW, max(1, max_results)),
    )


def validate_write_limits(write: bool, max_results: int) -> None:
    if write and max_results != MAX_RESULTS_PER_WINDOW:
        raise ValueError(
            "write mode requires --max-results 10 so production windows are not truncated"
        )


def make_window_key(query_key: str, start: str, end: str) -> str:
    return f"{query_key}|{start}|{end}"


def _window(
    query: dict[str, str],
    start: dt.date,
    end: dt.date,
    granularity: str,
    parent_window_key: str | None = None,
) -> dict[str, Any]:
    start_s, end_s = start.isoformat(), end.isoformat()
    return {
        "window_key": make_window_key(query["key"], start_s, end_s),
        "calendar_year": start.year,
        "query_key": query["key"],
        "query_text": query["query"],
        "window_start": start_s,
        "window_end": end_s,
        "granularity": granularity,
        "parent_window_key": parent_window_key,
        "status": "pending",
    }


def annual_windows(
    queries: Iterable[dict[str, str]], start_year: int, end_year: int
) -> list[dict[str, Any]]:
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    query_rows = list(queries)
    rows: list[dict[str, Any]] = []
    for year in range(end_year, start_year - 1, -1):
        for query in query_rows:
            rows.append(_window(
                query,
                dt.date(year, 1, 1),
                dt.date(year, 12, 31),
                "annual",
            ))
    return rows


def quarter_windows(parent: dict[str, Any]) -> list[dict[str, Any]]:
    year = int(parent["calendar_year"])
    query = {"key": parent["query_key"], "query": parent["query_text"]}
    ranges = (
        (dt.date(year, 1, 1), dt.date(year, 3, 31)),
        (dt.date(year, 4, 1), dt.date(year, 6, 30)),
        (dt.date(year, 7, 1), dt.date(year, 9, 30)),
        (dt.date(year, 10, 1), dt.date(year, 12, 31)),
    )
    return [
        _window(query, start, end, "quarter", parent["window_key"])
        for start, end in ranges
    ]


def _parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def select_windows(
    rows: Iterable[dict[str, Any]], *, now: dt.datetime, limit: int
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for row in rows:
        status = row.get("status")
        attempts = int(row.get("attempts") or 0)
        if status == "pending":
            eligible.append(row)
        elif status == "failed" and attempts < MAX_ATTEMPTS:
            eligible.append(row)
        elif status == "running" and attempts < MAX_ATTEMPTS:
            started_at = _parse_timestamp(row.get("started_at"))
            if started_at is None or now - started_at >= STALE_AFTER:
                eligible.append(row)
    if not eligible:
        return []
    newest_year = max(int(row["calendar_year"]) for row in eligible)
    same_year = [row for row in eligible if int(row["calendar_year"]) == newest_year]
    same_year.sort(key=lambda row: (
        row.get("window_start") or "",
        row.get("query_key") or "",
        row["window_key"],
    ))
    return same_year[: min(MAX_WINDOWS_PER_RUN, max(1, limit))]


def window_outcome(
    window: dict[str, Any], raw_result_count: int, max_results: int
) -> tuple[str, bool]:
    saturated = raw_result_count >= max_results
    if saturated and window.get("granularity") == "annual":
        return "split", True
    return "completed", saturated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historical risk media leads")
    parser.add_argument("--query-file", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--dry-year", type=int, default=2025)
    parser.add_argument("--window-limit", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def claim_windows(
    sb_request_func: Any,
    start_year: int,
    end_year: int,
    limit: int,
    now: dt.datetime,
) -> list[dict[str, Any]]:
    response = sb_request_func(
        "POST",
        "rpc/claim_risk_media_backfill_windows",
        json_body={
            "p_start_year": start_year,
            "p_end_year": end_year,
            "p_limit": limit,
            "p_stale_before": (now - STALE_AFTER).isoformat(),
        },
    )
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("backfill claim RPC returned a non-list response")
    return payload


def _process_dry_run(
    api_key: str,
    queries: list[dict[str, str]],
    dry_year: int,
    window_limit: int,
    max_results: int,
    log: Any,
) -> tuple[list[dict[str, Any]], int]:
    windows = annual_windows(queries[:window_limit], dry_year, dry_year)
    rows: list[dict[str, Any]] = []
    credits = 0
    for index, window in enumerate(windows, start=1):
        log(f"Historical dry-run {index}/{len(windows)}: {window['window_key']}")
        response = search_tavily(
            api_key,
            window["query_text"],
            max_results=max_results,
            start_date=window["window_start"],
            end_date=window["window_end"],
        )
        credits += int((response.get("usage") or {}).get("credits") or 1)
        rows.extend(prepare_leads(response.get("results") or [], window["query_key"]))
    return merge_leads(rows), credits


def main() -> None:
    args = parse_args()
    try:
        from scripts.common import env, log, sb_request, sb_select, sb_update, sb_upsert, snapshot_csv
    except ModuleNotFoundError:
        from common import env, log, sb_request, sb_select, sb_update, sb_upsert, snapshot_csv

    if args.start_year < 2000 or args.end_year > 2025:
        raise ValueError("historical backfill is intentionally bounded to 2000-2025")
    window_limit, max_results = bounded_backfill_limits(
        args.window_limit, args.max_results
    )
    validate_write_limits(args.write, max_results)
    queries = load_queries(args.query_file)
    api_key = env("TAVILY_API_KEY", required=True) or ""

    if not args.write:
        leads, credits = _process_dry_run(
            api_key, queries, args.dry_year, window_limit, max_results, log
        )
        snapshot_csv("risk_media_backfill_dry_run", leads)
        log(f"dry-run complete: {credits} credits, {len(leads)} leads; Supabase unchanged")
        return

    seeds = annual_windows(queries, args.start_year, args.end_year)
    sb_upsert(
        "risk_media_backfill_windows",
        seeds,
        on_conflict="window_key",
        resolution="ignore-duplicates",
    )
    now = dt.datetime.now(dt.timezone.utc)
    selected = claim_windows(
        sb_request,
        args.start_year,
        args.end_year,
        window_limit,
        now,
    )
    if not selected:
        terminal = sb_select(
            "risk_media_backfill_windows",
            {
                "select": "window_key",
                "status": "eq.failed",
                "attempts": f"gte.{MAX_ATTEMPTS}",
                "limit": 1,
            },
        )
        if terminal:
            raise RuntimeError("No eligible windows remain, but terminal failures need review")
        log("No eligible historical media windows remain")
        return

    companies = sb_select("companies", {"select": "code,name,full_name"}, paginate=True)
    run_leads: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, window in enumerate(selected, start=1):
        key_filter = {"window_key": f"eq.{window['window_key']}"}
        credits = 0
        try:
            log(f"Historical search {index}/{len(selected)}: {window['window_key']}")
            response = search_tavily(
                api_key,
                window["query_text"],
                max_results=max_results,
                start_date=window["window_start"],
                end_date=window["window_end"],
            )
            results = response.get("results") or []
            credits = int((response.get("usage") or {}).get("credits") or 1)
            leads = match_companies(
                merge_leads(prepare_leads(results, window["query_key"])),
                companies,
            )
            if leads:
                persist_leads(leads, sb_request)
                run_leads.extend(leads)
            status, saturated = window_outcome(window, len(results), max_results)
            if status == "split":
                sb_upsert(
                    "risk_media_backfill_windows",
                    quarter_windows(window),
                    on_conflict="window_key",
                    resolution="ignore-duplicates",
                )
            sb_update(
                "risk_media_backfill_windows",
                key_filter,
                {
                    "status": status,
                    "raw_result_count": len(results),
                    "lead_count": len(leads),
                    "credits_used": int(window.get("credits_used") or 0) + credits,
                    "saturated": saturated,
                    "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "last_error": None,
                },
            )
        except Exception as exc:
            failures.append(window["window_key"])
            sb_update(
                "risk_media_backfill_windows",
                key_filter,
                {
                    "status": "failed",
                    "credits_used": int(window.get("credits_used") or 0) + credits,
                    "last_error": str(exc)[:1000],
                    "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
            )
            log(f"Window failed: {window['window_key']} | {exc}")

    merged = merge_leads(run_leads)
    snapshot_csv("risk_media_backfill", merged)
    log(f"Historical batch complete: {len(selected)} windows, {len(merged)} unique leads")
    if failures:
        raise RuntimeError(
            f"{len(failures)} historical windows failed and were saved for retry: "
            + ", ".join(failures[:3])
        )


if __name__ == "__main__":
    main()
