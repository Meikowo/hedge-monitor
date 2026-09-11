"""Read-only M5 2025FY pilot. Produces reproducible source snapshots and review HTML.

No LLM calls, no database writes. All findings are provisional and source-linked.
"""
import argparse
from collections import Counter
import csv
from html import escape
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, log, sb_select, snapshot_json
from plan_actual_rules import FACT_BASIS, RULE_VERSION, canonical_reports, compare_names, compare_numeric, overall_status


def build_audit(data):
    profiles = {p['report_id']: p for p in data['profiles']}
    rows = []
    for report in canonical_reports(data['reports']):
        profile = profiles.get(report['report_id'], {})
        report_scopes = profile.get('scopes') or []
        facts = [m for m in data['metrics'] if m['report_id'] == report['report_id']]
        plans = [p for p in data['plans'] if p['code'] == report['code']
                 and p.get('ann_date') and p['ann_date'] <= report['period_end']
                 and p.get('ann_role') in ('计划-董事会', '计划-股东大会')]
        for scope in report_scopes or ['未明确']:
            scoped_plans = [p for p in plans if p.get('scope') in (scope, '综合', None)]
            # Never copy report-wide lists to each scope of a mixed report.
            actual_names = profile.get('underlyings') or [] if len(report_scopes) == 1 else []
            if len(report_scopes) > 1:
                actual_names = sorted({m['underlying'] for m in facts if m.get('scope') == scope
                                       and m.get('underlying') and m.get('value_verified') is True
                                       and m.get('quote_verified') is True})
            unambiguous = [p for p in scoped_plans if p.get('extraction_scopes') == [scope]]
            planned_names = sorted({s for p in unambiguous for s in p.get('underlyings', [])})
            planned_tools = sorted({s for p in unambiguous for s in p.get('instruments', [])})
            actual_tools = (profile.get('instruments') or []) if len(report_scopes) == 1 else []
            open_ended = any(re.search(r'不限于|包括但不限', p.get('raw_text','') + p.get('summary','')) for p in scoped_plans)
            underlyings = compare_names(planned_names, actual_names, open_ended)
            instruments = compare_names(planned_tools, actual_tools, open_ended)
            numeric = []
            for fact in facts:
                if fact.get('metric_type') not in FACT_BASIS:
                    continue
                if fact.get('scope') not in (scope, None):
                    continue
                numeric.append({**compare_numeric(report, fact, plans, report_scopes), 'fact':fact})
            venue = {'status':'insufficient_evidence', 'reason':'报告契约缺少可靠场所事实，不从币种或工具推断'}
            status = overall_status([underlyings['status'], instruments['status'], venue['status'],
                                     *(n['status'] for n in numeric)] if numeric else [])
            if report.get('status') != 'extracted' or not profile:
                status = 'unprocessed'
            rows.append({'code':report['code'],'name':report.get('name'), 'scope':scope,
                         'report':report,'profile':profile,'plans':scoped_plans,
                         'underlyings':underlyings,'instruments':instruments,'venue':venue,
                         'numeric':numeric,'status':status,'requires_review':True,
                         'rule_version':RULE_VERSION})
    return rows


