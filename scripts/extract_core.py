#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套保公告 LLM 结构化抽取核心模块
================================
职责: PDF -> 文本 -> 提示词 -> DeepSeek -> JSON -> 规整后的 hedge_events 字段
被 extract_pipeline.py 调用,也可单独 `python extract_core.py <pdf>` 测试一份。

DeepSeek 兼容 OpenAI SDK,故用 openai 库 + base_url 指向 DeepSeek。
环境变量:
  DEEPSEEK_API_KEY   必填
  DEEPSEEK_MODEL     默认 deepseek-chat
  DEEPSEEK_BASE_URL  默认 https://api.deepseek.com
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

# 喂给 LLM 的正文长度上限(字符)。实测套保公告关键字段都在前 ~1500 字,
# 给 6000 足够覆盖长公告的"交易情况概述"全章,又把 token 控制在很低水平。
MAX_CHARS = 6000

SYSTEM_PROMPT = """你是A股上市公司公告信息抽取助手。你只输出JSON,不输出任何解释、前言或Markdown代码块标记。
你的任务是从"套期保值/衍生品交易"类公告正文中抽取结构化字段。严格遵守:
- 只抽取公告中明确写出的信息,绝不猜测或脑补。原文没有的字段填 null。
- 不要把"可行性分析报告""管理制度"类文件误当成开展业务的公告。
- 金额要换算成数字(去掉千分位逗号),并单独给出币种和原文。"""

# 用 function-call 风格的 JSON Schema 描述,放进 user prompt 里约束输出
EXTRACTION_INSTRUCTION = """请从下面的公告正文抽取字段,输出符合以下结构的JSON对象:

{
  "is_hedging_announcement": true/false,   // 是否为"开展套保/衍生品业务"的实质公告(制度、可行性报告、进展、平仓填false)
  "hedge_type": "商品套期保值" | "外汇套期保值" | "利率套期保值" | "其他衍生品" | null,
  "risk_type": ["商品价格风险" | "汇率风险" | "利率风险" ...],  // 数组,可多个
  "instrument_type": ["期货","期权","远期结售汇","外汇掉期","互换" ...],  // 用到的金融工具,数组
  "underlying_asset": ["生猪","玉米","美元" ...],  // 具体标的/品种/币种,数组;没有明确列举则 []
  "trade_venue": "境内" | "境外" | "境内外" | null,  // LME/CME/芝商所等属境外
  "approval_level": "董事会" | "股东大会" | "董事会及股东大会" | null,
  "authorization_period": "原文表述,如'自董事会审议通过之日起12个月内'" | null,
  "contract_value_limit": 数字 | null,    // 额度上限,换算成元的数字。外汇看"业务总额",商品看"保证金最高占用额"
  "contract_value_currency": "人民币" | "美元" | null,
  "contract_value_basis": "保证金最高占用额" | "业务总额" | "合约价值" | null,  // 额度口径,很重要
  "contract_value_raw_text": "原文金额表述,如'保证金最高占用额不超过人民币1,000万元'" | null,
  "is_revolving": true/false/null,         // 额度是否可循环使用
  "use_own_funds": true/false/null,        // 是否使用自有资金(不含募集资金)
  "evidence": [                            // 每个关键字段的原文出处,供人工复核
    {"field": "contract_value_limit", "quote": "原文摘录(不超过30字)"}
  ],
  "confidence": 0.0~1.0                     // 你对本次抽取整体准确性的自评
}

注意单位换算: "1,000万元" = 10000000; "7,000万美元" = 70000000; "1亿元" = 100000000。

公告标题: {title}
公告正文:
\"\"\"
{body}
\"\"\""""


def extract_pdf_text(pdf_path: str | Path, max_chars: int = MAX_CHARS) -> str:
    """提取PDF文本。返回前 max_chars 字符。空文本(扫描件)返回空串,上层应跳过或OCR。"""
    doc = fitz.open(pdf_path)
    parts, total = [], 0
    for page in doc:
        t = page.get_text()
        parts.append(t)
        total += len(t)
        if total >= max_chars:
            break
    doc.close()
    text = "\n".join(parts).strip()
    # 压缩多余空白,省token
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]


def build_messages(title: str, body: str) -> list[dict]:
    user = EXTRACTION_INSTRUCTION.replace("{title}", title or "(无标题)").replace("{body}", body)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_json_obj(raw: str) -> dict:
    """从模型输出里稳健地提取 JSON 对象,兼容三种情况:
    1) thinking 模型把思考过程包在 <think>...</think> 里,后面才跟 JSON
    2) 模型用 ```json ... ``` 围栏包裹
    3) 模型在 JSON 前后多说了几句话(如"好的,结果如下:")
    策略: 先去掉 <think> 块和围栏,再用括号配对扫描出最外层 {...}。"""
    # 1) 去掉 thinking 标签块(M3/M2.x 开着 thinking 时会出现)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"</?think>", "", raw)  # 去掉残留的单边标签
    # 2) 去掉 markdown 围栏
    raw = re.sub(r"```(?:json)?", "", raw)
    raw = raw.strip()
    # 3) 直接能解析就直接返回
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 4) 括号配对扫描: 找到第一个 { 到与之匹配的 } 之间的内容
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"模型输出中找不到 JSON 对象。原始输出前300字: {raw[:300]}")
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
    raise ValueError(f"JSON 括号不配对。原始输出前300字: {raw[:300]}")


