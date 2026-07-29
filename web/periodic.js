const VERIFIED = (item) => item?.value_verified === true && item?.quote_verified === true;

const TYPE_LABELS = {
  period_purchase_amount: "报告期购入",
  period_sale_amount: "报告期售出",
  reported_derivative_comprehensive_pnl: "衍生品综合损益",
  derivative_disposal_investment_income: "投资收益相关",
  derivative_fv_change_pnl: "公允价值变动损益",
  ending_balance: "期末金额",
  net_asset_ratio: "期末净资产占比",
  derivative_asset_fv: "衍生金融资产",
  derivative_liability_fv: "衍生金融负债",
  derivative_net_fv: "公允价值净额",
  margin_end_cash: "期末保证金",
  margin_peak_reported: "期间保证金峰值",
  collateral_end_fair_value: "期末担保品公允价值",
  credit_facility_used_end: "期末已用授信",
  option_premium_usage_peak: "期权权利金峰值",
  notional_end_reported: "期末名义本金",
  notional_peak_reported: "期间名义本金峰值",
  contract_quantity_end: "期末合约数量",
  oci_amount: "计入权益金额",
  reclassification_amount: "重分类金额"
};

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function hasFiniteMetricValue(value) {
  return value !== null
    && value !== undefined
    && String(value).trim() !== ""
    && Number.isFinite(Number(value));
}

function aggregateCompatibleMetrics(candidates, isReportTotal) {
  if (candidates.length < 2 || isReportTotal) return null;
  const compatibilityFields = [
    "metric_type",
    "fact_level",
    "scope",
    "currency",
    "unit",
    "time_basis"
  ];
  const first = candidates[0];
  const compatible = candidates.every((item) => (
    hasFiniteMetricValue(item.value)
    && compatibilityFields.every((field) => (item[field] ?? null) === (first[field] ?? null))
  ));
  const identities = candidates.map((item) => [
    item.underlying,
    item.account_name
  ].filter(Boolean).join("|"));
  const distinguishable = identities.every(Boolean) && new Set(identities).size === candidates.length;
  if (!compatible || !distinguishable) return null;
  const pages = unique(candidates.map((item) => item.page));
  return {
    ...first,
    value: Math.round(candidates.reduce((sum, item) => sum + Number(item.value), 0) * 1e8) / 1e8,
    underlying: null,
    account_name: null,
    raw_text: `${candidates.length} 项同口径事实合计`,
    page: pages.length === 1 ? pages[0] : null,
    items: candidates,
    multipleCount: candidates.length,
    isAggregated: true,
    isReportTotal
  };
}

function chooseMetric(items, scope) {
  const scoped = items.filter((item) => item.fact_level !== "report" && item.scope === scope);
  const exact = scoped.filter((item) => item.fact_level === "scope");
  const candidates = exact.length ? exact : scoped;
  if (candidates.length === 1) return { ...candidates[0], isReportTotal: false };
  if (candidates.length > 1) {
    return aggregateCompatibleMetrics(candidates, false)
      || { items: candidates, multipleCount: candidates.length, value: null, isReportTotal: false };
  }
  const reportItems = items.filter((item) => item.fact_level === "report");
  if (reportItems.length === 1) return { ...reportItems[0], isReportTotal: true };
  if (reportItems.length > 1) {
    return aggregateCompatibleMetrics(reportItems, true)
      || { items: reportItems, multipleCount: reportItems.length, value: null, isReportTotal: true };
  }
  return null;
}

export function metricFor(row, metricType) {
  const direct = chooseMetric(
    row.verifiedMetrics.filter((item) => item.metric_type === metricType),
    row.scope
  );
  if (direct || metricType !== "derivative_net_fv") return direct;
  const asset = metricFor(row, "derivative_asset_fv");
  const liability = metricFor(row, "derivative_liability_fv");
  if (
    !asset || !liability
    || asset.value === null || liability.value === null
    || asset.unit !== liability.unit
    || asset.currency !== liability.currency
  ) return null;
  return {
    metric_type: "derivative_net_fv",
    value: Math.round((Number(asset.value) - Number(liability.value)) * 1e8) / 1e8,
    unit: asset.unit,
    currency: asset.currency,
    fact_level: asset.isReportTotal || liability.isReportTotal ? "report" : "scope",
    scope: asset.isReportTotal || liability.isReportTotal ? null : row.scope,
    page: null,
    raw_text: "衍生金融资产减衍生金融负债",
    isReportTotal: asset.isReportTotal || liability.isReportTotal,
    isComputed: true,
    value_verified: true,
    quote_verified: true
  };
}

