(() => {
  "use strict";

  const config = window.HEDGE_CONFIG || {};
  const PAGE_SIZE = 50;
  const API_PAGE_SIZE = 1000;
  const API_TIMEOUT_MS = 20000;
  const API_MAX_ATTEMPTS = 3;
  const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
  const EVENT_FIELDS = [
    "event_key", "code", "name", "anchor_year", "scope", "plan_label", "stage",
    "approval_level", "latest_ann_date", "ann_count",
    "instruments", "underlyings", "venue", "period_text", "is_revolving",
    "use_own_funds", "quota", "built_at", "ind_l1", "ind_l2", "ind_l3",
    "ent_type", "province"
  ].join(",");
  const ANNOUNCEMENT_FIELDS = [
    "ann_id", "event_key", "code", "name", "title", "ann_date", "pdf_url",
    "status", "ann_role", "scope", "instruments", "underlyings", "venue",
    "approval_level", "plan_label", "meeting", "period_text", "is_revolving",
    "use_own_funds", "summary", "confidence", "evidence", "extracted_at", "ind_l1",
    "ind_l2", "ind_l3", "ent_type", "province"
  ].join(",");

  const state = {
    view: "events",
    events: [],
    announcements: null,
    extractedCount: 0,
    query: "",
    scope: "all",
    approval: "all",
    entType: "all",
    dashboardYear: "all",
    page: 1,
    sortKey: "date",
    sortDirection: "desc",
    loadedAt: null,
    selectedEventKey: null,
    lastFocusedElement: null
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const asArray = (value) => Array.isArray(value) ? value : [];
  const escapeHtml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  function formatDate(value, compact = false) {
    if (!value) return "—";
    const normalized = String(value).slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(normalized)) return escapeHtml(value);
    return compact ? normalized.slice(5).replace("-", ".") : normalized.replace(/-/g, ".");
  }

  function joinValues(value, fallback = "未披露", separator = "、") {
    const values = asArray(value).filter(Boolean);
    return values.length ? values.join(separator) : fallback;
  }

  function formatAmount(amount, currency = "CNY") {
    if (amount === null || amount === undefined || amount === "") return "未披露";
    const numeric = Number(amount);
    if (!Number.isFinite(numeric)) return String(amount);
    const code = String(currency || "CNY").toUpperCase();
    const prefix = code === "CNY" ? "¥" : `${code} `;
    const absolute = Math.abs(numeric);
    if (absolute >= 100000000) return `${prefix}${trimZeros(numeric / 100000000)} 亿`;
    if (absolute >= 10000) return `${prefix}${trimZeros(numeric / 10000)} 万`;
    return `${prefix}${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
  }

  function trimZeros(value) {
    return Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  function percent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "—";
  }

  function safeExternalUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  }

  const delay = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  async function fetchWithRetry(url, options = {}) {
    let lastError;
    for (let attempt = 1; attempt <= API_MAX_ATTEMPTS; attempt += 1) {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
      try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        if (response.ok) return response;
        const message = await response.text().catch(() => "");
        const error = new Error(`数据接口 ${response.status}${message ? `：${message.slice(0, 80)}` : ""}`);
        error.status = response.status;
        if (!RETRYABLE_STATUS.has(response.status) || attempt === API_MAX_ATTEMPTS) throw error;
        lastError = error;
      } catch (error) {
        const normalized = error?.name === "AbortError"
          ? new Error(`数据请求超过 ${API_TIMEOUT_MS / 1000} 秒未响应`)
          : error;
        lastError = normalized;
        const retryable = error?.name === "AbortError"
          || error instanceof TypeError
          || RETRYABLE_STATUS.has(error?.status);
        if (!retryable || attempt === API_MAX_ATTEMPTS) throw normalized;
      } finally {
        window.clearTimeout(timeout);
      }
      setLoadingProgress(`网络波动，正在进行第 ${attempt + 1} / ${API_MAX_ATTEMPTS} 次尝试…`);
      await delay(500 * attempt);
    }
    throw lastError || new Error("数据请求失败");
  }

  async function apiRows(path, params = {}) {
    if (!config.supabaseUrl || !config.supabaseKey) {
      throw new Error("缺少 Supabase 公开只读配置");
    }
    const url = new URL(`${config.supabaseUrl}/rest/v1/${path}`);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
    });
    const response = await fetchWithRetry(url, { headers: { apikey: config.supabaseKey } });
    return response.json();
  }

  async function apiCount(path, params = {}) {
    if (!config.supabaseUrl || !config.supabaseKey) {
      throw new Error("缺少 Supabase 公开只读配置");
    }
    const url = new URL(`${config.supabaseUrl}/rest/v1/${path}`);
    Object.entries({ select: "*", ...params }).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
    });
    const response = await fetchWithRetry(url, {
      method: "HEAD",
      headers: { apikey: config.supabaseKey, Prefer: "count=exact" }
    });
    const contentRange = response.headers.get("content-range") || "";
    const total = Number(contentRange.split("/").pop());
    if (!Number.isFinite(total)) throw new Error("公告计数响应缺少总数");
    return total;
  }

  async function apiAll(path, params = {}, options = {}) {
    const output = [];
    let offset = 0;
    let page = 0;
    while (true) {
      const rows = await apiRows(path, { ...params, limit: String(API_PAGE_SIZE), offset: String(offset) });
      output.push(...rows);
      page += 1;
      if (options.progressLabel) {
        setLoadingProgress(`${options.progressLabel} · 已读取 ${output.length.toLocaleString("zh-CN")} 条`);
      }
      if (rows.length < API_PAGE_SIZE) break;
      offset += API_PAGE_SIZE;
      if (page >= 1000) throw new Error("分页数量异常，已停止继续请求");
    }
    return output;
  }

  async function loadCoreData() {
    setLoading(true);
    setConnection("loading");
    try {
      const [events, extractedCount] = await Promise.all([
        apiAll("v_events", { select: EVENT_FIELDS, order: "latest_ann_date.desc,event_key.asc" }, { progressLabel: "正在读取事件" }),
        apiCount("announcements", { select: "ann_id", status: "eq.extracted" })
      ]);
      state.events = events;
      state.extractedCount = extractedCount;
      state.loadedAt = new Date();
      state.page = 1;
      setConnection("online");
      renderMetrics();
      renderCurrentView();
      setLoading(false);
    } catch (error) {
      setLoading(false);
      setConnection("error");
      showError(error);
    }
  }

  async function ensureAnnouncements() {
    if (state.announcements) return;
    setLoading(true, "正在读取公告原流", "完整分页读取 3,000+ 条结构化公告");
    try {
      state.announcements = await apiAll("v_ann_flow", {
        select: ANNOUNCEMENT_FIELDS,
        status: "eq.extracted",
        is_hedge_related: "eq.true",
        order: "ann_date.desc,ann_id.asc"
      }, { progressLabel: "正在读取公告" });
      setLoading(false);
    } catch (error) {
      setLoading(false);
      showError(error);
      throw error;
    }
  }

  function setConnection(status) {
    const dot = $(".status-dot");
    dot.classList.remove("is-online", "is-error");
    if (status === "online") {
      dot.classList.add("is-online");
      $("#connection-label").textContent = "数据已连接";
    } else if (status === "error") {
      dot.classList.add("is-error");
      $("#connection-label").textContent = "连接异常";
    } else {
      $("#connection-label").textContent = "正在连接";
    }
  }

  function setLoading(isLoading, title = "正在读取结构化数据", subtitle = "首次载入会完整分页读取事件层") {
    $("#loading-state").hidden = !isLoading;
    if (isLoading) {
      $("#loading-state strong").textContent = title;
      $("#loading-state span:last-child").textContent = subtitle;
      $("#error-state").hidden = true;
      $("#events-table-wrap").hidden = true;
      $("#announcements-table-wrap").hidden = true;
      $("#pagination").hidden = true;
    }
  }

  function setLoadingProgress(message) {
    const loading = $("#loading-state");
    if (!loading || loading.hidden) return;
    const subtitle = $("#loading-state span:last-child");
    if (subtitle) subtitle.textContent = message;
  }

  function showError(error) {
    $("#error-state").hidden = false;
    $("#error-message").textContent = error?.message || "请稍后刷新。";
  }

  function renderMetrics() {
    const companyCount = new Set(state.events.map((event) => event.code).filter(Boolean)).size;
    const multiCount = state.events.filter((event) => Number(event.ann_count) > 1).length;
    const extractedCount = state.extractedCount;
    $("#metric-events").textContent = state.events.length.toLocaleString("zh-CN");
    $("#metric-extracted").textContent = extractedCount.toLocaleString("zh-CN");
    $("#metric-companies").textContent = companyCount.toLocaleString("zh-CN");
    $("#metric-multi").textContent = multiCount.toLocaleString("zh-CN");
    $("#nav-events-count").textContent = state.events.length.toLocaleString("zh-CN");
    $("#nav-announcements-count").textContent = extractedCount.toLocaleString("zh-CN");

    const latestBuilt = state.events.map((event) => event.built_at).filter(Boolean).sort().at(-1);
    $("#data-date").textContent = latestBuilt ? `数据更新至 ${formatDate(latestBuilt)}` : "数据已连接";
    $("#sidebar-updated").textContent = state.loadedAt
      ? `最后读取 ${state.loadedAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`
      : "Supabase · 只读";
  }

  function groupByDimension(rows, valueGetter, multiValue = false) {
    const groups = new Map();
    rows.forEach((row) => {
      const rawValues = multiValue ? asArray(valueGetter(row)) : [valueGetter(row)];
      const values = rawValues.filter(Boolean).length ? rawValues.filter(Boolean) : ["未分类"];
      values.forEach((value) => {
        if (!groups.has(value)) groups.set(value, { label: value, events: 0, companies: new Set() });
        const group = groups.get(value);
        group.events += 1;
        if (row.code) group.companies.add(row.code);
      });
    });
    return Array.from(groups.values()).map((group) => ({
      label: group.label,
      value: group.companies.size,
      events: group.events
    }));
  }

  function renderDashboard() {
    const yearGroups = new Map();
    state.events.forEach((event) => {
      const year = String(event.anchor_year || "未标注");
      if (!yearGroups.has(year)) yearGroups.set(year, { year, events: 0, companies: new Set() });
      const group = yearGroups.get(year);
      group.events += 1;
      if (event.code) group.companies.add(event.code);
    });
    const years = Array.from(yearGroups.values())
      .map((group) => ({ year: group.year, events: group.events, companies: group.companies.size }))
      .sort((a, b) => String(a.year).localeCompare(String(b.year)));
    const yearMax = Math.max(1, ...years.flatMap((item) => [item.events, item.companies]));
    $("#year-chart").innerHTML = `<div class="chart-legend"><span><i></i>覆盖公司</span><span><i></i>套保事件</span></div>${years.map((item) => `<div class="year-row">
      <span class="year-label">${escapeHtml(item.year)}</span>
      <div class="year-bars"><div class="year-bar"><i style="width:${(item.companies / yearMax * 100).toFixed(2)}%"></i></div><div class="year-bar"><i style="width:${(item.events / yearMax * 100).toFixed(2)}%"></i></div></div>
      <div class="year-values"><strong>${item.companies.toLocaleString("zh-CN")}</strong> 公司<br />${item.events.toLocaleString("zh-CN")} 事件</div>
    </div>`).join("")}`;

    renderDashboardYearOptions(years);
    const dashboardRows = state.dashboardYear === "all"
      ? state.events
      : state.events.filter((row) => String(row.anchor_year || "未标注") === state.dashboardYear);
    const dashboardCompanies = new Set(dashboardRows.map((row) => row.code).filter(Boolean)).size;
    $("#dashboard-year-summary").textContent = `${state.dashboardYear === "all" ? "全部年份" : `${state.dashboardYear} 年`} · ${dashboardCompanies.toLocaleString("zh-CN")} 家公司 · ${dashboardRows.length.toLocaleString("zh-CN")} 个事件`;

    const types = groupByDimension(dashboardRows, (row) => row.ent_type).sort((a, b) => b.value - a.value);
    const scopes = groupByDimension(dashboardRows, (row) => row.scope, true).sort((a, b) => b.events - a.events).map((item) => ({ ...item, secondary: item.value, value: item.events }));
    const industries = groupByDimension(dashboardRows, (row) => row.ind_l1).sort((a, b) => b.value - a.value).slice(0, 12);
    const provinces = groupByDimension(dashboardRows, (row) => row.province).sort((a, b) => b.value - a.value).slice(0, 16);
    const approvals = groupByDimension(dashboardRows, (row) => row.approval_level).sort((a, b) => b.events - a.events).map((item) => ({ ...item, secondary: item.value, value: item.events }));
    renderBarChart("#type-chart", types, "事件");
    renderBarChart("#scope-chart", scopes, "公司");
    renderBarChart("#industry-chart", industries, "事件");
    renderBarChart("#province-chart", provinces, "事件");
    renderBarChart("#approval-chart", approvals, "公司");

    const total = Math.max(1, dashboardRows.length);
    const quality = [
      { label: "额度已披露", count: dashboardRows.filter((row) => asArray(row.quota).length > 0).length },
      { label: "工具字段", count: dashboardRows.filter((row) => asArray(row.instruments).length > 0).length },
      { label: "品种字段", count: dashboardRows.filter((row) => asArray(row.underlyings).length > 0).length },
      { label: "期限字段", count: dashboardRows.filter((row) => Boolean(row.period_text)).length }
    ];
    $("#quality-chart").innerHTML = quality.map((item) => `<div class="quality-item"><span>${escapeHtml(item.label)}</span><strong>${(item.count / total * 100).toFixed(1)}%</strong><small>${item.count.toLocaleString("zh-CN")} / ${dashboardRows.length.toLocaleString("zh-CN")} 个事件</small></div>`).join("");
  }

  function renderDashboardYearOptions(years) {
    const select = $("#dashboard-year-filter");
    const options = [...years].sort((a, b) => String(b.year).localeCompare(String(a.year)));
    const validValues = new Set(["all", ...options.map((item) => String(item.year))]);
    if (!validValues.has(state.dashboardYear)) state.dashboardYear = "all";
    select.innerHTML = '<option value="all">全部年份</option>' + options.map((item) => `<option value="${escapeHtml(item.year)}">${escapeHtml(item.year)} 年</option>`).join("");
    select.value = state.dashboardYear;
  }

  function renderBarChart(selector, rows, secondaryLabel) {
    const maxValue = Math.max(1, ...rows.map((row) => row.value));
    $(selector).innerHTML = rows.length ? rows.map((row) => `<div class="bar-row">
      <span class="bar-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(row.value / maxValue * 100).toFixed(2)}%"></div></div>
      <span class="bar-value">${row.value.toLocaleString("zh-CN")}<small>${Number(row.secondary ?? row.events ?? 0).toLocaleString("zh-CN")} ${escapeHtml(secondaryLabel)}</small></span>
    </div>`).join("") : '<p class="drawer-empty">暂无可统计数据。</p>';
  }

  function matchesFilters(row) {
    const needle = state.query.trim().toLowerCase();
    const searchable = [
      row.name, row.code, row.title, row.plan_label, row.stage, row.summary,
      joinValues(row.scope, ""), joinValues(row.instruments, ""),
      joinValues(row.underlyings, ""), row.ind_l1, row.ind_l2, row.ind_l3,
      row.ent_type, row.province, row.approval_level
    ].join(" ").toLowerCase();
    const scopeMatch = state.scope === "all" || asArray(row.scope).includes(state.scope);
    const approvalMatch = state.approval === "all" || row.approval_level === state.approval;
    const typeMatch = state.entType === "all" || row.ent_type === state.entType;
    return (!needle || searchable.includes(needle)) && scopeMatch && approvalMatch && typeMatch;
  }

  function filteredEvents() {
    const rows = state.events.filter(matchesFilters);
    return rows.sort((a, b) => {
      let left;
      let right;
      if (state.sortKey === "company") {
        left = `${a.name || ""}${a.code || ""}`;
        right = `${b.name || ""}${b.code || ""}`;
      } else if (state.sortKey === "evidence") {
        left = Number(a.ann_count || 0);
        right = Number(b.ann_count || 0);
      } else {
        left = a.latest_ann_date || "";
        right = b.latest_ann_date || "";
      }
      const comparison = typeof left === "number"
        ? left - right
        : String(left).localeCompare(String(right), "zh-CN");
      return state.sortDirection === "asc" ? comparison : -comparison;
    });
  }

  function filteredAnnouncements() {
    return (state.announcements || []).filter(matchesFilters);
  }

  function representativeQuota(event) {
    const quotas = asArray(event.quota).filter((item) => item && item.amount !== null && item.amount !== undefined);
    if (!quotas.length) return { amount: "未披露", basis: "额度待原文确认", extra: "" };
    const first = quotas[0];
    return {
      amount: formatAmount(first.amount, first.currency),
      basis: first.basis || "已抽取额度",
      extra: quotas.length > 1 ? `另有 ${quotas.length - 1} 项` : ""
    };
  }

  function renderCurrentView() {
    updateViewChrome();
    if (state.view === "dashboard") renderDashboard();
    else if (state.view === "events") renderEvents();
    else renderAnnouncements();
  }

  function updateViewChrome() {
    const isDashboard = state.view === "dashboard";
    const isEvents = state.view === "events";
    $("#page-title").textContent = isDashboard ? "数据看板" : isEvents ? "套保事件" : "公告原流";
    $("#page-subtitle").textContent = isDashboard ? "公司覆盖、事件结构与字段质量" : isEvents ? "按公司、年度与类别聚合" : "结构化公告与证据记录";
    $("#breadcrumb-view").textContent = isDashboard ? "看板" : isEvents ? "事件" : "公告";
    $$('[data-view]').forEach((button) => button.classList.toggle("is-active", button.dataset.view === state.view));
    $("#dashboard-view").hidden = !isDashboard;
    $("#data-panel").hidden = isDashboard;
    $("#metric-grid").hidden = state.view === "announcements";
    $("#clear-filters").hidden = isDashboard;
    $("#events-table-wrap").hidden = !isEvents;
    $("#announcements-table-wrap").hidden = isEvents || isDashboard;
    $("#error-state").hidden = true;
  }

  function renderEvents() {
    const rows = filteredEvents();
    const pageRows = pageSlice(rows);
    $("#events-body").innerHTML = pageRows.length ? pageRows.map((event) => {
      const quota = representativeQuota(event);
      const scopeTags = asArray(event.scope).slice(0, 2).map((item) => `<span class="tag ${item === "综合" ? "tag--dark" : ""}">${escapeHtml(item)}</span>`).join("") || '<span class="tag">其他</span>';
      const instrumentLine = [joinValues(event.underlyings, "", "、"), joinValues(event.instruments, "", "、")].filter(Boolean).join(" · ") || "未披露";
      const selected = state.selectedEventKey === event.event_key ? " is-selected" : "";
      return `<tr class="data-row${selected}" tabindex="0" data-event-key="${escapeHtml(event.event_key)}" aria-label="打开 ${escapeHtml(event.name || "公司")} 事件详情">
        <td class="date-cell" data-label="最新披露"><span class="cell-primary">${escapeHtml(formatDate(event.latest_ann_date, true))}</span><span class="cell-secondary">${escapeHtml(event.anchor_year || "—")} 年度</span></td>
        <td class="company-cell" data-label="公司"><span class="cell-primary">${escapeHtml(event.name || "未命名公司")}</span><span class="cell-secondary">${escapeHtml(event.code || "—")} · ${escapeHtml(event.ind_l1 || "行业未录入")}</span></td>
        <td data-label="省份"><span class="cell-primary">${escapeHtml(event.province || "未录入")}</span></td>
        <td data-label="类别"><div class="tag-list">${scopeTags}</div></td>
        <td data-label="阶段"><span class="cell-primary">${escapeHtml(event.stage || "套保事件")}</span><span class="cell-secondary">${escapeHtml(event.approval_level || "审批未披露")}</span></td>
        <td data-label="品种 / 工具"><span class="cell-primary">${escapeHtml(instrumentLine)}</span><span class="cell-secondary">${escapeHtml(event.venue || "场所未披露")}</span></td>
        <td class="amount-cell" data-label="额度"><span class="cell-primary">${escapeHtml(quota.amount)}</span><span class="cell-secondary">${escapeHtml([quota.basis, quota.extra].filter(Boolean).join(" · "))}</span></td>
        <td data-label="期限"><span class="cell-primary">${escapeHtml(event.period_text || "未披露")}</span><span class="cell-secondary">${event.is_revolving ? "额度循环使用" : "非循环或未说明"}</span></td>
        <td data-label="证据"><button class="evidence-link" type="button" data-event-key="${escapeHtml(event.event_key)}">${escapeHtml(event.ann_count || 0)} 条</button></td>
      </tr>`;
    }).join("") : '<tr class="empty-row"><td colspan="9">没有匹配的事件，请调整搜索或筛选条件。</td></tr>';
    renderResultMeta(rows.length);
    renderPagination(rows.length);
    updateSortButtons();
  }

  function renderAnnouncements() {
    const rows = filteredAnnouncements();
    const pageRows = pageSlice(rows);
    $("#announcements-body").innerHTML = pageRows.length ? pageRows.map((row) => {
      const scopes = asArray(row.scope).slice(0, 2).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") || '<span class="tag">其他</span>';
      const evidenceCount = asArray(row.evidence).length;
      return `<tr class="data-row" tabindex="0" data-ann-id="${escapeHtml(row.ann_id)}" aria-label="打开 ${escapeHtml(row.title || "公告")} 详情">
        <td class="date-cell" data-label="披露日期"><span class="cell-primary">${escapeHtml(formatDate(row.ann_date))}</span></td>
        <td class="company-cell" data-label="公司"><span class="cell-primary">${escapeHtml(row.name || "未命名公司")}</span><span class="cell-secondary">${escapeHtml(row.code || "—")}</span></td>
        <td data-label="省份"><span class="cell-primary">${escapeHtml(row.province || "未录入")}</span></td>
        <td data-label="公告标题"><span class="cell-primary">${escapeHtml(row.title || "未命名公告")}</span><span class="cell-secondary">${escapeHtml(row.summary || "暂无摘要")}</span></td>
        <td data-label="角色"><span class="cell-primary">${escapeHtml(row.ann_role || "其他")}</span><span class="cell-secondary">${escapeHtml(row.approval_level || "审批未披露")}</span></td>
        <td data-label="类别"><div class="tag-list">${scopes}</div></td>
        <td data-label="置信度"><span class="cell-primary">${escapeHtml(percent(row.confidence))}</span></td>
        <td data-label="证据"><button class="evidence-link" type="button" data-ann-id="${escapeHtml(row.ann_id)}">${evidenceCount} 条</button></td>
      </tr>`;
    }).join("") : '<tr class="empty-row"><td colspan="8">没有匹配的公告，请调整搜索或筛选条件。</td></tr>';
    renderResultMeta(rows.length);
    renderPagination(rows.length);
  }

  function pageSlice(rows) {
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
  }

  function renderResultMeta(total) {
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    $("#result-count").textContent = `${total.toLocaleString("zh-CN")} ${state.view === "events" ? "个事件" : "条公告"}`;
    $("#page-label").textContent = `第 ${state.page} / ${totalPages} 页`;
  }

  function renderPagination(total) {
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const pagination = $("#pagination");
    pagination.hidden = total <= PAGE_SIZE;
    $("#prev-page").disabled = state.page <= 1;
    $("#next-page").disabled = state.page >= totalPages;
    if (pagination.hidden) return;

    const pages = paginationWindow(totalPages, state.page);
    $("#pagination-pages").innerHTML = pages.map((page) => page === "…"
      ? '<span class="page-ellipsis">…</span>'
      : `<button class="page-button ${page === state.page ? "is-active" : ""}" type="button" data-page="${page}">${page}</button>`
    ).join("");
  }

  function paginationWindow(totalPages, current) {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
    const pages = new Set([1, totalPages, current - 1, current, current + 1].filter((page) => page >= 1 && page <= totalPages));
    const ordered = Array.from(pages).sort((a, b) => a - b);
    const output = [];
    ordered.forEach((page, index) => {
      if (index && page - ordered[index - 1] > 1) output.push("…");
      output.push(page);
    });
    return output;
  }

  function updateSortButtons() {
    $$(".sort-button").forEach((button) => {
      const active = button.dataset.sort === state.sortKey;
      button.classList.toggle("is-active", active);
      button.dataset.direction = active ? state.sortDirection : "";
    });
  }

  function openDrawer(title, subtitle, kicker = "EVENT DETAIL") {
    state.lastFocusedElement = document.activeElement;
    $("#drawer-title").textContent = title;
    $("#drawer-subtitle").textContent = subtitle;
    $("#drawer-kicker").textContent = kicker;
    $("#detail-drawer").classList.add("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
    requestAnimationFrame(() => $("[data-close-drawer]").focus());
  }

  function closeDrawer() {
    $("#detail-drawer").classList.remove("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
    document.body.classList.remove("drawer-open");
    state.selectedEventKey = null;
    if (state.view === "events") renderEvents();
    if (state.lastFocusedElement?.focus) state.lastFocusedElement.focus();
  }

  async function openEventDetail(event) {
    state.selectedEventKey = event.event_key;
    renderEvents();
    openDrawer(event.name || "未命名公司", `${event.code || "—"} · ${event.anchor_year || "—"} · ${joinValues(event.scope)}`);
    $("#drawer-content").innerHTML = renderEventOverview(event) + '<section class="drawer-section"><h3 class="drawer-section-title">关联公告与证据</h3><div id="event-timeline" class="drawer-loading">正在读取公告证据…</div></section>';
    try {
      const rows = await apiRows("v_ann_flow", {
        select: ANNOUNCEMENT_FIELDS,
        event_key: `eq.${event.event_key}`,
        order: "ann_date.asc,ann_id.asc",
        limit: "200"
      });
      const target = $("#event-timeline");
      if (target) target.outerHTML = renderTimeline(rows);
    } catch (error) {
      const target = $("#event-timeline");
      if (target) target.innerHTML = `<p class="drawer-empty">公告证据读取失败：${escapeHtml(error.message)}</p>`;
    }
  }

  function renderEventOverview(event) {
    const quotas = asArray(event.quota);
    const quotaHtml = quotas.length ? quotas.map((item) => `<article class="quota-item">
      <div class="quota-item-head"><span>${escapeHtml(item.scope || "综合")} · ${escapeHtml(item.basis || "口径未披露")}</span><strong>${escapeHtml(formatAmount(item.amount, item.currency))}</strong></div>
      <p>${escapeHtml(item.raw_text || "未保留额度原文")}</p>
      <div class="verification"><span class="tag ${item.amount_verified ? "tag--blue" : ""}">金额${item.amount_verified ? "已回验" : "待回验"}</span><span class="tag ${item.quote_verified ? "tag--blue" : ""}">引文${item.quote_verified ? "已回验" : "待回验"}</span>${item.page ? `<span class="tag">第 ${escapeHtml(item.page)} 页</span>` : ""}</div>
    </article>`).join("") : '<p class="drawer-empty">该事件未披露可统计额度，不以 0 代替。</p>';

    return `<section class="drawer-section">
      <div class="detail-grid">
        <div class="detail-card"><span>事件阶段</span><strong>${escapeHtml(event.stage || "未披露")}</strong></div>
        <div class="detail-card"><span>审批层级</span><strong>${escapeHtml(event.approval_level || "未披露")}</strong></div>
        <div class="detail-card"><span>关联公告</span><strong>${escapeHtml(event.ann_count || 0)} 条</strong></div>
        <div class="detail-card"><span>期限</span><strong>${escapeHtml(event.period_text || "未披露")}</strong></div>
      </div>
    </section>
    <section class="drawer-section">
      <h3 class="drawer-section-title">事件字段</h3>
      <div class="detail-line"><span>工具</span><strong>${escapeHtml(joinValues(event.instruments))}</strong></div>
      <div class="detail-line"><span>品种</span><strong>${escapeHtml(joinValues(event.underlyings))}</strong></div>
      <div class="detail-line"><span>交易场所</span><strong>${escapeHtml(event.venue || "未披露")}</strong></div>
      <div class="detail-line"><span>额度循环</span><strong>${event.is_revolving === true ? "是" : event.is_revolving === false ? "否" : "未披露"}</strong></div>
      <div class="detail-line"><span>自有资金</span><strong>${event.use_own_funds === true ? "是" : event.use_own_funds === false ? "否" : "未披露"}</strong></div>
      <div class="detail-line"><span>行业</span><strong>${escapeHtml([event.ind_l1, event.ind_l2, event.ind_l3].filter(Boolean).join(" / ") || "未录入")}</strong></div>
      <div class="detail-line"><span>省份</span><strong>${escapeHtml(event.province || "未录入")}</strong></div>
      <div class="detail-line"><span>企业性质</span><strong>${escapeHtml(event.ent_type || "未录入")}</strong></div>
    </section>
    <section class="drawer-section"><h3 class="drawer-section-title">额度与口径</h3><div class="quota-list">${quotaHtml}</div></section>`;
  }

  function renderTimeline(rows) {
    if (!rows.length) return '<div class="timeline"><p class="drawer-empty">当前事件没有可读取的关联公告。</p></div>';
    return `<div class="timeline">${rows.map((row) => {
      const evidence = asArray(row.evidence).slice(0, 3);
      const evidenceHtml = evidence.map((item) => `<blockquote class="evidence-quote"><small>第 ${escapeHtml(item.page || "—")} 页 · ${escapeHtml(item.field || "证据")}</small>${escapeHtml(item.quote || "未提供引文")}</blockquote>`).join("");
      const pdf = safeExternalUrl(row.pdf_url);
      return `<article class="timeline-item">
        <div class="timeline-meta"><span>${escapeHtml(formatDate(row.ann_date))}</span><span class="tag">${escapeHtml(row.ann_role || "其他")}</span></div>
        <h4>${escapeHtml(row.title || "未命名公告")}</h4>
        <p>${escapeHtml(row.summary || "暂无摘要")}</p>
        ${evidenceHtml}
        ${pdf ? `<a class="source-link" href="${escapeHtml(pdf)}" target="_blank" rel="noopener noreferrer">打开公告原文 ↗</a>` : ""}
      </article>`;
    }).join("")}</div>`;
  }

  function openAnnouncementDetail(row) {
    openDrawer(row.name || "未命名公司", `${row.code || "—"} · ${formatDate(row.ann_date)}`, "ANNOUNCEMENT DETAIL");
    const evidence = asArray(row.evidence);
    const pdf = safeExternalUrl(row.pdf_url);
    const evidenceHtml = evidence.length ? evidence.map((item) => `<blockquote class="evidence-quote"><small>第 ${escapeHtml(item.page || "—")} 页 · ${escapeHtml(item.field || "证据")}</small>${escapeHtml(item.quote || "未提供引文")}</blockquote>`).join("") : '<p class="drawer-empty">当前公告没有可展示的证据引文。</p>';
    $("#drawer-content").innerHTML = `<section class="drawer-section">
      <div class="detail-grid">
        <div class="detail-card"><span>公告角色</span><strong>${escapeHtml(row.ann_role || "其他")}</strong></div>
        <div class="detail-card"><span>审批层级</span><strong>${escapeHtml(row.approval_level || "未披露")}</strong></div>
        <div class="detail-card"><span>类别</span><strong>${escapeHtml(joinValues(row.scope))}</strong></div>
        <div class="detail-card"><span>置信度</span><strong>${escapeHtml(percent(row.confidence))}</strong></div>
      </div>
    </section>
    <section class="drawer-section"><h3 class="drawer-section-title">${escapeHtml(row.title || "公告摘要")}</h3><p class="drawer-empty">${escapeHtml(row.summary || "暂无摘要")}</p>${pdf ? `<a class="source-link" href="${escapeHtml(pdf)}" target="_blank" rel="noopener noreferrer">打开公告原文 ↗</a>` : ""}</section>
    <section class="drawer-section"><h3 class="drawer-section-title">证据引文</h3>${evidenceHtml}</section>
    <section class="drawer-section"><h3 class="drawer-section-title">结构化字段</h3>
      <div class="detail-line"><span>工具</span><strong>${escapeHtml(joinValues(row.instruments))}</strong></div>
      <div class="detail-line"><span>品种</span><strong>${escapeHtml(joinValues(row.underlyings))}</strong></div>
      <div class="detail-line"><span>期限</span><strong>${escapeHtml(row.period_text || "未披露")}</strong></div>
      <div class="detail-line"><span>行业</span><strong>${escapeHtml([row.ind_l1, row.ind_l2, row.ind_l3].filter(Boolean).join(" / ") || "未录入")}</strong></div>
      <div class="detail-line"><span>省份</span><strong>${escapeHtml(row.province || "未录入")}</strong></div>
      <div class="detail-line"><span>企业性质</span><strong>${escapeHtml(row.ent_type || "未录入")}</strong></div>
    </section>`;
  }

  async function switchView(view) {
    if (!view || view === state.view) return;
    state.view = view;
    state.page = 1;
    if (view === "announcements") {
      updateViewChrome();
      try { await ensureAnnouncements(); } catch (_) { return; }
    }
    renderCurrentView();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearFilters() {
    state.query = "";
    state.scope = "all";
    state.approval = "all";
    state.entType = "all";
    state.page = 1;
    $("#search-input").value = "";
    $("#scope-filter").value = "all";
    $("#approval-filter").value = "all";
    $("#type-filter").value = "all";
    renderCurrentView();
  }

  function csvCell(value) {
    let text = value === null || value === undefined ? "" : String(value);
    if (/^[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  }

  function quotaExportText(event) {
    return asArray(event.quota).map((item) => [
      item.scope || "综合",
      item.basis || "口径未披露",
      item.currency || "CNY",
      item.amount ?? "未披露"
    ].join(" / ")).join("；");
  }

  function exportCurrentResults() {
    const isEvents = state.view === "events";
    const rows = isEvents ? filteredEvents() : filteredAnnouncements();
    if (!rows.length) {
      showToast("当前筛选没有可导出的数据");
      return;
    }

    const headers = isEvents
      ? ["最新披露", "年度", "股票代码", "公司", "省份", "一级行业", "二级行业", "企业性质", "类别", "事件阶段", "审批层级", "工具", "品种", "交易场所", "期限", "额度循环", "自有资金", "额度明细", "关联公告数", "事件键"]
      : ["披露日期", "股票代码", "公司", "省份", "公告标题", "公告角色", "审批层级", "类别", "工具", "品种", "期限", "行业", "企业性质", "置信度", "证据数", "摘要", "原文链接", "公告ID"];
    const body = rows.map((row) => isEvents
      ? [row.latest_ann_date, row.anchor_year, row.code, row.name, row.province, row.ind_l1, row.ind_l2, row.ent_type, joinValues(row.scope, ""), row.stage, row.approval_level, joinValues(row.instruments, ""), joinValues(row.underlyings, ""), row.venue, row.period_text, row.is_revolving === true ? "是" : row.is_revolving === false ? "否" : "", row.use_own_funds === true ? "是" : row.use_own_funds === false ? "否" : "", quotaExportText(row), row.ann_count, row.event_key]
      : [row.ann_date, row.code, row.name, row.province, row.title, row.ann_role, row.approval_level, joinValues(row.scope, ""), joinValues(row.instruments, ""), joinValues(row.underlyings, ""), row.period_text, row.ind_l1, row.ent_type, row.confidence, asArray(row.evidence).length, row.summary, row.pdf_url, row.ann_id]
    );
    const csv = `\uFEFF${[headers, ...body].map((line) => line.map(csvCell).join(",")).join("\r\n")}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    link.href = href;
    link.download = `hedge-${isEvents ? "events" : "announcements"}-filtered-${date}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    showToast(`已导出 ${rows.length.toLocaleString("zh-CN")} 条结果`);
  }

  function bindEvents() {
    $$('[data-view]').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
    $("#search-input").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.page = 1;
      renderCurrentView();
    });
    $("#scope-filter").addEventListener("change", (event) => { state.scope = event.target.value; state.page = 1; renderCurrentView(); });
    $("#approval-filter").addEventListener("change", (event) => { state.approval = event.target.value; state.page = 1; renderCurrentView(); });
    $("#type-filter").addEventListener("change", (event) => { state.entType = event.target.value; state.page = 1; renderCurrentView(); });
    $("#dashboard-year-filter").addEventListener("change", (event) => { state.dashboardYear = event.target.value; renderDashboard(); });
    $("#clear-filters").addEventListener("click", clearFilters);
    $("#export-button").addEventListener("click", exportCurrentResults);
    $("#refresh-button").addEventListener("click", async () => {
      state.announcements = null;
      await loadCoreData();
      showToast("数据已刷新");
    });

    $("#events-body").addEventListener("click", (event) => {
      const row = event.target.closest("[data-event-key]");
      if (!row) return;
      const item = state.events.find((candidate) => candidate.event_key === row.dataset.eventKey);
      if (item) openEventDetail(item);
    });
    $("#events-body").addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      const row = event.target.closest("tr[data-event-key]");
      if (!row) return;
      event.preventDefault();
      const item = state.events.find((candidate) => candidate.event_key === row.dataset.eventKey);
      if (item) openEventDetail(item);
    });
    $("#announcements-body").addEventListener("click", (event) => {
      const row = event.target.closest("[data-ann-id]");
      if (!row) return;
      const item = (state.announcements || []).find((candidate) => candidate.ann_id === row.dataset.annId);
      if (item) openAnnouncementDetail(item);
    });
    $("#announcements-body").addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      const row = event.target.closest("tr[data-ann-id]");
      if (!row) return;
      event.preventDefault();
      const item = (state.announcements || []).find((candidate) => candidate.ann_id === row.dataset.annId);
      if (item) openAnnouncementDetail(item);
    });

    $$("[data-close-drawer]").forEach((button) => button.addEventListener("click", closeDrawer));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && $("#detail-drawer").classList.contains("is-open")) closeDrawer();
    });
    document.addEventListener("click", (event) => {
      const sort = event.target.closest(".sort-button");
      if (sort) {
        const key = sort.dataset.sort;
        if (state.sortKey === key) state.sortDirection = state.sortDirection === "desc" ? "asc" : "desc";
        else { state.sortKey = key; state.sortDirection = key === "company" ? "asc" : "desc"; }
        state.page = 1;
        renderEvents();
      }
      const page = event.target.closest("[data-page]");
      if (page) {
        state.page = Number(page.dataset.page);
        renderCurrentView();
        $(".data-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    $("#prev-page").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; renderCurrentView(); } });
    $("#next-page").addEventListener("click", () => { state.page += 1; renderCurrentView(); });
  }

  let toastTimer;
  function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  function handleFatalError(error) {
    setLoading(false);
    setConnection("error");
    showError(error instanceof Error ? error : new Error(String(error || "页面初始化失败")));
  }

  window.addEventListener("error", (event) => handleFatalError(event.error || new Error(event.message || "页面脚本加载失败")));
  window.addEventListener("unhandledrejection", (event) => handleFatalError(event.reason || new Error("数据请求未能完成")));

  try {
    bindEvents();
    loadCoreData();
  } catch (error) {
    handleFatalError(error);
  }
})();
