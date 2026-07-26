#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定期报告套保披露结构化提示词。"""

PROMPT_VERSION = "periodic-v2.1-multipass"

METRIC_FAMILIES = {
    "operations": (
        "period_purchase_amount",
        "period_sale_amount",
        "ending_balance",
        "net_asset_ratio",
        "notional_end_reported",
        "notional_peak_reported",
        "contract_quantity_end",
    ),
    "pnl": (
        "reported_derivative_comprehensive_pnl",
        "derivative_disposal_investment_income",
        "derivative_fv_change_pnl",
        "oci_amount",
        "reclassification_amount",
    ),
    "position": (
        "derivative_asset_fv",
        "derivative_liability_fv",
        "derivative_net_fv",
        "margin_end_cash",
        "margin_peak_reported",
        "collateral_end_fair_value",
        "credit_facility_used_end",
        "option_premium_usage_peak",
    ),
}

METRIC_FAMILY_GUIDANCE = {
    "operations": """
- period_purchase_amount / period_sale_amount：衍生品投资表直接披露的报告期购入/售出金额。
- ending_balance：表格直接披露的期末投资金额或期末余额，不等同于公允价值净额。
- net_asset_ratio：期末投资金额占净资产比例。
- notional_end_reported / notional_peak_reported：仅限原文明示的期末/期间最高名义本金。
- contract_quantity_end：期末合约数量（吨、手等）。
""",
    "pnl": """
- reported_derivative_comprehensive_pnl：衍生品投资情况表直接披露的报告期损益合计。
- derivative_disposal_investment_income：附注“投资收益”中处置衍生金融工具的金额。
- derivative_fv_change_pnl：附注“公允价值变动损益”中衍生工具的金额。
- oci_amount：其他综合收益或套期储备中明确归属于套期会计/衍生工具的金额。
- reclassification_amount：套期储备重分类进损益或资产成本的金额。
- 报表中的“—”或“-”表示无金额，不得输出为0；只有原文数字0才能输出0。
""",
    "position": """
- derivative_asset_fv / derivative_liability_fv：期末衍生金融资产/负债总额，必须分列。
- derivative_net_fv：仅在原文直接披露净额时记录，不得自行用资产减负债生成。
- margin_end_cash：报告日期末保证金余额，并保留列示科目和受限状态。
- margin_peak_reported：仅限原文明示的报告期最高保证金。
- collateral_end_fair_value：期末抵押品公允价值。
- credit_facility_used_end / option_premium_usage_peak：期末已用授信/期间最高权利金占用。
""",
}

SYSTEM_PROMPT = """你是A股定期报告套期保值信息抽取引擎。只输出一个JSON对象。
铁律：
1. 只记录候选页原文明确披露的事实；没有就填null或空数组。
2. 禁止估算、推导、合并现货端与衍生品端损益，禁止用行情反推。
3. 每个数值保留原文数值、币种、单位、页码和不超过120字的原文摘录。
4. 区分报告期流量、期末时点和期间峰值；区分经济套保效果与会计报表影响。
5. 区分报告级合计、业务类别和具体品种；公司合计不得分摊到商品、外汇或品种。
6. 期末公允价值、期间买入卖出额不能冒充授权额度或最高占用额。
7. 衍生金融资产、衍生金融负债和净额分别记录；净额不能替代资产或负债。
8. “未披露”必须输出null，不能输出0。"""

