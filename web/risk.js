const RISK_LABELS = {
  loss: "重大衍生品损失",
  margin_liquidity: "保证金与流动性风险",
  unauthorized: "超授权或未经授权开展",
  speculation: "偏离套保目的/投机化",
  regulatory: "监管整改/处罚/追责",
  internal_control: "审批或内控缺陷",
  disclosure: "衍生品会计与信息披露违规",
  other: "其他衍生品风险",
};

const SOURCE_LABELS = {
  SSE: "上海证券交易所",
  SZSE: "深圳证券交易所",
  CSRC: "中国证监会",
  CSRC_BUREAU: "证监会派出机构",
  CNINFO: "巨潮资讯",
  OTHER_OFFICIAL: "其他官方来源",
};

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function dateValue(value) {
  const text = String(value || "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : "";
}

function riskLabel(value) {
  return RISK_LABELS[value] || value || "其他衍生品风险";
}

function sourceLabel(value) {
  return SOURCE_LABELS[value] || value || "未披露来源";
}

function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function normalizeOfficialCase(row, payload) {
  const relations = asArray(payload.documents).filter((item) => item.case_key === row.case_key);
  const sourceById = new Map(asArray(payload.sourceDocuments).map((item) => [item.source_doc_id, item]));
  const documents = relations.map((relation) => {
    const source = sourceById.get(relation.source_doc_id) || {};
    return {
      id: relation.source_doc_id,
      date: dateValue(source.publish_date),
      type: relation.relation_type || source.source_type || "official",
      title: source.title || "官方文档",
      sourceOrg: sourceLabel(source.source_org),
      url: source.document_url || "",
    };
  }).sort((a, b) => a.date.localeCompare(b.date));
  const evidence = asArray(payload.evidence)
    .filter((item) => item.case_key === row.case_key)
    .map((item) => ({
      id: item.id,
      field: item.field,
      page: item.page,
      quote: item.quote,
      value: item.extracted_value,
      url: item.source_url,
      verified: item.quote_verified === true && item.value_verified === true,
      sourceTitle: sourceById.get(item.source_doc_id)?.title || "官方证据",
    }));
  return {
    id: row.case_key,
    officialCaseKey: row.case_key,
    evidenceLevel: "official_verified",
    verificationStatus: "官方证据",
    date: dateValue(row.event_date || row.first_disclosure_date),
    company: row.company_name || "未命名公司",
    code: row.code || "",
    riskTypes: [riskLabel(row.risk_type)],
    instruments: asArray(row.instruments),
    underlyings: asArray(row.underlyings),
    amount: row.amount,
    currency: row.currency,
    unit: row.unit,
    regulatoryAction: row.regulatory_action || "未披露",
    outcome: row.outcome || "未披露",
    sourceOrg: documents[0]?.sourceOrg || "官方来源",
    status: row.case_status || "待复核",
    summary: row.summary || "暂无摘要",
    documents,
    evidence,
  };
}

function normalizeMediaReport(row, payload) {
  const sources = asArray(payload.sources)
    .filter((item) => item.media_key === row.media_key)
    .map((item) => ({
      id: item.source_key,
      date: dateValue(item.published_at),
      type: "媒体报道",
      title: item.title || "媒体报道",
      sourceOrg: item.publisher_name || item.source_domain || "具名媒体",
      url: item.url || "",
      excerpt: item.short_excerpt || "",
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
  return {
    id: row.media_key,
    officialCaseKey: row.official_case_key || null,
    evidenceLevel: "media_unverified",
    verificationStatus: "媒体报道／未核实",
    date: dateValue(row.event_date),
    company: row.company_name || "未命名公司",
    code: row.code || "",
    riskTypes: [riskLabel(row.risk_type)],
    instruments: asArray(row.instruments),
    underlyings: asArray(row.underlyings),
    amount: null,
    currency: null,
    unit: null,
    regulatoryAction: "尚未找到官方监管文件",
    outcome: "等待官方文件或公司公告交叉核实",
    sourceOrg: sources[0]?.sourceOrg || "具名媒体",
    status: "媒体报道／未核实",
    summary: row.summary || sources[0]?.excerpt || "暂无摘要",
    documents: sources,
    evidence: [],
  };
}

function sameLikelyEvent(media, official) {
  if (media.officialCaseKey && media.officialCaseKey === official.id) return true;
  if (!media.date || !official.date || media.code !== official.code) return false;
  if (!media.riskTypes.some((type) => official.riskTypes.includes(type))) return false;
  const gap = Math.abs(new Date(media.date).getTime() - new Date(official.date).getTime());
  return gap <= 14 * 86400000;
}

export function buildRiskRows(payload = {}) {
  const official = asArray(payload.cases).map((row) => normalizeOfficialCase(row, payload));
  const media = asArray(payload.reports)
    .filter((row) => ["published", "corroborated"].includes(row.publish_status))
    .map((row) => normalizeMediaReport(row, payload))
    .filter((row) => !official.some((item) => sameLikelyEvent(row, item)));
  return [...official, ...media].sort((a, b) => (
    b.date.localeCompare(a.date) || a.company.localeCompare(b.company, "zh-CN")
  ));
}

export function filterRiskRows(rows, filters = {}) {
  const query = String(filters.search || "").trim().toLowerCase();
  return asArray(rows).filter((row) => {
    const searchable = [
      row.company, row.code, row.summary, row.sourceOrg,
      ...row.riskTypes, ...row.instruments, ...row.underlyings,
    ].join(" ").toLowerCase();
    return (!query || searchable.includes(query))
      && (!filters.year || filters.year === "all" || row.date.slice(0, 4) === filters.year)
      && (!filters.riskType || filters.riskType === "all" || row.riskTypes.includes(filters.riskType))
      && (!filters.source || filters.source === "all" || row.sourceOrg === filters.source)
      && (!filters.status || filters.status === "all" || row.status === filters.status)
      && (!filters.evidence || filters.evidence === "all" || row.evidenceLevel === filters.evidence);
  });
}

export function summarizeRiskRows(rows) {
  return {
    official: rows.filter((row) => row.evidenceLevel === "official_verified").length,
    media: rows.filter((row) => row.evidenceLevel === "media_unverified").length,
    companies: new Set(rows.map((row) => row.code).filter(Boolean)).size,
    loss: rows.filter((row) => row.riskTypes.includes("重大衍生品损失")).length,
  };
}

export function riskRowsToCsv(rows) {
  const headers = [
    "事件日期", "股票代码", "公司", "风险类型", "工具", "品种", "证据层级",
    "状态", "来源", "摘要", "金额", "币种", "单位", "监管措施", "处理结果", "来源链接",
  ];
  const body = rows.map((row) => [
    row.date, row.code, row.company, row.riskTypes.join(" / "), row.instruments.join(" / "),
    row.underlyings.join(" / "), row.verificationStatus, row.status, row.sourceOrg,
    row.summary, row.amount, row.currency, row.unit, row.regulatoryAction, row.outcome,
    row.documents.map((item) => item.url).filter(Boolean).join(" "),
  ]);
  return `\uFEFF${[headers, ...body].map((line) => line.map(csvCell).join(",")).join("\r\n")}`;
}

const browserState = {
  rows: [],
  payload: null,
  loadingPromise: null,
  filters: { search: "", year: "all", riskType: "all", source: "all", status: "all", evidence: "all" },
};

function escapeHtml(value) {
  if (typeof window !== "undefined" && window.HedgeShell?.escapeHtml) return window.HedgeShell.escapeHtml(value);
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function renderBadges(values) {
  return values.length ? values.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("") : '<span class="cell-secondary">未披露</span>';
}

function displayAmount(row) {
  if (row.amount === null || row.amount === undefined) return "未披露";
  return `${row.currency || ""} ${Number(row.amount).toLocaleString("zh-CN")} ${row.unit || ""}`.trim();
}

function renderTableRow(row) {
  const levelClass = row.evidenceLevel === "official_verified" ? "risk-level--official" : "risk-level--media";
  return `<tr class="data-row" tabindex="0" data-risk-row="${escapeHtml(row.id)}">
    <td data-label="事件日期"><span class="cell-primary">${escapeHtml(row.date || "—")}</span></td>
    <td class="company-cell" data-label="公司"><span class="cell-primary">${escapeHtml(row.company)}</span><span class="cell-secondary">${escapeHtml(row.code || "—")}</span></td>
    <td data-label="风险类型"><div class="tag-list">${renderBadges(row.riskTypes)}</div></td>
    <td data-label="工具 / 品种"><span class="cell-primary">${escapeHtml(unique([...row.underlyings, ...row.instruments]).join("、") || "未披露")}</span></td>
    <td data-label="证据层级"><span class="risk-level ${levelClass}">${escapeHtml(row.verificationStatus)}</span></td>
    <td data-label="状态"><span class="cell-primary">${escapeHtml(row.status)}</span></td>
    <td data-label="来源"><span class="cell-primary">${escapeHtml(row.sourceOrg)}</span><span class="cell-secondary">${row.documents.length} 个来源</span></td>
    <td data-label="详情"><button class="periodic-evidence-button" type="button" data-risk-row="${escapeHtml(row.id)}">查看详情</button></td>
  </tr>`;
}

function renderDetail(row) {
  const shell = window.HedgeShell;
  shell.openDrawer(row.company, `${row.code || "—"} · ${row.date || "—"}`, "RISK CASE");
  const documents = row.documents.length ? row.documents.map((item) => {
    const url = shell.safeExternalUrl(item.url);
    return `<article class="timeline-item"><div class="timeline-meta"><span>${escapeHtml(item.date || "—")}</span><span class="tag">${escapeHtml(item.type)}</span></div><h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.excerpt || item.sourceOrg)}</p>${url ? `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : ""}</article>`;
  }).join("") : '<p class="drawer-empty">暂无来源文档。</p>';
  const evidence = row.evidence.length ? row.evidence.map((item) => `<blockquote class="evidence-quote"><small>${escapeHtml(item.field || "证据")} · 第 ${escapeHtml(item.page || "—")} 页${item.verified ? " · 已回验" : ""}</small>${escapeHtml(item.quote || "未提供引文")}</blockquote>`).join("") : '<p class="drawer-empty">媒体记录尚无官方逐字段证据。</p>';
  document.querySelector("#drawer-content").innerHTML = `
    <section class="drawer-section"><div class="detail-grid">
      <div class="detail-card"><span>证据层级</span><strong>${escapeHtml(row.verificationStatus)}</strong></div>
      <div class="detail-card"><span>风险状态</span><strong>${escapeHtml(row.status)}</strong></div>
      <div class="detail-card"><span>金额</span><strong>${escapeHtml(displayAmount(row))}</strong></div>
      <div class="detail-card"><span>来源</span><strong>${escapeHtml(row.sourceOrg)}</strong></div>
    </div></section>
    <section class="drawer-section"><h3 class="drawer-section-title">事件摘要</h3><p class="drawer-empty">${escapeHtml(row.summary)}</p>
      <div class="detail-line"><span>风险类型</span><strong>${escapeHtml(row.riskTypes.join(" / "))}</strong></div>
      <div class="detail-line"><span>工具与品种</span><strong>${escapeHtml(unique([...row.instruments, ...row.underlyings]).join(" / ") || "未披露")}</strong></div>
      <div class="detail-line"><span>监管措施</span><strong>${escapeHtml(row.regulatoryAction)}</strong></div>
      <div class="detail-line"><span>处理结果</span><strong>${escapeHtml(row.outcome)}</strong></div>
    </section>
    <section class="drawer-section"><h3 class="drawer-section-title">来源文档</h3><div class="timeline">${documents}</div></section>
    <section class="drawer-section"><h3 class="drawer-section-title">逐字段证据</h3>${evidence}</section>`;
}

function fillSelect(selector, values) {
  const select = document.querySelector(selector);
  if (!select) return;
  const current = select.value || "all";
  select.innerHTML = '<option value="all">全部</option>' + values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = values.includes(current) ? current : "all";
}

function renderBrowser() {
  const rows = filterRiskRows(browserState.rows, browserState.filters);
  const metrics = summarizeRiskRows(browserState.rows);
  document.querySelector("#risk-official-count").textContent = metrics.official.toLocaleString("zh-CN");
  document.querySelector("#risk-media-count").textContent = metrics.media.toLocaleString("zh-CN");
  document.querySelector("#risk-company-count").textContent = metrics.companies.toLocaleString("zh-CN");
  document.querySelector("#risk-loss-count").textContent = metrics.loss.toLocaleString("zh-CN");
  document.querySelector("#nav-risk-count").textContent = browserState.rows.length.toLocaleString("zh-CN");
  document.querySelector("#risk-result-count").textContent = `${rows.length.toLocaleString("zh-CN")} 条风险记录`;
  document.querySelector("#risk-body").innerHTML = rows.map(renderTableRow).join("");
  document.querySelector("#risk-table-wrap").hidden = rows.length === 0;
  document.querySelector("#risk-empty").hidden = rows.length !== 0;
}

async function loadPayload() {
  const apiAll = window.HedgeShell.apiAll;
  const [cases, sourceDocuments, documents, evidence, reports, sources] = await Promise.all([
    apiAll("derivative_risk_cases", { select: "case_key,code,company_name,event_date,first_disclosure_date,risk_type,instruments,underlyings,summary,amount,currency,unit,regulatory_action,outcome,case_status", order: "event_date.desc.nullslast,case_key.asc" }),
    apiAll("risk_source_documents", { select: "source_doc_id,source_org,source_type,title,publish_date,document_url", order: "publish_date.desc.nullslast,source_doc_id.asc" }),
    apiAll("risk_case_documents", { select: "case_key,source_doc_id,relation_type", order: "case_key.asc,source_doc_id.asc" }),
    apiAll("risk_case_evidence", { select: "id,case_key,source_doc_id,field,page,quote,extracted_value,source_url,quote_verified,value_verified", order: "case_key.asc,id.asc" }),
    apiAll("risk_media_reports", { select: "media_key,code,company_name,event_date,risk_type,instruments,underlyings,summary,verification_status,official_case_key,publish_status", publish_status: "in.(published,corroborated)", order: "event_date.desc,media_key.asc" }),
    apiAll("risk_media_report_sources", { select: "source_key,media_key,publisher_name,source_domain,title,published_at,url,short_excerpt,matched_derivative_terms,matched_risk_terms", order: "published_at.desc,source_key.asc" }),
  ]);
  return { cases, sourceDocuments, documents, evidence, reports, sources };
}

export async function activate() {
  if (browserState.payload) {
    renderBrowser();
    return browserState.rows;
  }
  if (browserState.loadingPromise) return browserState.loadingPromise;
  const loading = document.querySelector("#risk-loading");
  const error = document.querySelector("#risk-error");
  loading.hidden = false;
  error.hidden = true;
  browserState.loadingPromise = (async () => {
    try {
      browserState.payload = await loadPayload();
      browserState.rows = buildRiskRows(browserState.payload);
      fillSelect("#risk-year-filter", unique(browserState.rows.map((row) => row.date.slice(0, 4))).sort().reverse());
      fillSelect("#risk-type-filter", unique(browserState.rows.flatMap((row) => row.riskTypes)).sort((a, b) => a.localeCompare(b, "zh-CN")));
      fillSelect("#risk-source-filter", unique(browserState.rows.map((row) => row.sourceOrg).sort((a, b) => a.localeCompare(b, "zh-CN"))));
      fillSelect("#risk-status-filter", unique(browserState.rows.map((row) => row.status).sort((a, b) => a.localeCompare(b, "zh-CN"))));
      renderBrowser();
      return browserState.rows;
    } catch (loadError) {
      error.hidden = false;
      document.querySelector("#risk-error-message").textContent = loadError?.message || "风险案例数据读取失败";
      throw loadError;
    } finally {
      loading.hidden = true;
      browserState.loadingPromise = null;
    }
  })();
  return browserState.loadingPromise;
}

export async function refresh() {
  browserState.payload = null;
  browserState.rows = [];
  return activate();
}

function bindBrowserEvents() {
  const bindings = [
    ["#risk-search", "input", "search"],
    ["#risk-year-filter", "change", "year"],
    ["#risk-type-filter", "change", "riskType"],
    ["#risk-source-filter", "change", "source"],
    ["#risk-status-filter", "change", "status"],
    ["#risk-evidence-filter", "change", "evidence"],
  ];
  bindings.forEach(([selector, eventName, key]) => document.querySelector(selector)?.addEventListener(eventName, (event) => {
    browserState.filters[key] = event.target.value;
    renderBrowser();
  }));
  document.querySelector("#risk-body")?.addEventListener("click", (event) => {
    const target = event.target.closest("[data-risk-row]");
    const row = browserState.rows.find((item) => item.id === target?.dataset.riskRow);
    if (row) renderDetail(row);
  });
  document.querySelector("#risk-export-button")?.addEventListener("click", () => {
    const rows = filterRiskRows(browserState.rows, browserState.filters);
    if (!rows.length) return window.HedgeShell.showToast("当前筛选没有可导出的风险记录");
    const blob = new Blob([riskRowsToCsv(rows)], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `hedge-risk-cases-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    window.HedgeShell.showToast(`已导出 ${rows.length.toLocaleString("zh-CN")} 条风险记录`);
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  window.HedgeRisk = Object.freeze({ activate, refresh });
  bindBrowserEvents();
}
