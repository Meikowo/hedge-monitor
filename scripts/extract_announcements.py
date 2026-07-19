#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_announcements.py —— 公告抽取管线（抽取层）
====================================================
流程：取 pending 公告 → 下载PDF → 关键词定位相关页(带页码标记)
      → MiniMax-M3 严格JSON抽取 → 枚举规范化 → 程序回验(防幻觉兜底)
      → 写 extractions + quota_items，公告状态流转。

状态机：pending → extracted(套保相关) / irrelevant(LLM判无关)
                / skipped(扫描件或无PDF) / failed(可重试)

用法：
  python scripts/extract_announcements.py --limit 40
  python scripts/extract_announcements.py --limit 300 --since 2026-01-01
  python scripts/extract_announcements.py --retry-failed --limit 50
  python scripts/extract_announcements.py --ids 1226058xxx --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fitz  # PyMuPDF

import cninfo
import prompt_extract as pe
from common import env, log, sb_delete, sb_insert, sb_select, sb_update, sb_upsert, snapshot_csv, warn

MAX_CHARS = 14000     # 送模型的正文上限（字符）
MAX_PAGES = 12        # 最多送多少页
PAGE_KEYWORDS = ["套期保值", "套保", "衍生品", "远期", "期货", "期权",
                 "掉期", "互换", "结售汇", "额度", "保证金", "合约价值", "名义本金"]

ROLE_SET = {"计划-董事会", "计划-股东大会", "可行性分析", "管理制度",
            "进展", "平仓或终止", "风险提示", "其他"}
VENUE_SET = {"境内", "境外", "境内外", "未披露"}
APPROVAL_SET = {"董事会", "股东大会", "董事会及股东大会", "未披露"}
SCOPE_SET = {"商品", "外汇", "利率", "其他"}
BASIS_SET = {"保证金占用", "业务总额", "名义本金", "合约价值", "其他", "未披露"}
BASIS_SYNONYM = [("保证金", "保证金占用"), ("业务总额", "业务总额"), ("累计", "业务总额"),
                 ("名义本金", "名义本金"), ("合约价值", "合约价值"), ("合约金额", "合约价值"),
                 ("投资金额", "其他")]
CURRENCY_MAP = {"人民币": "CNY", "元": "CNY", "美元": "USD", "港元": "HKD", "港币": "HKD",
                "欧元": "EUR", "日元": "JPY", "英镑": "GBP"}


# ----------------------------- PDF → 带页码正文 -----------------------------
def pdf_to_marked_text(content: bytes) -> tuple[str, int]:
    """提取PDF文本：第1页 + 含关键词的页，带【P页码】标记。返回(文本, 总页数)。"""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
        tf.write(content)
        tf.flush()
        doc = fitz.open(tf.name)
        pages = [(i + 1, p.get_text()) for i, p in enumerate(doc)]
        doc.close()
    picked = [(n, t) for n, t in pages
              if n == 1 or any(k in t for k in PAGE_KEYWORDS)]
    if len(picked) <= 1 and len(pages) > 1:   # 关键词定位失败：兜底取前4页
        picked = pages[:4]
    picked = picked[:MAX_PAGES]
    parts, total = [], 0
    for n, t in picked:
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t).strip()
        seg = f"【P{n}】\n{t}"
        if total + len(seg) > MAX_CHARS:
            seg = seg[: MAX_CHARS - total]
        parts.append(seg)
        total += len(seg)
        if total >= MAX_CHARS:
            break
    return "\n\n".join(parts), len(pages)


