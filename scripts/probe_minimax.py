#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_minimax.py —— MiniMax API 可达性探活
============================================
2026-07-08 教训：任何国内接口从 GitHub Actions 的可达性必须逐源实测，
不能类比推断（东财/akshare 曾被机房 IP 段拉黑）。本脚本在架构定型前
实测 MiniMax@Actions：成功 → 抽取跑 Actions；失败 → 抽取降级本地跑。

用法：python scripts/probe_minimax.py
退出码：0=可达且返回正常；1=失败（Actions 会标红）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import env, log


def main() -> int:
    from openai import OpenAI
    base = env("LLM_BASE_URL", "https://api.minimaxi.com/v1")
    model = env("LLM_MODEL", "MiniMax-M3")
    log(f"探活目标: {base} | 模型: {model}")
    client = OpenAI(api_key=env("LLM_API_KEY", required=True), base_url=base)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "只回复两个字：正常"}],
            max_tokens=512,
            extra_body={"thinking": {"type": "disabled"}},
        )
        latency = time.time() - t0
        content = (resp.choices[0].message.content or "").strip()[:50]
        log(f"✅ 可达。往返 {latency:.1f}s | 返回: {content!r} | usage: {resp.usage}")
        return 0
    except Exception as e:
        log(f"❌ 探活失败: {repr(e)[:300]}")
        log("结论：MiniMax 从 Actions 不可达或密钥无效 → 抽取需降级为本地执行，"
            "或换 LLM_BASE_URL 指向可达的兼容厂商。请把上面的报错原样贴回会话。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
