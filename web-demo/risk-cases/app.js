const riskCaseRows = globalThis.riskCaseRows || [];

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayAmount(value, currency, unit) {
  if (value === null || value === undefined || value === "") return "未披露";
  const suffix = [unit, currency].filter(Boolean).join(" · ");
  return `${numberFormatter.format(value)}${suffix ? ` ${suffix}` : ""}`;
}

function sortDocuments(documents = []) {
  return [...documents].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
}

function filterCases(rows, filters = {}) {
  const {
    year = "all",
    riskType = "all",
    sourceOrg = "all",
    caseStatus = "all",
    evidenceLevel = "all",
    search = "",
  } = filters;
  const query = String(search).trim().toLocaleLowerCase("zh-CN");

  return rows
    .filter((row) => {
      if (year !== "all" && !String(row.date).startsWith(`${year}-`)) return false;
      if (riskType !== "all" && !(row.riskTypes || []).includes(riskType)) return false;
      if (sourceOrg !== "all" && row.sourceOrg !== sourceOrg) return false;
      if (caseStatus !== "all" && row.status !== caseStatus) return false;
      if (evidenceLevel !== "all" && row.evidenceLevel !== evidenceLevel) return false;
      if (!query) return true;
      const haystack = [
        row.company,
        row.code,
        row.province,
        row.industry,
        row.summary,
        row.regulatoryAction,
        row.outcome,
        row.sourceOrg,
        row.publisherName,
        row.sourceDomain,
        row.verificationStatus,
        ...(row.riskTypes || []),
        ...(row.instruments || []),
        ...(row.underlyings || []),
      ].join(" ").toLocaleLowerCase("zh-CN");
      return haystack.includes(query);
    })
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));
}