INSTRUCTION = '''请从下列年报候选页抽取严格JSON：
{
  "disclosure_status": "有数值"|"提及无数值"|"未提及"|"需复核",
  "scopes": ["商品"|"外汇"|"利率"|"其他"],
  "instruments": ["期货","期权","远期结售汇","外汇远期","外汇掉期","货币互换","利率互换","其他"],
  "underlyings": ["铜","铝","美元"...],
  "purpose": "原文明确披露的套保目的" | null,
  "hedge_accounting_status": "已应用"|"未应用"|"混合应用"|"未明确披露"|"需复核",
  "hedge_accounting_types": ["公允价值套期"|"现金流量套期"|"境外经营净投资套期"|"其他"],
  "non_application_reason": "原文明示的未应用原因"|null,
  "hedge_accounting_evidence": {"page": 123, "quote": "明确勾选或原文陈述"} | null,
  "hedge_accounting_items": [
    {
      "scope": "商品"|"外汇"|"利率"|"其他"|null,
      "instrument": "期货/期权/外汇远期等"|null,
      "underlying_asset": "原文品种"|null,
      "application_status": "已应用"|"未应用"|"未明确披露"|"需复核",
      "accounting_type": "公允价值套期"|"现金流量套期"|"境外经营净投资套期"|"其他"|null,
      "non_application_reason": "原文明示的未应用原因"|null,
      "source_section": "套期会计/衍生品投资情况/财务报表附注等",
      "page": 123,
      "quote": "支持该业务级结论的原文摘录",
      "confidence": 0.0
    }
  ],
  "metrics": [
    {
      "metric_type": "period_purchase_amount"|"period_sale_amount"|"reported_derivative_comprehensive_pnl"|"derivative_disposal_investment_income"|"derivative_fv_change_pnl"|"ending_balance"|"net_asset_ratio"|"derivative_asset_fv"|"derivative_liability_fv"|"derivative_net_fv"|"margin_end_cash"|"margin_peak_reported"|"collateral_end_fair_value"|"credit_facility_used_end"|"option_premium_usage_peak"|"notional_end_reported"|"notional_peak_reported"|"contract_quantity_end"|"oci_amount"|"reclassification_amount",
      "fact_level": "report"|"scope"|"underlying",
      "scope": "商品"|"外汇"|"利率"|"其他"|null,
      "underlying": "原文品种"|null,
      "value": 1234.56,
      "currency": "CNY"|"USD"|"EUR"|"HKD"|"JPY"|"其他"|null,
      "unit": "元"|"万元"|"亿元"|"万美元"|"%"|"吨"|"手"|"其他",
      "time_basis": "period"|"period_end"|"period_peak",
      "source_section": "衍生品投资情况/财务报表附注/管理层讨论等",
      "account_name": "其他货币资金/其他应收款等"|null,
      "is_restricted": true|false|null,
      "counterparty": "期货公司或其他对手方"|null,
      "raw": "包含该数字的原文摘录，不超过120字",
      "page": 123
    }
  ],
  "evidence": [{"field":"scopes","quote":"原文摘录","page":123}],
  "summary": "只概括已披露事实，不作评价，不超过100字",
  "confidence": 0.0
}

口径说明：
- reported_derivative_comprehensive_pnl：公司衍生品投资情况表直接披露的综合损益，可能同时包含投资收益、公允价值变动和浮动损益。
- derivative_disposal_investment_income：财务附注明确披露的处置衍生金融工具投资收益。
- derivative_fv_change_pnl：财务附注明确披露的衍生工具公允价值变动损益。
- derivative_asset_fv、derivative_liability_fv、derivative_net_fv 必须分列；净额只在原文直接披露时记录。
- fact_level=report 时 scope 和 underlying 必须为null；报告级数值不得复制到业务类别。
- notional_end_reported：原文明示的期末名义本金；notional_peak_reported：原文明示的期间最高值。
- margin_end_cash 是期末快照，不能标成 period_peak；同时提取列示科目、是否受限和对手方（若披露）。
- margin_peak_reported 只在原文明确写“报告期最高/最大保证金占用”时使用。
- 套期会计以明确勾选或原文陈述为准；未应用但未解释原因时 non_application_reason=null。
- 同一报告不同业务的套期会计处理不同时，报告级状态填“混合应用”，并逐项输出 hedge_accounting_items。
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


def _report_context(
    title: str,
    name: str,
    code: str,
    report_period: str,
    body: str,
) -> str:
    return f"""报告标题：{title or ""}
公司：{name or ""}（{code or ""}）
报告期：{report_period or ""}
候选页正文：
\"\"\"
{body}
\"\"\""""


def build_profile_messages(
    title: str,
    name: str,
    code: str,
    report_period: str,
    body: str,
) -> list[dict]:
    instruction = """本次只抽取报告摘要、业务范围和套期会计，不输出任何 metrics。
只输出以下JSON对象，不要解释：
{
  "disclosure_status": "有数值"|"提及无数值"|"未提及"|"需复核",
  "scopes": ["商品"|"外汇"|"利率"|"其他"],
  "instruments": ["期货","期权","远期结售汇","外汇远期","外汇掉期","货币互换","利率互换","其他"],
  "underlyings": ["原文品种"],
  "purpose": "原文明确目的"|null,
  "hedge_accounting_status": "已应用"|"未应用"|"混合应用"|"未明确披露"|"需复核",
  "hedge_accounting_types": ["公允价值套期"|"现金流量套期"|"境外经营净投资套期"|"其他"],
  "non_application_reason": "原文明示原因"|null,
  "hedge_accounting_evidence": {"page": 123, "quote": "原文摘录"}|null,
  "hedge_accounting_items": [{
    "scope": "商品"|"外汇"|"利率"|"其他"|null,
    "instrument": "原文工具"|null,
    "underlying_asset": "原文品种"|null,
    "application_status": "已应用"|"未应用"|"未明确披露"|"需复核",
    "accounting_type": "公允价值套期"|"现金流量套期"|"境外经营净投资套期"|"其他"|null,
    "non_application_reason": "原文明示原因"|null,
    "source_section": "章节",
    "page": 123,
    "quote": "原文摘录",
    "confidence": 0.0
  }],
  "evidence": [{"field": "scopes", "quote": "原文摘录", "page": 123}],
  "summary": "不超过100字",
  "confidence": 0.0
}
未应用但未解释原因时原因必须为null；不同业务处理不同则报告级为“混合应用”。
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction + _report_context(
            title, name, code, report_period, body
        )},
    ]


def build_metric_messages(
    family: str,
    title: str,
    name: str,
    code: str,
    report_period: str,
    body: str,
) -> list[dict]:
    allowed = METRIC_FAMILIES[family]
    instruction = f"""本次只抽取 {family} 数值事实，只输出JSON对象 {{"metrics":[]}}。
metric_type 只允许：{", ".join(allowed)}。
字段口径：{METRIC_FAMILY_GUIDANCE[family]}
每项结构：
{{
  "metric_type": "上列枚举",
  "fact_level": "report"|"scope"|"underlying",
  "scope": "商品"|"外汇"|"利率"|"其他"|null,
  "underlying": "原文品种"|null,
  "value": 1234.56,
  "currency": "CNY"|"USD"|"EUR"|"HKD"|"JPY"|"其他"|null,
  "unit": "元"|"万元"|"亿元"|"万美元"|"%"|"吨"|"手"|"其他",
  "time_basis": "period"|"period_end"|"period_peak",
  "source_section": "章节",
  "account_name": "列示科目"|null,
  "is_restricted": true|false|null,
  "counterparty": "对手方"|null,
  "raw": "包含该数字的原文摘录，不超过80字",
  "page": 123
}}
只记录原文直接披露且摘录中出现的数字；没有就返回空数组。报告级合计不得复制到类别。
资产、负债、净额分列；期末保证金不得标成期间峰值。
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction + _report_context(
            title, name, code, report_period, body
        )},
    ]