def render_audit(rows):
    esc = lambda value: escape(str(value if value is not None else '未披露'))
    labels={'consistent':'已披露品种一致（预核对）','difference_needs_review':'品种差异待复核',
            'insufficient_evidence':'业务归属/证据不足','open_authorization':'开放授权，需复核'}
    def link(url, label, page=None):
        if urlparse(url or '').scheme not in {'http','https'}:
            return esc(label)
        target=(url or '').split('#')[0] + (f'#page={page}' if page else '')
        return f'<a href="{esc(target)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'
    body=[]
    for row in rows:
        numeric = '<br>'.join(esc(n['reason']) for n in row['numeric']) or '缺少可比较的实际占用指标'
        sources=link(row['report'].get('pdf_url'),'年报原文')
        seen=set()
        for plan in row['plans']:
            if plan['ann_id'] in seen:
                continue
            seen.add(plan['ann_id'])
            sources += ' · '+link(plan.get('pdf_url'),str(plan['ann_id']),plan.get('page'))
        detail=esc(json.dumps(row,ensure_ascii=False,indent=2))
        body.append(f"<tr><td>{esc(row['name'])}<small>{esc(row['code'])}</small></td>"
                    f"<td>{esc(row['scope'])}</td><td>{len(row['plans'])}</td>"
                    f"<td>{esc(labels.get(row['underlyings']['status'],row['underlyings']['status']))}</td><td>{numeric}</td>"
                    f"<td>{sources}<details><summary>查看两侧事实与来源</summary><pre>{detail}</pre></details></td></tr>")
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M5 2025FY 核对样本</title><style>body{font:14px/1.6 system-ui;color:#202124;margin:24px;background:#fff}
table{border-collapse:collapse;width:100%}th,td{padding:10px;border:1px solid #ddd;text-align:left;vertical-align:top}
th{background:#f8f9fa}small{display:block;color:#667}pre{white-space:pre-wrap;max-width:700px;max-height:65vh;overflow:auto;font:12px/1.6 monospace}
summary{cursor:pointer;color:#245a8c}h1{font-size:20px}p{color:#555}</style><h1>M5 · 2025FY 真实样本预核对</h1>
<p>复核材料，不是正式结论。仅核对候选计划与披露事实；缺少证据不代表未开展或违规。授权候选检索覆盖上一年起至报告期末。</p>
<table><thead><tr><th>公司</th><th>业务类别</th><th>候选额度条数</th><th>品种预核对</th><th>数值核对与限制</th><th>证据</th></tr></thead><tbody>''' + ''.join(body) + '</tbody></table></html>'


def select_ids(table, field, values, select='*'):
    rows=[]
    for start in range(0,len(values),100):
        rows.extend(sb_select(table, {'select':select, field:f"in.({','.join(values[start:start+100])})"},paginate=True))
    return rows


def verify_period_sources(plans):
    """Full period text must be on the stated PDF page, not merely a 40-char prefix."""
    import fitz
    import cninfo
    texts={}
    for plan in plans:
        period=plan.get('period_text') or ''
        if len(re.findall(r'20\d{2}年\d{1,2}月\d{1,2}日', period)) != 2:
            continue
        aid=plan['ann_id']
        if aid not in texts:
            content=cninfo.download_pdf(plan['pdf_url']) if plan.get('pdf_url') else None
            if content:
                with fitz.open(stream=content,filetype='pdf') as doc:
                    texts[aid]=[page.get_text() for page in doc]
            else:
                texts[aid]=[]
        strip=lambda text: re.sub(r'\s+','',text or '')
        for evidence in plan.get('evidence') or []:
            page=evidence.get('page')
            quote=evidence.get('quote') or ''
            if evidence.get('field') != 'period' or not isinstance(page,int) or not (0<page<=len(texts[aid])):
                continue
            if strip(period) in strip(quote) and strip(quote) in strip(texts[aid][page-1]):
                plan.update(period_quote=quote,period_page=page,period_quote_verified=True)
                break
    log(f'授权期原页全文回验：{sum(p.get("period_quote_verified") is True for p in plans)}/{len(plans)} 条额度')


def load_inputs(sample, verify_periods=False):
    with open(sample,encoding='utf-8-sig',newline='') as f:
        companies=list(csv.DictReader(f))
    codes=[row['code'] for row in companies]
    reports=sb_select('periodic_reports',{'select':'*','code':f"in.({','.join(codes)})",
                        'fiscal_year':'eq.2025','report_type':'eq.annual'},paginate=True)
    ids=[r['report_id'] for r in reports]
    profiles=select_ids('periodic_derivatives','report_id',ids,
                        'report_id,scopes,instruments,underlyings,summary,disclosure_status,evidence,review_status')
    metrics=select_ids('periodic_metric_items','report_id',ids)
    announcements=sb_select('announcements',{'select':'ann_id,code,title,ann_date,pdf_url',
                      'code':f"in.({','.join(codes)})",'and':'(ann_date.gte.2024-01-01,ann_date.lte.2025-12-31)'},paginate=True)
    anns={a['ann_id']:a for a in announcements}
    extracts=select_ids('extractions','ann_id',list(anns),
                       'ann_id,ann_role,scope,instruments,underlyings,period_text,evidence,summary')
    extractions={e['ann_id']:e for e in extracts if e['ann_role'] in ('计划-董事会','计划-股东大会')}
    quotas=select_ids('quota_items','ann_id',list(extractions))
    plans=[]
    for quota in quotas:
        ext=extractions[quota['ann_id']]
        plan={**anns[quota['ann_id']],**ext,**quota,'extraction_scopes':ext.get('scope') or []}
        plans.append(plan)
    if verify_periods:
        verify_period_sources(plans)
    covered={r['code'] for r in reports}
    for company in companies:
        if company['code'] not in covered:
            reports.append({**company,'report_id':None,'fiscal_year':2025,'report_type':'annual',
                            'period_end':'2025-12-31','status':'not_found'})
    return {'reports':reports,'profiles':profiles,'metrics':metrics,'plans':plans}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',default=str(ROOT/'config/m5_validation_2025.csv'))
    parser.add_argument('--input',help='Recompute a saved source snapshot without any network calls')
    parser.add_argument('--verify-periods',action='store_true')
    args=parser.parse_args()
    data=json.loads(Path(args.input).read_text(encoding='utf-8')) if args.input else load_inputs(args.sample,args.verify_periods)
    if not args.input:
        snapshot_json('m5_sources_2025',data)
    rows=build_audit(data)
    path=snapshot_json('m5_audit_2025',rows)
    path.with_suffix('.html').write_text(render_audit(rows),encoding='utf-8')
    log(f"M5 样本 {len({r['code'] for r in rows})} 家，业务行 {len(rows)}；没有写数据库")
    log(str(dict(Counter(n['status'] for r in rows for n in r['numeric']))))


if __name__ == '__main__':
    main()
