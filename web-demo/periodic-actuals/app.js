const periodicActualRows = globalThis.periodicActualRows || [];

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

function displayValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "未披露";
  return `${numberFormatter.format(value)}${suffix ? ` ${suffix}` : ""}`;
}

function accountingLabel(row) {
  if (row.accountingStatus === "未应用") {
    return row.nonApplicationReason
      ? `未应用 · ${row.nonApplicationReason}`
      : "未应用 · 原因未披露";
  }
  if (["已应用", "混合应用"].includes(row.accountingStatus) && row.accountingTypes?.length) {
    return `${row.accountingStatus} · ${row.accountingTypes.join(" / ")}`;
  }
  return row.accountingStatus || "未明确披露";
}

function evidenceProgress(row) {
  return `${row.evidence?.verified ?? 0}/${row.evidence?.total ?? 0}`;
}

function matchesNumericState(value, state) {
  if (!state || state === "all") return true;
  if (state === "missing") return value === null || value === undefined;
  if (typeof value !== "number") return false;
  if (state === "positive") return value > 0;
  if (state === "negative") return value < 0;
  if (state === "zero") return value === 0;
  return true;
}

function filterRows(rows, filters = {}) {
  const {
    period = "all",
    category = "all",
    accounting = "all",
    match = "all",
    search = "",
    columnPeriod = "all",
    company = "all",
    underlying = "all",
    planBasis = "all",
    flowState = "all",
    marginState = "all",
    assetState = "all",
    liabilityState = "all",
    netState = "all",
    pnlState = "all",
    disposalState = "all",
    fvState = "all",
    columnAccounting = "all",
    method = "all",
    columnMatch = "all",
    evidenceState = "all",
  } = filters;
  const query = search.trim().toLocaleLowerCase("zh-CN");

  return rows.filter((row) => {
    if (period !== "all" && row.period !== period) return false;
    if (category !== "all" && row.category !== category) return false;
    if (accounting !== "all" && row.accountingStatus !== accounting) return false;
    if (match !== "all" && row.matchStatus !== match) return false;
    if (columnPeriod !== "all" && row.period !== columnPeriod) return false;
    if (company !== "all" && row.company !== company) return false;
    if (underlying !== "all" && ![
      row.category,
      ...(row.underlying || []),
      ...(row.instrument || []),
    ].includes(underlying)) return false;
    if (planBasis !== "all" && row.plan?.basis !== planBasis) return false;
    const hasFlow = row.purchaseAmount !== null || row.saleAmount !== null;
    if (flowState === "reported" && !hasFlow) return false;
    if (flowState === "missing" && hasFlow) return false;
    if (!matchesNumericState(row.marginBalance, marginState)) return false;
    if (!matchesNumericState(row.derivativeAssets, assetState)) return false;
    if (!matchesNumericState(row.derivativeLiabilities, liabilityState)) return false;
    if (!matchesNumericState(row.netFairValue, netState)) return false;
    if (!matchesNumericState(row.comprehensivePnl, pnlState)) return false;
    if (!matchesNumericState(row.disposalIncome, disposalState)) return false;
    if (!matchesNumericState(row.fvChangePnl, fvState)) return false;
    if (columnAccounting !== "all" && row.accountingStatus !== columnAccounting) return false;
    if (method !== "all" && !(row.accountingTypes || []).includes(method)) return false;
    if (columnMatch !== "all" && row.matchStatus !== columnMatch) return false;
    const evidenceComplete = (row.evidence?.total ?? 0) > 0
      && row.evidence.verified === row.evidence.total;
    if (evidenceState === "complete" && !evidenceComplete) return false;
    if (evidenceState === "partial" && evidenceComplete) return false;
    if (!query) return true;

    const haystack = [
      row.company,
      row.ticker,
      row.category,
      ...(row.underlying || []),
      ...(row.instrument || []),
    ].join(" ").toLocaleLowerCase("zh-CN");
    return haystack.includes(query);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusTone(status) {
  if (["匹配", "已应用", "双回验通过", "引文通过"].includes(status)) return "badge--green";
  if (["部分匹配", "未应用", "待补证据"].includes(status)) return "badge--amber";
  if (["需复核", "仅有实际", "仅有计划"].includes(status)) return "badge--red";
  if (status === "混合应用") return "badge--blue";
  return "";
}

function valueClass(value) {
  return typeof value === "number" && value < 0 ? "num negative" : "num";
}

function renderBadge(label, toneSource = label) {
  return `<span class="badge ${statusTone(toneSource)}">${escapeHtml(label)}</span>`;
}

function renderCategoryMetric(row, field, unit, label) {
  if (row[field] === null && row.reportTotals?.[field] !== null && row.reportTotals?.[field] !== undefined) {
    return `<span class="muted report-total-label" aria-label="${escapeHtml(label)}：报告级合计">报告级合计</span>`;
  }
  return `<span class="${valueClass(row[field])}" aria-label="${escapeHtml(label)}：${escapeHtml(displayValue(row[field], unit))}">${escapeHtml(displayValue(row[field], unit))}</span>`;
}

function renderTableRow(row) {
  const plan = `${displayValue(row.plan?.amount, row.plan?.unit)} · ${row.plan?.basis || "口径未披露"}`;
  const flow = row.purchaseAmount === null && row.saleAmount === null
    ? `<span class="muted">未披露</span>`
    : `<span class="num">购 ${displayValue(row.purchaseAmount, row.flowUnit)}</span>
       <span class="num">售 ${displayValue(row.saleAmount, row.flowUnit)}</span>`;
  const accounting = accountingLabel(row);
  const method = row.accountingTypes?.length ? row.accountingTypes.join(" / ") : "—";

  return `
    <tr>
      <td><strong>${escapeHtml(row.period)}</strong><br><span class="muted">${escapeHtml(row.reportType)}</span></td>
      <td><div class="company-cell"><strong>${escapeHtml(row.company)}</strong><span>${escapeHtml(row.ticker)} · ${escapeHtml(row.province)}</span></div></td>
      <td><div class="stack"><strong>${escapeHtml(row.category)} · ${escapeHtml(row.underlying.join(" / "))}</strong><small>${escapeHtml(row.instrument.join(" / "))}</small></div></td>
      <td><div class="stack"><span class="num">${escapeHtml(plan)}</span><small>${escapeHtml(row.plan?.term || "期间未披露")}</small></div></td>
      <td><div class="stack">${flow}</div></td>
      <td><span class="${valueClass(row.marginBalance)}" aria-label="期末保证金${row.marginBalance === null ? "未披露" : `：${escapeHtml(displayValue(row.marginBalance, row.marginUnit || row.balanceUnit))}`}">${escapeHtml(displayValue(row.marginBalance, row.marginUnit || row.balanceUnit))}</span></td>
      <td>${renderCategoryMetric(row, "derivativeAssets", row.balanceUnit, "衍生金融资产")}</td>
      <td>${renderCategoryMetric(row, "derivativeLiabilities", row.balanceUnit, "衍生金融负债")}</td>
      <td><span class="${valueClass(row.netFairValue)}" aria-label="公允价值净额：${escapeHtml(displayValue(row.netFairValue, row.balanceUnit))}">${escapeHtml(displayValue(row.netFairValue, row.balanceUnit))}</span></td>
      <td><span class="${valueClass(row.comprehensivePnl)}">${escapeHtml(displayValue(row.comprehensivePnl, row.pnlUnit))}</span></td>
      <td>${renderCategoryMetric(row, "disposalIncome", row.pnlUnit, "处置投资收益")}</td>
      <td>${renderCategoryMetric(row, "fvChangePnl", row.pnlUnit, "公允价值变动损益")}</td>
      <td>${renderBadge(row.accountingStatus)}</td>
      <td><span class="muted">${escapeHtml(method)}</span></td>
      <td>${renderBadge(row.matchStatus)}</td>
      <td><button class="detail-button" type="button" data-row-id="${escapeHtml(row.id)}">${escapeHtml(evidenceProgress(row))}</button></td>
    </tr>`;
}

function renderDetailItems(items) {
  return items.map(([label, value]) => `
    <div class="detail-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>`).join("");
}

function renderDrawer(row) {
  const accountingMethod = row.accountingTypes?.length ? row.accountingTypes.join(" / ") : "未披露";
  const evidenceRows = row.evidenceRows.map((item) => `
    <div class="evidence-row">
      <span>${escapeHtml(item.page)}</span>
      <p><strong>${escapeHtml(item.label)}</strong><br>${escapeHtml(item.quote)}</p>
      ${renderBadge(item.status)}
    </div>`).join("");
  const reconciliations = row.reconciliations.length
    ? row.reconciliations.map((equation) => `<p class="equation">${escapeHtml(equation)}</p>`).join("")
    : `<p class="equation muted">当前没有可执行的确定性勾稽。</p>`;
  const reportTotals = row.reportTotals
    ? `
      <section class="detail-section report-total-section">
        <header><h3>报告级合计（未按类别分摊）</h3><span>${escapeHtml(row.reportTotals.source)}</span></header>
        <div class="detail-grid">${renderDetailItems([
          ["处置投资收益", displayValue(row.reportTotals.disposalIncome, row.reportTotals.unit)],
          ["公允价值变动损益", displayValue(row.reportTotals.fvChangePnl, row.reportTotals.unit)],
          ["衍生品综合损益", displayValue(row.reportTotals.comprehensivePnl, row.reportTotals.unit)],
          ["衍生金融资产", displayValue(row.reportTotals.derivativeAssets, row.reportTotals.unit)],
          ["衍生金融负债", displayValue(row.reportTotals.derivativeLiabilities, row.reportTotals.unit)],
          ["期末公允价值净额", displayValue(row.reportTotals.netFairValue, row.reportTotals.unit)],
        ])}</div>
        ${reconciliations}
      </section>`
    : "";

  return `
    <section class="detail-section">
      <header><h3>公告计划</h3><span>${escapeHtml(row.plan?.page || "公告证据")}</span></header>
      <div class="detail-grid">${renderDetailItems([
        ["计划额度", displayValue(row.plan?.amount, row.plan?.unit)],
        ["额度口径", row.plan?.basis || "未披露"],
        ["品种 / 工具", `${row.underlying.join(" / ")} · ${row.instrument.join(" / ")}`],
        ["授权期间", row.plan?.term || "未披露"],
      ])}</div>
    </section>

    <section class="detail-section">
      <header><h3>定期报告实际</h3><span>${escapeHtml(`${row.period} · ${row.reportType}`)}</span></header>
      <div class="detail-grid">${renderDetailItems([
        ["报告期购入", displayValue(row.purchaseAmount, row.flowUnit)],
        ["报告期售出", displayValue(row.saleAmount, row.flowUnit)],
        ["期末保证金", displayValue(row.marginBalance, row.marginUnit || row.balanceUnit)],
        ["保证金列示科目", row.marginAccount || "未披露"],
        ["衍生金融资产", row.reportTotals ? "见报告级合计" : displayValue(row.derivativeAssets, row.balanceUnit)],
        ["衍生金融负债", row.reportTotals ? "见报告级合计" : displayValue(row.derivativeLiabilities, row.balanceUnit)],
        ["期末账面净额", displayValue(row.netFairValue, row.balanceUnit)],
        ["衍生品综合损益", displayValue(row.comprehensivePnl, row.pnlUnit)],
        ["处置投资收益", row.reportTotals ? "见报告级合计" : displayValue(row.disposalIncome, row.pnlUnit)],
        ["公允价值变动损益", row.reportTotals ? "见报告级合计" : displayValue(row.fvChangePnl, row.pnlUnit)],
      ])}</div>
    </section>

    ${reportTotals}

    <section class="detail-section">
      <header><h3>套期会计</h3><span>随报告期记录</span></header>
      <div class="detail-grid">${renderDetailItems([
        ["报告级状态", row.accountingStatus],
        ["会计方法", accountingMethod],
        ["未应用原因", row.nonApplicationReason || "未披露原因"],
        ["认定口径", "以明确勾选或原文陈述为准"],
      ])}</div>
    </section>

    <section class="detail-section">
      <header><h3>核对与证据</h3><span>${escapeHtml(evidenceProgress(row))} 条通过</span></header>
      <div class="detail-grid">${renderDetailItems([
        ["核对状态", row.matchStatus],
        ["核对说明", row.matchNote],
      ])}</div>
      <div class="evidence-list">${evidenceRows}</div>
    </section>`;
}

globalThis.PeriodicActualsDemo = {
  accountingLabel,
  displayValue,
  evidenceProgress,
  filterRows,
  renderDrawer,
  renderTableRow,
};

if (typeof document !== "undefined") {
  const byId = (id) => document.getElementById(id);
  const controls = {
    period: byId("period-filter"),
    category: byId("category-filter"),
    accounting: byId("accounting-filter"),
    match: byId("match-filter"),
    search: byId("search-input"),
  };
  const columnControls = {
    columnPeriod: byId("column-period-filter"),
    company: byId("column-company-filter"),
    underlying: byId("column-underlying-filter"),
    planBasis: byId("column-plan-basis-filter"),
    flowState: byId("column-flow-filter"),
    marginState: byId("column-margin-filter"),
    assetState: byId("column-asset-filter"),
    liabilityState: byId("column-liability-filter"),
    netState: byId("column-net-filter"),
    pnlState: byId("column-pnl-filter"),
    disposalState: byId("column-disposal-filter"),
    fvState: byId("column-fv-filter"),
    columnAccounting: byId("column-accounting-filter"),
    method: byId("column-method-filter"),
    columnMatch: byId("column-match-filter"),
    evidenceState: byId("column-evidence-filter"),
  };
  const body = byId("actuals-body");
  const resultCount = byId("result-count");
  const emptyState = byId("empty-state");
  const tableScroll = document.querySelector(".table-scroll");
  const drawer = byId("detail-drawer");
  const drawerOverlay = byId("drawer-overlay");
  const drawerTitle = byId("drawer-title");
  const drawerContent = byId("drawer-content");

  function appendOptions(control, values) {
    for (const value of [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh-CN"))) {
      control.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
    }
  }

  const periods = [...new Set(periodicActualRows.map((row) => row.period))].sort().reverse();
  appendOptions(controls.period, periods);
  appendOptions(columnControls.columnPeriod, periods);
  appendOptions(columnControls.company, periodicActualRows.map((row) => row.company));
  appendOptions(columnControls.underlying, periodicActualRows.flatMap((row) => [
    row.category,
    ...(row.underlying || []),
    ...(row.instrument || []),
  ]));
  appendOptions(columnControls.planBasis, periodicActualRows.map((row) => row.plan?.basis));
  appendOptions(columnControls.method, periodicActualRows.flatMap((row) => row.accountingTypes || []));

  function currentFilters() {
    return {
      period: controls.period.value,
      category: controls.category.value,
      accounting: controls.accounting.value,
      match: controls.match.value,
      search: controls.search.value,
      ...Object.fromEntries(
        Object.entries(columnControls).map(([key, control]) => [key, control.value]),
      ),
    };
  }

  function render() {
    const visibleRows = filterRows(periodicActualRows, currentFilters());
    body.innerHTML = visibleRows.map(renderTableRow).join("");
    resultCount.textContent = String(visibleRows.length);
    emptyState.hidden = visibleRows.length > 0;
    tableScroll.hidden = visibleRows.length === 0;
  }

  function openDrawer(row) {
    drawerTitle.textContent = `${row.company} · ${row.period} · ${row.category}`;
    drawerContent.innerHTML = renderDrawer(row);
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    drawerOverlay.hidden = false;
    document.body.classList.add("drawer-open");
  }

  function closeDrawer() {
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    drawerOverlay.hidden = true;
    document.body.classList.remove("drawer-open");
  }

  for (const control of [...Object.values(controls), ...Object.values(columnControls)]) {
    control.addEventListener(control === controls.search ? "input" : "change", render);
  }

  byId("reset-filters").addEventListener("click", () => {
    controls.period.value = "all";
    controls.category.value = "all";
    controls.accounting.value = "all";
    controls.match.value = "all";
    controls.search.value = "";
    for (const control of Object.values(columnControls)) control.value = "all";
    render();
  });

  body.addEventListener("click", (event) => {
    const button = event.target.closest("[data-row-id]");
    if (!button) return;
    const row = periodicActualRows.find((item) => item.id === button.dataset.rowId);
    if (row) openDrawer(row);
  });

  byId("drawer-close").addEventListener("click", closeDrawer);
  drawerOverlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });

  const fullyVerified = periodicActualRows.filter((row) => row.evidence.verified === row.evidence.total).length;
  const appliedAccounting = periodicActualRows.filter((row) => ["已应用", "混合应用"].includes(row.accountingStatus)).length;
  byId("metric-rows").textContent = String(periodicActualRows.length);
  byId("metric-companies").textContent = String(new Set(periodicActualRows.map((row) => row.ticker)).size);
  byId("metric-verified").textContent = `${fullyVerified}/${periodicActualRows.length}`;
  byId("metric-accounting").textContent = String(appliedAccounting);

  render();
}
