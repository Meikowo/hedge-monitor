"""M5 first-stage deterministic pre-checks. Pure functions; never mutate source facts.

All results remain requires_review: string/number verification is not semantic approval.
Only explicit, source-verified calendar dates can establish candidate coverage here.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
try:
    from .metric_evidence import is_authorization_peak
except ImportError:  # Direct script execution by the audit CLI.
    from metric_evidence import is_authorization_peak

RULE_VERSION = 'm5-poc-v1'
FACT_BASIS = {
    'margin_end_cash': ('保证金占用', 'period_end'),
    'margin_peak_reported': ('保证金占用', 'period_peak'),
    'notional_end_reported': ('名义本金', 'period_end'),
    'notional_peak_reported': ('名义本金', 'period_peak'),
}
UNITS = {'元': 1, '千元': 1000, '万元': 10000, '亿元': 100000000}
ALIASES = {'美金': '美元', 'USD': '美元', 'EUR': '欧元', 'JPY': '日元',
           '外汇远期': '远期', '远期外汇': '远期', '远期结售汇': '远期',
           '商品期货': '期货', '外汇期权': '期权', '外汇掉期': '掉期'}
GENERIC = {'其他', '商品', '外汇', '商品衍生品', '金融衍生品', '衍生品', '未明确'}
REASONS = {
    'within_snapshot': '同口径候选上限内；仅报告期末时点，不证明全年未超限',
    'within_period': '同口径期间峰值低于候选上限；需确认授权效力及业务覆盖',
    'exceeds_disclosed_cap': '超过披露上限，需复核；不作违规结论',
    'missing_value': '数值为空、非有限数或无有效数值，不能按零处理',
    'basis_incomparable': '实际指标与公告额度口径不可比',
    'currency_mismatch': '币种不同或缺失，不进行汇率换算',
    'unit_unknown': '缺少确定的单位倍率',
    'coverage_uncertain': '现金保证金、授信、担保品或非衍生品资金覆盖范围待核实',
    'scope_uncertain': '报告合计或综合额度不能自动分配至各业务类别',
    'evidence_unverified': '数字/引文未通过回验或来源缺失',
    'period_unknown': '授权期缺少已回验的绝对起止日期；不得用年度标签或公告日替代',
    'period_uncovered': '明确授权区间未覆盖报告日或完整报告期间',
    'quota_conflict': '存在多个不同候选额度/期间，需核实调额与替代关系',
    'no_plan': '所检索候选中没有对应公司的实际计划类额度；不等于从未授权',
    'unprocessed': '报告尚未提取，不能当作未披露',
    'actual_is_authorization': '原文为计划授权上限，不是已发生的实际占用',
}


def result(status, **details):
    return {'status': status, 'reason': REASONS.get(status, status),
            'rule_version': RULE_VERSION, 'requires_review': True, **details}


def decimal_value(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def compact(value):
    return re.sub(r'\s+', '', value or '')


def explicit_period(plan):
    text = compact(plan.get('period_text'))
    quote = compact(plan.get('period_quote'))
    if not plan.get('period_quote_verified') or not text or text not in quote:
        return None
    dates = re.findall(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', text)
    if len(dates) != 2:
        return None
    try:
        start, end = (date(*(int(v) for v in x)) for x in dates)
        return (start, end) if start <= end else None
    except ValueError:
        return None


def compare_numeric(report, metric, plans, report_scopes):
    context = {'report_id': report.get('report_id'), 'metric_id': metric.get('id')}
    out = lambda status, **kw: result(status, **{**context, **kw})
    if report.get('status') != 'extracted':
        return out('unprocessed')
    spec = FACT_BASIS.get(metric.get('metric_type'))
    if not spec or metric.get('time_basis') != spec[1]:
        return out('basis_incomparable')
    if spec[1] == 'period_peak' and is_authorization_peak(metric.get('raw_text', ''), metric.get('value')):
        return out('actual_is_authorization')
    value = decimal_value(metric.get('value'))
    if value is None:
        return out('missing_value')
    if not (metric.get('value_verified') is True and metric.get('quote_verified') is True
            and metric.get('raw_text') and metric.get('page')):
        return out('evidence_unverified')
    scale = UNITS.get(metric.get('unit'))
    if scale is None:
        return out('unit_unknown')
    scope = metric.get('scope')
    if metric.get('fact_level') == 'report':
        if len(report_scopes) != 1:
            return out('scope_uncertain')
        scope = report_scopes[0]
    if scope not in {'商品', '外汇', '利率'}:
        return out('scope_uncertain')
    candidates = [p for p in plans if p.get('code') == report.get('code')
                  and p.get('ann_role') in ('计划-董事会', '计划-股东大会')]
    if not candidates:
        return out('no_plan')
    candidates = [p for p in candidates if p.get('basis') == spec[0]
                  and p.get('scope') in (scope, '综合', None)]
    if not candidates:
        return out('basis_incomparable')
    context['source_quota_ids'] = sorted({p['id'] for p in candidates})
    if any(p.get('scope') != scope for p in candidates):
        return out('scope_uncertain')
    if any(not (p.get('amount_verified') is True and p.get('quote_verified') is True
                and p.get('raw_text') and p.get('page')) for p in candidates):
        return out('evidence_unverified')
    if any(decimal_value(p.get('amount')) is None for p in candidates):
        return out('missing_value')
    if not metric.get('currency') or any(p.get('currency') != metric['currency'] for p in candidates):
        return out('currency_mismatch')
    # Do not infer matching funding coverage from a coarse metric_type label.
    uncertain = r'授信|担保|抵押|信用证|保函|履约|投标|票据'
    if re.search(uncertain, metric.get('raw_text', '')) or any(
            re.search(uncertain, p.get('raw_text', '')) for p in candidates):
        return out('coverage_uncertain')
    periods = [explicit_period(p) for p in candidates]
    if any(period is None for period in periods):
        return out('period_unknown')
    try:
        end = date.fromisoformat(report['period_end'])
        start = date(int(report['fiscal_year']), 1, 1) if spec[1] == 'period_peak' else end
    except (ValueError, KeyError, TypeError):
        return out('period_unknown')
    applicable = [(p, window) for p, window in zip(candidates, periods)
                  if window[0] <= start and window[1] >= end]
    if not applicable:
        return out('period_uncovered')
    # A partial-period different cap blocks annual peak conclusions too.
    overlapping = [(p, window) for p, window in zip(candidates, periods)
                   if window[0] <= end and window[1] >= start]
    identities = {(decimal_value(p['amount']), window) for p, window in overlapping}
    if len(identities) != 1:
        return out('quota_conflict')
    quota = decimal_value(applicable[0][0]['amount'])
    actual = value * scale
    grade = 'B' if spec[1] == 'period_end' else 'A'
    status = 'exceeds_disclosed_cap' if actual > quota else (
        'within_snapshot' if grade == 'B' else 'within_period')
    return out(status, grade=grade, actual_base=format(actual, 'f'),
               quota_base=format(quota, 'f'), currency=metric['currency'],
               unit_multiplier=scale, source_quota_ids=sorted({p['id'] for p, _ in applicable}),
               authorization_start=applicable[0][1][0].isoformat(),
               authorization_end=applicable[0][1][1].isoformat())


def compare_names(plan_values, actual_values, open_ended=False):
    def norm(values):
        return {ALIASES.get(x.strip(), x.strip()) for x in values if isinstance(x, str) and x.strip()}
    planned, actual = norm(plan_values), norm(actual_values)
    if not planned or not actual or (planned | actual) & GENERIC:
        status = 'insufficient_evidence'
    elif open_ended:
        status = 'open_authorization'
    else:
        status = 'consistent' if not actual - planned else 'difference_needs_review'
    return {'status': status, 'plan_raw': plan_values, 'actual_raw': actual_values,
            'intersection': sorted(planned & actual), 'plan_only': sorted(planned - actual),
            'actual_only': sorted(actual - planned)}


def overall_status(statuses):
    # Missing dimensions never become a full match; numeric matches are still provisional.
    return 'precheck_consistent' if statuses and all(
        status in {'consistent', 'within_snapshot', 'within_period'} for status in statuses
    ) else 'needs_review'


def canonical_reports(rows):
    priority = {'skipped': 1, 'failed': 2, 'needs_ocr': 3, 'discovered': 4,
                'located': 5, 'extracted': 6}
    rank = lambda row: (priority.get(row.get('status'), 0), bool(row.get('is_revised')),
                        row.get('publish_date') or '', row.get('report_id') or '')
    selected = {}
    for row in rows:
        key = (row.get('code'), row.get('fiscal_year'), row.get('report_type'))
        if key not in selected or rank(row) > rank(selected[key]):
            selected[key] = row
    return list(selected.values())