# ----------------------------- LLM 调用与 JSON 容错 -----------------------------
def extract_json_obj(raw: str) -> dict:
    """稳健提取JSON：剥离<think>块与Markdown围栏，再做括号配对扫描。"""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"</?think>", "", raw)
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"输出中无JSON对象。前300字: {raw[:300]}")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(raw)):
        c = raw[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(raw[start:i + 1])
    raise ValueError(f"JSON括号不配对。前300字: {raw[:300]}")


def call_llm(messages: list[dict]) -> dict:
    """MiniMax-M3（OpenAI兼容）。thinking 保持 adaptive，思考内容由解析层剥离。"""
    from openai import OpenAI
    client = OpenAI(api_key=env("LLM_API_KEY", required=True),
                    base_url=env("LLM_BASE_URL", "https://api.minimaxi.com/v1"))
    kwargs = dict(model=env("LLM_MODEL", "MiniMax-M3"), messages=messages,
                  temperature=float(env("LLM_TEMPERATURE", "1.0")),
                  max_tokens=int(env("LLM_MAX_TOKENS", "8000")))
    if env("LLM_THINKING", "on").lower() == "on":
        kwargs["extra_body"] = {"thinking": {"type": "adaptive"}}
    last = None
    for backoff in (0, 10, 40):
        if backoff:
            warn(f"LLM 调用重试，先休眠 {backoff}s")
            time.sleep(backoff)
        try:
            resp = client.chat.completions.create(**kwargs)
            return extract_json_obj(resp.choices[0].message.content or "")
        except Exception as e:
            last = e
    raise RuntimeError(f"LLM 调用最终失败: {repr(last)[:200]}")


# ----------------------------- 规范化与程序回验 -----------------------------
def _coerce(val, allowed: set, default: str):
    return val if val in allowed else (default if val else default)


def _norm_list(val, allowed: set | None = None) -> list[str]:
    if not isinstance(val, list):
        return []
    out = [str(x).strip() for x in val if x and str(x).strip()]
    if allowed:
        out = [x if x in allowed else "其他" for x in out]
        out = list(dict.fromkeys(out))
    return out


def _norm_amount(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.]", "", str(v))
    return float(s) if s else None


def _norm_basis(b) -> str:
    b = (b or "").strip()
    if b in BASIS_SET:
        return b
    for key, target in BASIS_SYNONYM:
        if key in b:
            return target
    return "其他" if b else "未披露"


def verify_amount(amount: float | None, raw: str | None) -> bool | None:
    """程序回验：从原文摘录里解析所有 数字×(万|亿) 候选，看是否能对上 amount。"""
    if amount is None:
        return None
    if not raw:
        return False
    cands = set()
    for m in re.finditer(r"([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(亿|万)?", raw):
        try:
            base = float(m.group(1).replace(",", "").replace("，", ""))
        except ValueError:
            continue
        mult = {"亿": 1e8, "万": 1e4}.get(m.group(2), 1.0)
        cands.add(round(base * mult, 2))
    return any(abs(c - amount) <= max(1.0, abs(amount) * 1e-6) for c in cands)


def verify_quote(quote: str | None, haystack: str) -> bool | None:
    if not quote:
        return None
    strip = lambda s: re.sub(r"[\s,，、。;；:：\"'“”]", "", s)
    return strip(quote)[:40] in strip(haystack)


def normalize_extraction(ext: dict, body: str) -> tuple[dict, list[dict]]:
    """把 LLM 输出规范化为 extractions 行 + quota_items 行。"""
    is_rel = bool(ext.get("is_hedge_related"))
    row = {
        "is_hedge_related": is_rel,
        "ann_role": _coerce(ext.get("ann_role"), ROLE_SET, "其他"),
        "scope": _norm_list(ext.get("scope"), SCOPE_SET),
        "instruments": _norm_list(ext.get("instruments")),
        "underlyings": _norm_list(ext.get("underlyings")),
        "venue": _coerce(ext.get("venue"), VENUE_SET, "未披露"),
        "venues_detail": _norm_list(ext.get("venues_detail")),
        "approval_level": _coerce(ext.get("approval_level"), APPROVAL_SET, "未披露"),
        "plan_label": (ext.get("plan_label") or None),
        "meeting": (ext.get("meeting") or None),
        "period_text": (ext.get("period_text") or None),
        "period_months": ext.get("period_months") if isinstance(ext.get("period_months"), int) else None,
        "is_revolving": ext.get("is_revolving") if isinstance(ext.get("is_revolving"), bool) else None,
        "use_own_funds": ext.get("use_own_funds") if isinstance(ext.get("use_own_funds"), bool) else None,
        "summary": (ext.get("summary") or "")[:200] or None,
        "confidence": float(ext["confidence"]) if isinstance(ext.get("confidence"), (int, float)) else None,
        "evidence": ext.get("evidence") or [],
        "raw": ext,
    }
    quotas = []
    for q in (ext.get("quotas") or []):
        if not isinstance(q, dict):
            continue
        amount = _norm_amount(q.get("amount"))
        raw_text = (q.get("raw") or "")[:120] or None
        quotas.append({
            "scope": q.get("scope") if q.get("scope") in (SCOPE_SET | {"综合"}) else "综合",
            "basis": _norm_basis(q.get("basis")),
            "amount": amount,
            "currency": CURRENCY_MAP.get(q.get("currency"), q.get("currency") or "未披露"),
            "raw_text": raw_text,
            "page": q.get("page") if isinstance(q.get("page"), int) else None,
            "amount_verified": verify_amount(amount, raw_text),
            "quote_verified": verify_quote(raw_text, body),
        })
    return row, quotas


# ----------------------------- 主流程 -----------------------------
def fetch_pending(limit: int, since: str | None, retry_failed: bool,
                  ids: list[str] | None) -> list[dict]:
    params = {"select": "ann_id,code,name,title,pdf_url,publish_time",
              "order": "publish_time.desc", "limit": str(limit)}
    if ids:
        params["ann_id"] = f"in.({','.join(ids)})"
    else:
        params["status"] = "in.(pending,failed)" if retry_failed else "eq.pending"
        if since:
            params["publish_time"] = f"gte.{since}"
    return sb_select("announcements", params)


def process_one(r: dict, dry_run: bool) -> str:
    aid = r["ann_id"]
    if not r.get("pdf_url"):
        if not dry_run:
            sb_update("announcements", {"ann_id": f"eq.{aid}"},
                      {"status": "skipped", "note": "无PDF直链"})
        return "skipped"
    content = cninfo.download_pdf(r["pdf_url"])
    if not content:
        if not dry_run:
            sb_update("announcements", {"ann_id": f"eq.{aid}"},
                      {"status": "failed", "note": "PDF下载失败"})
        return "failed"
    body, n_pages = pdf_to_marked_text(content)
    if len(body) < 80:
        if not dry_run:
            sb_update("announcements", {"ann_id": f"eq.{aid}"},
                      {"status": "skipped", "note": "正文过短，疑似扫描件"})
        return "skipped"

    ext = call_llm(pe.build_messages(r.get("title"), r.get("name"), r.get("code"), body))
    row, quotas = normalize_extraction(ext, body)
    row.update({"ann_id": aid, "model": env("LLM_MODEL", "MiniMax-M3"),
                "prompt_version": pe.PROMPT_VERSION,
                "text_chars": len(body), "pdf_pages": n_pages,
                "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat()})

    q_desc = "; ".join(f"{q['scope']}/{q['basis']} {q['amount'] or '—'} {q['currency']}"
                       f"{'' if q['amount_verified'] in (True, None) else ' ⚠未回验'}"
                       for q in quotas) or "—"
    log(f"    role={row['ann_role']} scope={row['scope']} venue={row['venue']} "
        f"conf={row['confidence']} | 额度: {q_desc}")

    if dry_run:
        print(json.dumps(row["raw"], ensure_ascii=False, indent=2)[:1500])
        return "dry"
    sb_upsert("extractions", [row], on_conflict="ann_id")
    sb_delete("quota_items", {"ann_id": f"eq.{aid}"})
    if quotas:
        sb_insert("quota_items", [{**q, "ann_id": aid} for q in quotas])
    status = "extracted" if row["is_hedge_related"] else "irrelevant"
    sb_update("announcements", {"ann_id": f"eq.{aid}"},
              {"status": status, "note": None if status == "extracted" else "LLM判定与套保无关"})
    return status


def main() -> None:
    ap = argparse.ArgumentParser(description="公告 LLM 抽取管线")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--since", help="只抽该日期后发布的 YYYY-MM-DD")
    ap.add_argument("--retry-failed", action="store_true", help="把 failed 一并重试")
    ap.add_argument("--max-consecutive-failures", type=int, default=0,
                    help="连续失败达到该数量时熔断；0 表示关闭")
    ap.add_argument("--ids", nargs="+", help="只抽指定 ann_id（调试用）")
    ap.add_argument("--dry-run", action="store_true", help="抽取但不写库")
    args = ap.parse_args()

    todo = fetch_pending(args.limit, args.since, args.retry_failed, args.ids)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"selected_count={len(todo)}\n")
    log(f"待抽取 {len(todo)} 条（limit={args.limit}）")
    stats: dict[str, int] = {}
    report = []
    consecutive_failures = 0
    circuit_tripped = False
    for i, r in enumerate(todo, 1):
        log(f"[{i}/{len(todo)}] {r.get('name')} {r.get('code')} | {(r.get('title') or '')[:44]}")
        try:
            outcome = process_one(r, args.dry_run)
        except Exception as e:
            outcome = "failed"
            warn(f"    抽取异常: {repr(e)[:180]}")
            if not args.dry_run:
                sb_update("announcements", {"ann_id": f"eq.{r['ann_id']}"},
                          {"status": "failed", "note": repr(e)[:180]})
        stats[outcome] = stats.get(outcome, 0) + 1
        report.append({"ann_id": r["ann_id"], "code": r.get("code"),
                       "title": r.get("title"), "outcome": outcome})
        consecutive_failures = consecutive_failures + 1 if outcome == "failed" else 0
        if (args.max_consecutive_failures > 0 and
                consecutive_failures >= args.max_consecutive_failures):
            circuit_tripped = True
            warn(f"连续失败 {consecutive_failures} 条，触发熔断；剩余公告保留 pending")
            break
        time.sleep(0.4)
    log(f"完成: {stats}")
    snapshot_csv("extract_run", report)
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"processed_count={len(report)}\n")
    if circuit_tripped:
        raise SystemExit(2)
    if stats.get("failed", 0) > max(3, len(todo) * 0.3):
        raise SystemExit(1)  # 失败率异常时让 Actions 标红提醒


if __name__ == "__main__":
    main()

