#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公告计划额度 ↔ 定期报告事实的 A/B/C/D 可核验等级（M5 前置规则）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Verification:
    level: str
    result: str
    reason: str
    comparable_metric: str | None = None


def classify(plan_basis: str, available_metrics: set[str]) -> Verification:
    """只判断是否具备同口径事实，不在这里计算占用率。"""
    if plan_basis == "保证金占用":
        if "margin_peak_reported" in available_metrics:
            return Verification("A", "可直接核验", "年报明确披露期间最高保证金占用", "margin_peak_reported")
        if "margin_end_cash" in available_metrics:
            return Verification("B", "仅期末快照", "期末保证金不能代表期间最高占用", "margin_end_cash")
    elif plan_basis in {"名义本金", "合约价值"}:
        if "notional_peak_reported" in available_metrics:
            return Verification("A", "可直接核验", "年报明确披露期间最高名义本金", "notional_peak_reported")
        if "notional_end_reported" in available_metrics:
            return Verification("B", "仅期末快照", "期末名义本金不能代表期间最高值", "notional_end_reported")
    # 买入/卖出流量、期末公允价值、损益与额度量纲/口径不同，只能作一致性参考。
    if available_metrics:
        return Verification("C", "间接一致性", "存在相关披露，但没有与公告额度同口径的数值")
    return Verification("D", "无法核验", "定期报告未提供可用于核验的数值")

