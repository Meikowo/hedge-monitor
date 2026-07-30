#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6a deterministic relevance gate for derivatives-related risk documents."""
from __future__ import annotations

from dataclasses import dataclass


DERIVATIVE_TERMS = (
    "套期保值",
    "套保",
    "衍生金融工具",
    "衍生品",
    "期货",
    "商品期权",
    "外汇期权",
    "场外期权",
    "期货期权",
    "期权交易",
    "期权合约",
    "期权业务",
    "期权套保",
    "远期结售汇",
    "外汇远期",
    "远期外汇",
    "商品远期",
    "远期购汇",
    "远期售汇",
    "远期合约",
    "远期交易",
    "掉期",
    "利率互换",
    "货币互换",
    "金融互换",
    "互换合约",
    "互换交易",
    "对冲",
)

RISK_TERMS = (
    "未经授权",
    "超授权",
    "偏离套保目的",
    "投机",
    "重大损失",
    "亏损",
    "保证金",
    "流动性风险",
    "审批",
    "内控",
    "会计",
    "信息披露",
    "违规",
    "整改",
    "处罚",
    "追责",
    "监管措施",
    "监管警示",
    "额度不一致",
    "期限不一致",
    "场所不一致",
)

GENERIC_POLICY_TERMS = (
    "一般会计政策",
    "企业会计准则",
    "会计政策和会计估计",
    "衍生金融工具会计政策",
)

COMPANY_EVENT_TERMS = (
    "公司未经",
    "公司发生",
    "公司存在",
    "实际损失",
    "风险敞口",
    "补充保证金",
    "强制平仓",
    "监管工作函",
    "问询函",
    "监管警示",
    "纪律处分",
    "行政处罚",
    "责令改正",
)


@dataclass(frozen=True)
class RelevanceAssessment:
    candidate: bool
    matched_derivative_terms: tuple[str, ...]
    matched_risk_terms: tuple[str, ...]
    reason: str


def _matches(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    hits: list[str] = []
    for term in terms:
        if term in text:
            hits.append(term)
        elif term == "未经授权":
            start = text.find("未经")
            if start >= 0 and "授权" in text[start:start + 12]:
                hits.append(term)
    return tuple(hits)


def assess_relevance(
    title: str,
    text: str = "",
    source_type: str = "other_official",
) -> RelevanceAssessment:
    """Conservative rule gate; formal cases still require LLM and human review."""
    combined = f"{title}\n{text}"
    # 监管决定末尾的固定表述不是上市公司开展期货业务的事实。
    combined = combined.replace("证券期货市场诚信档案数据库", "证券市场诚信档案数据库")
    combined = combined.replace("证券期货市场诚信档案", "证券市场诚信档案")
    # 航运舱位交换是运营安排，不是金融互换合约。
    combined = combined.replace("舱位互换", "舱位调换")
    derivative = _matches(combined, DERIVATIVE_TERMS)
    risk = _matches(combined, RISK_TERMS)

    generic_policy = any(term in combined for term in GENERIC_POLICY_TERMS)
    concrete_event = any(term in combined for term in COMPANY_EVENT_TERMS)
    if generic_policy and not concrete_event:
        return RelevanceAssessment(False, derivative, risk, "仅通用政策，未见公司具体风险事件")
    if not derivative:
        return RelevanceAssessment(False, derivative, risk, "未命中衍生品业务词")
    if not risk:
        return RelevanceAssessment(False, derivative, risk, "命中衍生品词但未命中风险事实词")

    if source_type in {"inquiry", "regulatory_measure", "disciplinary_action",
                       "administrative_penalty"}:
        return RelevanceAssessment(True, derivative, risk, "监管来源同时命中衍生品与风险词")
    return RelevanceAssessment(True, derivative, risk, "同时命中衍生品与具体风险词")