export function displayMetric(metric) {
  if (!metric) return "未披露";
  if (metric.multipleCount && !metric.isAggregated) return `${metric.multipleCount} 项事实`;
  if (metric.value === null || metric.value === undefined || !Number.isFinite(Number(metric.value))) {
    return "未披露";
  }
  const value = Number(metric.value).toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2
  });
  return `${value}${metric.unit ? ` ${metric.unit}` : ""}`;
}

function planEventsFor(report, scope, events) {
  return events.filter((event) => {
    if (event.code !== report.code || Number(event.anchor_year) !== Number(report.fiscal_year)) return false;
    const scopes = asArray(event.scope);
    return scopes.includes(scope) || scopes.includes("综合") || scope === "未明确";
  });
}

export function buildPeriodicRows(payload, eventRows = []) {
  const reports = asArray(payload?.reports).filter((report) => report.status === "extracted");
  const profiles = new Map(asArray(payload?.profiles).map((profile) => [profile.report_id, profile]));
  const metricsByReport = new Map();
  asArray(payload?.metrics).filter(VERIFIED).forEach((metric) => {
    const bucket = metricsByReport.get(metric.report_id) || [];
    bucket.push(metric);
    metricsByReport.set(metric.report_id, bucket);
  });
  const accountingByReport = new Map();
  asArray(payload?.accountingItems).forEach((item) => {
    const bucket = accountingByReport.get(item.report_id) || [];
    bucket.push(item);
    accountingByReport.set(item.report_id, bucket);
  });
  const companyMetaByCode = new Map();
  eventRows.forEach((event) => {
    if (!companyMetaByCode.has(event.code)) {
      companyMetaByCode.set(event.code, {
        province: event.province || null,
        entType: event.ent_type || null,
        industry: event.ind_l1 || null
      });
    }
  });

  return reports.flatMap((report) => {
    const profile = profiles.get(report.report_id);
    if (!profile) return [];
    const scopes = unique(asArray(profile.scopes));
    const rowScopes = scopes.length ? scopes : ["未明确"];
    const verifiedMetrics = metricsByReport.get(report.report_id) || [];
    const accountingItems = accountingByReport.get(report.report_id) || [];
    const evidenceState = verifiedMetrics.length > 0 && (
      asArray(profile.evidence).length > 0
      || profile.hedge_accounting_quote_verified === true
      || accountingItems.some((item) => item.quote_verified === true)
    ) ? "完整" : "部分";

    return rowScopes.map((scope) => ({
      rowId: `${report.report_id}|${scope}`,
      report,
      profile,
      scope,
      verifiedMetrics,
      accountingItems,
      companyMeta: companyMetaByCode.get(report.code) || {
        province: null,
        entType: null,
        industry: null
      },
      planEvents: planEventsFor(report, scope, eventRows),
      hedgeAccountingStatus: profile.hedge_accounting_status || "未明确披露",
      hedgeAccountingTypes: asArray(profile.hedge_accounting_types),
      nonApplicationReason: profile.non_application_reason ?? null,
      evidenceState,
      matchStatus: "待口径核对"
    }));
  }).sort((left, right) => (
    Number(right.report.fiscal_year) - Number(left.report.fiscal_year)
    || String(left.report.code).localeCompare(String(right.report.code), "zh-CN")
    || String(left.scope).localeCompare(String(right.scope), "zh-CN")
  ));
}