def call_llm(messages: list[dict]) -> dict:
    """调用大模型抽取,返回解析后的 dict。厂商无关设计,通过环境变量切换。

    默认走 MiniMax(你的年费套餐)。换任意 OpenAI 兼容厂商只需改这三个环境变量:
      LLM_API_KEY    必填,你的 API key
      LLM_BASE_URL   默认 https://api.minimaxi.com/v1 (MiniMax 国内站,注意是 minimaxi 带 i)
      LLM_MODEL      默认 MiniMax-M3

    设计要点:
    - 不使用 response_format(JSON模式): M3 等模型不一定支持,改为靠强力的 extract_json_obj 容错。
    - thinking 默认开启: 通过 extra_body 显式 adaptive,让模型先思考再输出,抽取更准;
      思考内容由 extract_json_obj 自动剥离,不影响结果。
    - 兼容旧变量名: 若只设了 DEEPSEEK_* 也能用。
    """
    from openai import OpenAI

    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
                or "https://api.minimaxi.com/v1")
    model = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "MiniMax-M3"
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY(或 DEEPSEEK_API_KEY)")

    client = OpenAI(api_key=api_key, base_url=base_url)

    # thinking 开启时,模型输出更长,max_tokens 给足,避免 JSON 被截断
    kwargs = dict(
        model=model,
        messages=messages,
        temperature=float(os.getenv("LLM_TEMPERATURE", "1.0")),  # M3 推荐 1.0
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4000")),
    )
    # MiniMax-M3 显式保持 thinking 开启(adaptive)。对不认识此参数的厂商无害(放在 extra_body)。
    if os.getenv("LLM_THINKING", "on").lower() == "on":
        kwargs["extra_body"] = {"thinking": {"type": "adaptive"}}

    resp = client.chat.completions.create(**kwargs)
    raw = resp.choices[0].message.content or ""
    return extract_json_obj(raw)


# 兼容旧调用名(extract_pipeline.py 里调的是 call_deepseek)
call_deepseek = call_llm


def to_hedge_event_row(announcement_id: str, extracted: dict) -> dict:
    """把 LLM 输出映射成 hedge_events 表的一行。need_review 由 confidence 和关键字段缺失决定。"""
    conf = extracted.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (ValueError, TypeError):
        conf = None

    limit = extracted.get("contract_value_limit")
    if isinstance(limit, str):
        limit = float(re.sub(r"[^\d.]", "", limit) or 0) or None

    # v2: 制度/可行性/进展/平仓类(is_hedging_announcement=false)本就没有额度,
    # 不应因 limit 为空进复核队列——否则回填历史后队列被非事件公告淹没。
    is_hedging = extracted.get("is_hedging_announcement")
    need_review = (
        (conf is not None and conf < 0.75)
        or (limit is None and is_hedging is not False)
        or not extracted.get("hedge_type")
    )

    return {
        "announcement_id": announcement_id,
        "hedge_type": extracted.get("hedge_type"),
        "instrument_type": extracted.get("instrument_type") or None,
        "underlying_asset": extracted.get("underlying_asset") or None,
        "risk_type": extracted.get("risk_type") or None,
        "approval_level": extracted.get("approval_level"),
        "authorization_period": extracted.get("authorization_period"),
        "contract_value_limit": limit,
        "contract_value_currency": extracted.get("contract_value_currency"),
        "contract_value_raw_text": extracted.get("contract_value_raw_text"),
        "confidence": conf,
        "need_review": need_review,
        # 下面这些是扩展字段,若 schema 未加列会被入库脚本忽略
        "_trade_venue": extracted.get("trade_venue"),
        "_contract_value_basis": extracted.get("contract_value_basis"),
        "_is_revolving": extracted.get("is_revolving"),
        "_use_own_funds": extracted.get("use_own_funds"),
        "_is_hedging_announcement": extracted.get("is_hedging_announcement"),
    }


def to_evidence_rows(announcement_id: str, extracted: dict) -> list[dict]:
    rows = []
    for ev in (extracted.get("evidence") or []):
        if not isinstance(ev, dict):
            continue
        rows.append({
            "announcement_id": announcement_id,
            "field_name": ev.get("field"),
            "page_no": None,
            "quote_text": (ev.get("quote") or "")[:200],
            "confidence": None,
        })
    return rows


# ----------------------------- 单文件测试入口 -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python extract_core.py <pdf路径> [标题]")
        sys.exit(1)
    pdf = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else Path(pdf).stem
    body = extract_pdf_text(pdf)
    print(f"提取正文 {len(body)} 字符")
    msgs = build_messages(title, body)
    if not (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
        print("\n[未配置 LLM_API_KEY,只打印将发送的 user prompt 前 800 字]\n")
        print(msgs[1]["content"][:800])
        sys.exit(0)
    extracted = call_llm(msgs)
    print("\n=== LLM 原始抽取 ===")
    print(json.dumps(extracted, ensure_ascii=False, indent=2))
    print("\n=== 映射为 hedge_events 行 ===")
    print(json.dumps(to_hedge_event_row("TEST", extracted), ensure_ascii=False, indent=2))