function csvCell(value) {
  const text = String(value ?? "").replaceAll('"', '""');
  return /[",\r\n]/.test(text) ? `"${text}"` : text;
}

function casesToCsv(rows) {
  const headers = [
    "案例键", "事件日期", "公司名称", "证券代码", "省份", "行业", "风险类型",
    "工具", "品种", "金额", "币种", "单位", "监管措施", "处理结果", "来源机构",
    "案例状态", "证据级别", "核实状态", "来源名称", "来源日期", "来源URL",
    "事实摘要", "官方文档标题", "官方文档日期", "官方URL", "证据状态",
  ];
  const body = rows.map((row) => {
    const documents = sortDocuments(row.documents || []);
    const verified = (row.evidence || []).filter((item) => item.verified).length;
    return [
      row.caseKey,
      row.date,
      row.company,
      row.code,
      row.province,
      row.industry,
      row.riskTypes.join(" / "),
      row.instruments.join(" / "),
      row.underlyings.join(" / "),
      row.amount,
      row.currency,
      row.unit,
      row.regulatoryAction,
      row.outcome,
      row.sourceOrg,
      row.status,
      evidenceLevelLabel(row),
      row.verificationStatus,
      row.publisherName || row.sourceOrg,
      row.sourceDate || documents[0]?.date || row.date,
      row.sourceUrl || documents.map((item) => item.url).join(" | "),
      row.summary,
      documents.map((item) => item.title).join(" | "),
      documents.map((item) => item.date).join(" | "),
      documents.map((item) => item.url).join(" | "),
      row.evidenceLevel === "media_unverified"
        ? "尚未找到官方依据"
        : `${verified}/${(row.evidence || []).length} 已回验`,
    ].map(csvCell).join(",");
  });
  return `\uFEFF${[headers.join(","), ...body].join("\r\n")}`;
}

function badgeTone(label) {
  if (["已结案", "已回验"].includes(label)) return "badge--green";
  if (["整改中", "持续披露", "媒体报道／未核实", "媒体未核实"].includes(label)) return "badge--amber";
  if (label === "官方文件／已核实") return "badge--green";
  if (["重大衍生品损失", "保证金与流动性风险", "超授权或未经授权开展"].includes(label)) return "badge--red";
  if (["纪律处分", "行政监管措施"].some((term) => String(label).includes(term))) return "badge--blue";
  return "";
}

function renderBadge(label, toneSource = label) {
  return `<span class="badge ${badgeTone(toneSource)}">${escapeHtml(label)}</span>`;
}

function evidenceLevelLabel(row) {
  return row.evidenceLevel === "media_unverified"
    ? "媒体报道／未核实"
    : "官方文件／已核实";
}

function evidenceProgress(row) {
  const total = row.evidence?.length || 0;
  const verified = (row.evidence || []).filter((item) => item.verified).length;
  return `${verified}/${total}`;
}

function renderTableRow(row) {
  return `
    <tr>
      <td><strong class="date-cell">${escapeHtml(row.date)}</strong></td>
      <td><div class="company-cell"><strong>${escapeHtml(row.company)}</strong><span>${escapeHtml(row.code)} · ${escapeHtml(row.province)}</span></div></td>
      <td><div class="badge-stack">${row.riskTypes.map((item) => renderBadge(item)).join("")}</div></td>
      <td><div class="stack"><strong>${escapeHtml((row.instruments || []).join(" / "))}</strong><small>${escapeHtml((row.underlyings || []).join(" / "))}</small></div></td>
      <td><strong class="amount-cell">${escapeHtml(displayAmount(row.amount, row.currency, row.unit))}</strong></td>
      <td><span>${escapeHtml(row.regulatoryAction)}</span></td>
      <td><span>${escapeHtml(row.outcome)}</span></td>
      <td><div class="stack"><strong>${escapeHtml(row.sourceOrg)}</strong><small>${escapeHtml(row.industry)}</small></div></td>
      <td>${renderBadge(row.status)}</td>
      <td><div class="evidence-cell">${renderBadge(evidenceLevelLabel(row))}<button class="detail-button" type="button" data-case-id="${escapeHtml(row.id)}">查看</button></div></td>
    </tr>`;
}

function renderDetailItems(items) {
  return items.map(([label, value]) => `
    <div class="detail-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("");
}

function renderDrawer(row) {
  if (row.evidenceLevel === "media_unverified") {
    return `
      <div class="drawer-kicker">固定演示数据 · ${escapeHtml(evidenceLevelLabel(row))}</div>
      <section class="detail-section">
        <header><h3>事件事实</h3><span>${escapeHtml(row.caseKey)}</span></header>
        <p class="case-summary">${escapeHtml(row.summary)}</p>
        <div class="detail-grid">${renderDetailItems([
          ["事件日期", row.date],
          ["风险类型", (row.riskTypes || []).join(" / ")],
          ["工具与品种", `${(row.instruments || []).join(" / ")} · ${(row.underlyings || []).join(" / ")}`],
          ["核实状态", row.verificationStatus],
        ])}</div>
      </section>
      <section class="detail-section">
        <header><h3>媒体来源</h3><span>${escapeHtml(row.sourceDomain)}</span></header>
        <article class="source-card">
          <div><strong>${escapeHtml(row.publisherName)}</strong><time>${escapeHtml(row.sourceDate)}</time></div>
          <p>${escapeHtml(row.shortExcerpt)}</p>
          <a href="${escapeHtml(row.sourceUrl)}" target="_blank" rel="noreferrer">打开来源链接 ↗</a>
        </article>
        <div class="verification-note"><strong>尚未找到官方依据</strong><span>该记录不计入正式案例，等待监管文件或公司公告交叉核实。</span></div>
      </section>`;
  }
  const documents = sortDocuments(row.documents).map((item, index) => `
    <li class="document-item">
      <div class="timeline-marker"><span>${index + 1}</span></div>
      <div class="document-copy">
        <div><time>${escapeHtml(item.date)}</time>${renderBadge(item.type, item.type)}</div>
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.sourceOrg)}</span>
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开演示链接 ↗</a>
      </div>
    </li>`).join("");
  const evidence = row.evidence.map((item) => `
    <article class="evidence-row">
      <div><strong>${escapeHtml(item.field)}</strong><span>P${escapeHtml(item.page)}</span></div>
      <p>${escapeHtml(item.quote)}</p>
      <footer><span>${escapeHtml(item.sourceTitle)}</span>${renderBadge(item.verified ? "已回验" : "待复核")}</footer>
    </article>`).join("");

  return `
    <div class="drawer-kicker">固定演示数据 · 非真实案例</div>
    <section class="detail-section">
      <header><h3>事件事实</h3><span>${escapeHtml(row.caseKey)}</span></header>
      <p class="case-summary">${escapeHtml(row.summary)}</p>
      <div class="detail-grid">${renderDetailItems([
        ["事件日期", row.date],
        ["风险类型", row.riskTypes.join(" / ")],
        ["工具与品种", `${row.instruments.join(" / ")} · ${row.underlyings.join(" / ")}`],
        ["损失或涉案金额", displayAmount(row.amount, row.currency, row.unit)],
        ["监管措施", row.regulatoryAction],
        ["处理结果", row.outcome],
      ])}</div>
    </section>
    <section class="detail-section">
      <header><h3>监管文档链</h3><span>${row.documents.length} 份文档</span></header>
      <ol class="document-timeline">${documents}</ol>
    </section>
    <section class="detail-section">
      <header><h3>逐字段证据</h3><span>${escapeHtml(evidenceProgress(row))} 已回验</span></header>
      <div class="evidence-list">${evidence}</div>
    </section>`;
}

function summarizeRows(rows) {
  return {
    official: rows.filter((row) => row.evidenceLevel === "official_verified").length,
    media: rows.filter((row) => row.evidenceLevel === "media_unverified").length,
    companies: new Set(rows.map((row) => row.code).filter(Boolean)).size,
    loss: rows.filter((row) => (row.riskTypes || []).includes("重大衍生品损失")).length,
  };
}

globalThis.RiskCasesDemo = {
  casesToCsv,
  displayAmount,
  filterCases,
  renderDrawer,
  renderTableRow,
  sortDocuments,
  summarizeRows,
};

if (typeof document !== "undefined") {
  const $ = (selector) => document.querySelector(selector);
  const state = { rows: riskCaseRows, filtered: riskCaseRows };

  function uniqueValues(mapper) {
    return [...new Set(riskCaseRows.flatMap(mapper).filter(Boolean))].sort((a, b) => String(b).localeCompare(String(a), "zh-CN"));
  }

  function fillSelect(selector, values) {
    const select = $(selector);
    if (!select) return;
    select.insertAdjacentHTML("beforeend", values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join(""));
  }

  function currentFilters() {
    return {
      search: $("#search-input").value,
      year: $("#year-filter").value,
      riskType: $("#risk-filter").value,
      sourceOrg: $("#source-filter").value,
      caseStatus: $("#status-filter").value,
      evidenceLevel: $("#evidence-filter").value,
    };
  }

  function renderMetrics() {
    const metrics = summarizeRows(riskCaseRows);
    $("#metric-official").textContent = metrics.official.toLocaleString("zh-CN");
    $("#metric-media").textContent = metrics.media.toLocaleString("zh-CN");
    $("#metric-companies").textContent = metrics.companies.toLocaleString("zh-CN");
    $("#metric-loss").textContent = metrics.loss.toLocaleString("zh-CN");
  }

  function render() {
    state.filtered = filterCases(state.rows, currentFilters());
    $("#result-count").textContent = state.filtered.length.toLocaleString("zh-CN");
    $("#cases-body").innerHTML = state.filtered.map(renderTableRow).join("");
    $("#empty-state").hidden = state.filtered.length > 0;
    $("#table-scroll").hidden = state.filtered.length === 0;
  }

  function openDrawer(row) {
    $("#drawer-title").textContent = row.company;
    $("#drawer-subtitle").textContent = `${row.date} · ${row.riskTypes.join(" / ")}`;
    $("#drawer-content").innerHTML = renderDrawer(row);
    $("#drawer-overlay").hidden = false;
    $("#detail-drawer").classList.add("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
  }

  function closeDrawer() {
    $("#detail-drawer").classList.remove("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
    $("#drawer-overlay").hidden = true;
    document.body.classList.remove("drawer-open");
  }

  function resetFilters() {
    $("#search-input").value = "";
    ["#year-filter", "#risk-filter", "#source-filter", "#status-filter", "#evidence-filter"].forEach((selector) => { $(selector).value = "all"; });
    render();
  }

  function exportResults() {
    const blob = new Blob([casesToCsv(state.filtered)], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "risk-cases-demo.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  document.addEventListener("DOMContentLoaded", () => {
    fillSelect("#year-filter", uniqueValues((row) => [row.date.slice(0, 4)]));
    fillSelect("#risk-filter", uniqueValues((row) => row.riskTypes));
    fillSelect("#source-filter", uniqueValues((row) => [row.sourceOrg]));
    fillSelect("#status-filter", uniqueValues((row) => [row.status]));
    renderMetrics();
    render();

    $("#search-input").addEventListener("input", render);
    ["#year-filter", "#risk-filter", "#source-filter", "#status-filter", "#evidence-filter"].forEach((selector) => $(selector).addEventListener("change", render));
    $("#reset-filters").addEventListener("click", resetFilters);
    $("#export-button").addEventListener("click", exportResults);
    $("#cases-body").addEventListener("click", (event) => {
      const button = event.target.closest("[data-case-id]");
      if (!button) return;
      const row = riskCaseRows.find((item) => item.id === button.dataset.caseId);
      if (row) openDrawer(row);
    });
    $("#drawer-close").addEventListener("click", closeDrawer);
    $("#drawer-overlay").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });
  });
}