export function filterPeriodicRows(rows, filters) {
  const query = String(filters?.query || "").trim().toLowerCase();
  return rows.filter((row) => {
    if (filters?.year && filters.year !== "all" && String(row.report.fiscal_year) !== String(filters.year)) return false;
    if (filters?.scope && filters.scope !== "all" && row.scope !== filters.scope) return false;
    if (filters?.accounting && filters.accounting !== "all" && row.hedgeAccountingStatus !== filters.accounting) return false;
    if (filters?.evidence && filters.evidence !== "all" && row.evidenceState !== filters.evidence) return false;
    if (!query) return true;
    const haystack = [
      row.report.name,
      row.report.code,
      row.scope,
      ...asArray(row.profile.instruments),
      ...asArray(row.profile.underlyings),
      row.companyMeta.province,
      row.companyMeta.industry
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(query);
  });
}

export function detailMetricsFor(row) {
  return row.verifiedMetrics.filter((item) => (
    item.fact_level === "report" || item.scope === row.scope
  ));
}

function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  if (typeof value === "string" && /^\s*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function metricExportParts(row, metricType) {
  const metric = metricFor(row, metricType);
  const hasValue = metric && hasFiniteMetricValue(metric.value);
  return [
    hasValue ? Number(metric.value) : "",
    hasValue ? metric.currency || "" : "",
    hasValue ? metric.unit || "" : "",
    metric?.multipleCount || (metric ? 1 : 0)
  ];
}

function planExportText(row) {
  return row.planEvents.flatMap((event) => asArray(event.quota)).map((item) => [
    item.scope || "综合",
    item.basis || "口径未披露",
    item.currency || "CNY",
    item.amount ?? "未披露"
  ].join(" / ")).join("；");
}

export function periodicRowsToCsv(rows) {
  const headers = [
    "报告期", "报告类型", "年度", "公司代码", "公司名称", "省份", "一级行业", "企业性质",
    "类别", "品种", "工具", "公告计划候选",
    "报告期购入", "购入币种", "购入单位", "购入事实数",
    "报告期售出", "售出币种", "售出单位", "售出事实数",
    "期末保证金", "保证金币种", "保证金单位", "保证金事实数",
    "衍生金融资产", "资产币种", "资产单位", "资产事实数",
    "衍生金融负债", "负债币种", "负债单位", "负债事实数",
    "公允价值净额", "净额币种", "净额单位", "净额事实数",
    "衍生品综合损益", "综合损益币种", "综合损益单位", "综合损益事实数",
    "处置投资收益", "投资收益币种", "投资收益单位", "投资收益事实数",
    "公允价值变动损益", "公允价值变动币种", "公允价值变动单位", "公允价值变动事实数",
    "套期会计状态", "套期会计方法", "未应用原因", "匹配状态", "证据状态", "年报原文"
  ];
  const body = asArray(rows).map((row) => [
    row.report.report_period || "",
    reportTypeLabel(row.report.report_type),
    row.report.fiscal_year ?? "",
    row.report.code || "",
    row.report.name || "",
    row.companyMeta.province || "",
    row.companyMeta.industry || "",
    row.companyMeta.entType || "",
    row.scope || "",
    unique(asArray(row.profile.underlyings)).join("、"),
    unique(asArray(row.profile.instruments)).join("、"),
    planExportText(row),
    ...metricExportParts(row, "period_purchase_amount"),
    ...metricExportParts(row, "period_sale_amount"),
    ...metricExportParts(row, "margin_end_cash"),
    ...metricExportParts(row, "derivative_asset_fv"),
    ...metricExportParts(row, "derivative_liability_fv"),
    ...metricExportParts(row, "derivative_net_fv"),
    ...metricExportParts(row, "reported_derivative_comprehensive_pnl"),
    ...metricExportParts(row, "derivative_disposal_investment_income"),
    ...metricExportParts(row, "derivative_fv_change_pnl"),
    row.hedgeAccountingStatus || "",
    row.hedgeAccountingTypes.join("、"),
    row.nonApplicationReason || "",
    row.matchStatus || "",
    row.evidenceState || "",
    row.report.pdf_url || ""
  ]);
  return `\uFEFF${[headers, ...body].map((line) => line.map(csvCell).join(",")).join("\r\n")}`;
}

function detailAccountingItemsFor(row) {
  return row.accountingItems.filter((item) => !item.scope || item.scope === row.scope);
}

function reportTypeLabel(value) {
  return {
    annual: "年度报告",
    semiannual: "半年度报告",
    quarterly: "季度报告"
  }[value] || value || "定期报告";
}

export function resolveYearFilter(years, currentValue) {
  const current = String(currentValue || "all");
  return current === "all" || years.map(String).includes(current) ? current : "all";
}

const browserState = {
  payload: null,
  rows: [],
  loadingPromise: null,
  filters: {
    query: "",
    year: "all",
    scope: "all",
    accounting: "all",
    evidence: "all"
  }
};

function planLabel(row) {
  const quotas = row.planEvents.flatMap((event) => asArray(event.quota));
  if (!quotas.length) return '<span class="metric-value">未匹配公告</span><span class="metric-note">待 M5 核对</span>';
  const first = quotas[0];
  const amount = first.amount === null || first.amount === undefined
    ? "额度未披露"
    : `${Number(first.amount).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} ${first.currency || "CNY"}`;
  return `<span class="metric-value">${escape(amount)}</span><span class="metric-note">${escape(first.basis || "口径未披露")}${quotas.length > 1 ? ` · 共 ${quotas.length} 项` : ""}</span>`;
}

function metricCell(row, type) {
  const metric = metricFor(row, type);
  const negative = metric && Number(metric.value) < 0 ? " is-negative" : "";
  const note = metric?.isAggregated
    ? `合计 · ${metric.multipleCount} 项`
    : metric?.isComputed
      ? "勾稽计算"
      : metric?.isReportTotal
        ? "报告级合计"
        : metric?.page
          ? `第 ${metric.page} 页`
          : "";
  return `<span class="metric-value${negative}">${escape(displayMetric(metric))}</span>${note ? `<span class="metric-note">${escape(note)}</span>` : ""}`;
}

function flowCell(row) {
  const purchase = metricFor(row, "period_purchase_amount");
  const sale = metricFor(row, "period_sale_amount");
  const purchaseNote = purchase?.isAggregated ? ` · 合计 ${purchase.multipleCount} 项` : "";
  const saleNote = sale?.isAggregated ? ` · 合计 ${sale.multipleCount} 项` : "";
  return `<span class="metric-value">购 ${escape(displayMetric(purchase))}${escape(purchaseNote)}</span><span class="metric-note">售 ${escape(displayMetric(sale))}${escape(saleNote)}</span>`;
}

function accountingBadge(row) {
  const status = row.hedgeAccountingStatus;
  const cls = status === "已应用" ? " periodic-status--applied" : status === "需复核" ? " periodic-status--review" : "";
  return `<span class="periodic-status${cls}">${escape(status)}</span>`;
}

function renderRows() {
  const rows = filterPeriodicRows(browserState.rows, browserState.filters);
  const body = document.querySelector("#periodic-body");
  document.querySelector("#periodic-result-count").textContent = `${rows.length.toLocaleString("zh-CN")} 行`;
  body.innerHTML = rows.length ? rows.map((row) => {
    const underlying = unique(asArray(row.profile.underlyings)).join("、") || "品种未披露";
    const methods = row.hedgeAccountingTypes.length ? row.hedgeAccountingTypes.join("、") : (
      row.hedgeAccountingStatus === "未应用" ? "不适用" : "未披露"
    );
    return `<tr class="data-row">
      <td><span class="cell-primary">${escape(row.report.report_period || row.report.fiscal_year)}</span><span class="cell-secondary">${escape(reportTypeLabel(row.report.report_type))}</span></td>
      <td class="company-cell"><span class="cell-primary">${escape(row.report.name || "未命名公司")}</span><span class="cell-secondary">${escape(row.report.code || "—")} · ${escape(row.companyMeta.industry || "行业未录入")}</span></td>
      <td><span class="cell-primary">${escape(row.scope)}</span><span class="cell-secondary">${escape(underlying)}</span></td>
      <td>${planLabel(row)}</td>
      <td>${flowCell(row)}</td>
      <td>${metricCell(row, "margin_end_cash")}</td>
      <td>${metricCell(row, "derivative_asset_fv")}</td>
      <td>${metricCell(row, "derivative_liability_fv")}</td>
      <td>${metricCell(row, "derivative_net_fv")}</td>
      <td>${metricCell(row, "reported_derivative_comprehensive_pnl")}</td>
      <td>${metricCell(row, "derivative_disposal_investment_income")}</td>
      <td>${metricCell(row, "derivative_fv_change_pnl")}</td>
      <td>${accountingBadge(row)}</td>
      <td><span class="cell-primary">${escape(methods)}</span>${row.nonApplicationReason ? `<span class="cell-secondary">${escape(row.nonApplicationReason)}</span>` : ""}</td>
      <td><span class="periodic-status periodic-status--review">${escape(row.matchStatus)}</span></td>
      <td><button class="periodic-evidence-button" type="button" data-periodic-row="${escape(row.rowId)}">${escape(row.evidenceState)} · 查看</button></td>
    </tr>`;
  }).join("") : '<tr class="empty-row"><td colspan="16">没有匹配的定期报告记录，请调整筛选条件。</td></tr>';
}

function renderSummary() {
  const reports = asArray(browserState.payload?.reports);
  const profiles = asArray(browserState.payload?.profiles);
  const metrics = asArray(browserState.payload?.metrics).filter(VERIFIED);
  document.querySelector("#periodic-report-count").textContent = reports.length.toLocaleString("zh-CN");
  document.querySelector("#periodic-company-count").textContent = new Set(reports.map((row) => row.code).filter(Boolean)).size.toLocaleString("zh-CN");
  document.querySelector("#periodic-metric-count").textContent = metrics.length.toLocaleString("zh-CN");
  document.querySelector("#periodic-accounting-count").textContent = profiles.filter((row) => row.hedge_accounting_status === "已应用").length.toLocaleString("zh-CN");
  document.querySelector("#nav-periodic-count").textContent = reports.length.toLocaleString("zh-CN");
  const years = unique(reports.map((row) => row.fiscal_year)).sort((a, b) => b - a);
  const yearFilter = document.querySelector("#periodic-year-filter");
  yearFilter.innerHTML = '<option value="all">全部</option>' + years.map((year) => `<option value="${escape(year)}">${escape(year)}</option>`).join("");
  browserState.filters.year = resolveYearFilter(years, browserState.filters.year);
  yearFilter.value = browserState.filters.year;
}

function renderDetail(row) {
  const shell = window.HedgeShell;
  shell.openDrawer(
    row.report.name || "未命名公司",
    `${row.report.code || "—"} · ${row.report.report_period || row.report.fiscal_year} · ${row.scope}`,
    "PERIODIC REPORT"
  );
  const metricItems = detailMetricsFor(row).map((item) => `<article class="quota-item">
    <div class="quota-item-head"><span>${escape(TYPE_LABELS[item.metric_type] || item.metric_type)}</span><strong>${escape(displayMetric(item))}</strong></div>
    <p>${escape(item.raw_text || "未保留原文")}</p>
    <div class="verification"><span class="tag tag--blue">数值已回验</span><span class="tag tag--blue">引文已回验</span>${item.page ? `<span class="tag">第 ${escape(item.page)} 页</span>` : ""}${item.fact_level === "report" ? '<span class="tag">报告级</span>' : ""}</div>
  </article>`).join("") || '<p class="drawer-empty">没有通过双回验的数值事实。</p>';
  const accountingItems = detailAccountingItemsFor(row).map((item) => `<article class="timeline-item">
    <div class="timeline-meta"><span>${escape(item.application_status || "未明确披露")}</span>${item.accounting_type ? `<span class="tag">${escape(item.accounting_type)}</span>` : ""}</div>
    <p>${escape(item.quote || "原文未披露")}</p>
    ${item.page ? `<span class="tag">第 ${escape(item.page)} 页</span>` : ""}
  </article>`).join("") || '<p class="drawer-empty">没有业务级套期会计明细。</p>';
  const pdf = shell.safeExternalUrl(row.report.pdf_url);
  document.querySelector("#drawer-content").innerHTML = `
    <section class="drawer-section">
      <div class="detail-grid">
        <div class="detail-card"><span>报告类型</span><strong>${escape(reportTypeLabel(row.report.report_type))}</strong></div>
        <div class="detail-card"><span>披露状态</span><strong>${escape(row.profile.disclosure_status || "未明确")}</strong></div>
        <div class="detail-card"><span>套期会计</span><strong>${escape(row.hedgeAccountingStatus)}</strong></div>
        <div class="detail-card"><span>证据状态</span><strong>${escape(row.evidenceState)}</strong></div>
      </div>
    </section>
    <section class="drawer-section">
      <h3 class="drawer-section-title">业务摘要</h3>
      <p class="drawer-empty">${escape(row.profile.summary || "未披露摘要")}</p>
      <div class="detail-line"><span>工具</span><strong>${escape(unique(asArray(row.profile.instruments)).join("、") || "未披露")}</strong></div>
      <div class="detail-line"><span>品种</span><strong>${escape(unique(asArray(row.profile.underlyings)).join("、") || "未披露")}</strong></div>
      <div class="detail-line"><span>公告计划</span><strong>${escape(row.planEvents.length ? `${row.planEvents.length} 个候选事件，待 M5 核对` : "未匹配")}</strong></div>
      ${pdf ? `<a class="source-link" href="${escape(pdf)}" target="_blank" rel="noopener noreferrer">打开年报原文 ↗</a>` : ""}
    </section>
    <section class="drawer-section"><h3 class="drawer-section-title">已回验数值事实</h3><div class="quota-list">${metricItems}</div></section>
    <section class="drawer-section"><h3 class="drawer-section-title">套期会计证据</h3><div class="timeline">${accountingItems}</div></section>
    <section class="drawer-section"><h3 class="drawer-section-title">核对状态</h3><p class="drawer-empty">当前版本展示公告计划候选项与年报实际事实；自动品种、模式和数值口径匹配将在 M5 启用。</p></section>`;
}

function escape(value) {
  if (typeof window !== "undefined" && window.HedgeShell?.escapeHtml) {
    return window.HedgeShell.escapeHtml(value);
  }
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function loadPayload() {
  const shell = window.HedgeShell;
  if (!shell?.apiAll) throw new Error("页面数据客户端尚未就绪");
  const fields = {
    reports: "report_id,code,name,title,report_type,report_period,fiscal_year,period_end,publish_date,pdf_url,status",
    profiles: "report_id,disclosure_status,scopes,instruments,underlyings,purpose,summary,evidence,review_status,hedge_accounting_status,hedge_accounting_types,non_application_reason,hedge_accounting_page,hedge_accounting_quote,hedge_accounting_quote_verified",
    metrics: "id,report_id,metric_type,fact_level,scope,underlying,value,currency,unit,time_basis,source_section,account_name,is_restricted,counterparty,raw_text,page,value_verified,quote_verified",
    accounting: "id,report_id,scope,instrument,underlying_asset,application_status,accounting_type,non_application_reason,source_section,page,quote,quote_verified,confidence,need_review"
  };
  const [reports, profiles, metrics, accountingItems] = await Promise.all([
    shell.apiAll("periodic_reports", { select: fields.reports, status: "eq.extracted", order: "fiscal_year.desc,code.asc" }),
    shell.apiAll("periodic_derivatives", { select: fields.profiles, order: "report_id.asc" }),
    shell.apiAll("periodic_metric_items", { select: fields.metrics, value_verified: "eq.true", quote_verified: "eq.true", order: "report_id.asc,id.asc" }),
    shell.apiAll("periodic_hedge_accounting_items", { select: fields.accounting, order: "report_id.asc,id.asc" })
  ]);
  return { reports, profiles, metrics, accountingItems };
}

async function activate() {
  if (browserState.payload) {
    renderRows();
    return;
  }
  if (browserState.loadingPromise) return browserState.loadingPromise;
  const loading = document.querySelector("#periodic-loading");
  const error = document.querySelector("#periodic-error");
  const table = document.querySelector("#periodic-table-wrap");
  loading.hidden = false;
  error.hidden = true;
  table.hidden = true;
  browserState.loadingPromise = (async () => {
    try {
      browserState.payload = await loadPayload();
      browserState.rows = buildPeriodicRows(browserState.payload, window.HedgeShell.events());
      renderSummary();
      renderRows();
      table.hidden = false;
    } catch (loadError) {
      error.hidden = false;
      document.querySelector("#periodic-error-message").textContent = loadError?.message || "定期报告数据读取失败";
      throw loadError;
    } finally {
      loading.hidden = true;
      browserState.loadingPromise = null;
    }
  })();
  return browserState.loadingPromise;
}

async function refresh() {
  browserState.payload = null;
  browserState.rows = [];
  return activate();
}

function bindBrowserEvents() {
  const bindings = [
    ["#periodic-search", "input", "query"],
    ["#periodic-year-filter", "change", "year"],
    ["#periodic-scope-filter", "change", "scope"],
    ["#periodic-accounting-filter", "change", "accounting"],
    ["#periodic-evidence-filter", "change", "evidence"]
  ];
  bindings.forEach(([selector, eventName, key]) => {
    document.querySelector(selector)?.addEventListener(eventName, (event) => {
      browserState.filters[key] = event.target.value;
      renderRows();
    });
  });
  document.querySelector("#periodic-body")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-periodic-row]");
    if (!button) return;
    const row = browserState.rows.find((candidate) => candidate.rowId === button.dataset.periodicRow);
    if (row) renderDetail(row);
  });
  document.querySelector("#periodic-export-button")?.addEventListener("click", () => {
    const rows = filterPeriodicRows(browserState.rows, browserState.filters);
    const shell = window.HedgeShell;
    if (!rows.length) {
      shell?.showToast("当前筛选没有可导出的定期报告数据");
      return;
    }
    const blob = new Blob([periodicRowsToCsv(rows)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const date = new Date().toISOString().slice(0, 10);
    link.href = href;
    link.download = `hedge-periodic-actuals-${date}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    shell?.showToast(`已导出 ${rows.length.toLocaleString("zh-CN")} 条定期报告结果`);
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.HedgePeriodic = Object.freeze({ activate, refresh });
  bindBrowserEvents();
}
