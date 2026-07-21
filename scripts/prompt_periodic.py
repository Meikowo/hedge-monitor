#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定期报告套保披露结构化提示词。"""

PROMPT_VERSION = "periodic-v1.0"

SYSTEM_PROMPT = """你是A股定期报告套期保值信息抽取引擎。只输出一个JSON对象。
铁律：
1. 只记录候选页原文明确披露的事实；没有就填null或空数组。
2. 禁止估算、推导、合并现货端与衍生品端损益，禁止用行情反推。
3. 每个数值保留原文数值、币种、单位、页码和不超过120字的原文摘录。
4. 区分报告期流量、期末时点和期间峰值；区分经济套保效果与会计报表影响。
5. 期末公允价值、期间买入卖出额不能冒充授权额度或最高占用额。"""

INSTRUCTION = '''请从下列年报候选页抽取严格JSON：
{
  "disclosure_status": "有数值"|"提及无数值"|"未提及"|"需复核",
  "scopes": ["商品"|"外汇"|"利率"|"其他"],
  "instruments": ["期货","期权","远期结售汇","外汇远期","外汇掉期","货币互换","利率互换","其他"],
  "underlyings": ["铜","铝","美元"...],
  "purpose": "原文明确披露的套保目的" | null,
  "hedge_accounting": ["未指定套期关系"|"公允价值套期"|"现金流量套期"|"境外经营净投资套期"|"未披露"],
  "metrics": [
    {
      "metric_type": "period_purchase_amount"|"period_sale_amount"|"period_pnl"|"ending_balance"|"net_asset_ratio"|"derivative_asset_fv"|"derivative_liability_fv"|"margin_end_cash"|"margin_peak_reported"|"collateral_end_fair_value"|"credit_facility_used_end"|"option_premium_usage_peak"|"notional_end_reported"|"notional_peak_reported"|"contract_quantity_end"|"oci_amount"|"reclassification_amount",
      "scope": "商品"|"外汇"|"利率"|"其他"|null,
      "underlying": "原文品种"|null,
      "value": 1234.56,
      "currency": "CNY"|"USD"|"EUR"|"HKD"|"JPY"|"其他"|null,
      "unit": "元"|"万元"|"亿元"|"万美元"|"%"|"吨"|"手"|"其他",
      "time_basis": "period"|"period_end"|"period_peak",
      "source_section": "衍生品投资情况/财务报表附注/管理层讨论等",
      "raw": "包含该数字的原文摘录，不超过120字",
      "page": 123
    }
  ],
  "evidence": [{"field":"scopes","quote":"原文摘录","page":123}],
  "summary": "只概括已披露事实，不作评价，不超过100字",
  "confidence": 0.0
}

口径说明：
- period_pnl：仅限原文明示的报告期套保/衍生品损益，不把现货经营损益推导进去。
- notional_end_reported：原文明示的期末名义本金；notional_peak_reported：原文明示的期间最高值。
- margin_end_cash 是期末快照，不能标成 period_peak。
- margin_peak_reported 只在原文明确写“报告期最高/最大保证金占用”时使用。
- 报告提及套保但没有可抽数值，填“提及无数值”且 metrics=[]。
- 候选页完全没有相关内容，填“未提及”。版面/表格无法可靠判断时填“需复核”。

报告标题：{title}
公司：{name}（{code}）
报告期：{report_period}
候选页正文：
"""
{body}
"""
'''


def build_messages(title: str, name: str, code: str, report_period: str, body: str) -> list[dict]:
    user = (INSTRUCTION.replace("{title}", title or "")
            .replace("{name}", name or "")
            .replace("{code}", code or "")
            .replace("{report_period}", report_period or "")
            .replace("{body}", body))
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]
