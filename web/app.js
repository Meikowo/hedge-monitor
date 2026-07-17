(() => {
  "use strict";

  const config = window.HEDGE_CONFIG || {};
  const state = {
    view: "events",
    announcements: [],
    events: [],
    statuses: [],
    query: "",
    scope: "all",
    role: "all",
    loadedAt: null
  };

  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const asArray = (value) => Array.isArray(value) ? value : [];
  const join = (value, fallback = "未披露") => asArray(value).length ? asArray(value).join(" / ") : fallback;
  const formatDate = (value) => value ? String(value).slice(0, 10).replace(/-/g, ".") : "—";
  const formatAmount = (amount, currency = "CNY") => {
    if (amount === null || amount === undefined || amount === "") return "未披露";
    const numeric = Number(amount);
    if (!Number.isFinite(numeric)) return escapeHtml(amount);
    const unit = currency === "CNY" ? "¥" : `${currency} `;
    if (Math.abs(numeric) >= 100000000) return `${unit}${(numeric / 100000000).toFixed(2).replace(/\.00$/, "")}亿`;
    if (Math.abs(numeric) >= 10000) return `${unit}${(numeric / 10000).toFixed(2).replace(/\.00$/, "")}万`;
    return `${unit}${numeric.toLocaleString("zh-CN")}`;
  };
  const scopeClass = (scope) => scope === "商品" ? "legend-dot--commodity" : scope === "外汇" ? "legend-dot--fx" : "legend-dot--rate";

  async function api(path, params = {}) {
    if (!config.supabaseUrl || !config.supabaseKey) throw new Error("缺少 Supabase 只读配置");
    const url = new URL(`${config.supabaseUrl}/rest/v1/${path}`);
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
    const response = await fetch(url, {
      headers: {
        apikey: config.supabaseKey,
        Authorization: `Bearer ${config.supabaseKey}`
      }
    });
    if (!response.ok) throw new Error(`数据接口 ${response.status}`);
    return response.json();
  }

  async function loadData() {
    setLoading(true);
    try {
      const [announcements, events, statuses] = await Promise.all([
        api("v_ann_flow", { select: "*", status: "eq.extracted", order: "ann_date.desc", limit: "1000" }),
        api("v_events", { select: "event_key,code,name,anchor_year,scope,plan_label,stage,approval_level,first_ann_date,latest_ann_date,ann_count,ann_roles,instruments,underlyings,venue,period_text,is_revolving,use_own_funds,quota,quota_source_ann_id", order: "latest_ann_date.desc", limit: "1000" }),
        api("announcements", { select: "status", limit: "5000" })
      ]);
      state.announcements = announcements;
      state.events = events;
      state.statuses = statuses;
      state.loadedAt = new Date();
      renderAll();
      setLoading(false);
    } catch (error) {
      setLoading(false);
      $("#error-state").hidden = false;
      $("#error-message").textContent = error.message || "请检查 Supabase 只读配置。";
      $("#loading-state").hidden = true;
    }
  }

  function setLoading(isLoading) {
    $("#loading-state").hidden = !isLoading;
    if (isLoading) {
      $("#error-state").hidden = true;
      $("#event-list").hidden = true;
      $("#announcement-list").hidden = true;
    }
  }

  function statusCount(status) {
    return state.statuses.filter((row) => row.status === status).length;
  }

  function renderMetrics() {
    $("#metric-extracted").textContent = statusCount("extracted").toLocaleString("zh-CN");
    $("#metric-events").textContent = state.events.length.toLocaleString("zh-CN");
    $("#metric-pending").textContent = statusCount("pending").toLocaleString("zh-CN");
    $("#metric-failed").textContent = statusCount("failed").toLocaleString("zh-CN");
    const dates = state.announcements.map((row) => row.ann_date).filter(Boolean).sort();
    $("#coverage-label").textContent = dates.length ? `${formatDate(dates[dates.length - 1])} 数据已接入` : "等待数据接入";
    $("#updated-label").textContent = state.loadedAt ? `最后读取 ${state.loadedAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : "读取 Supabase 只读视图";
  }

  function filteredEvents() {
    const needle = state.query.trim().toLowerCase();
    return state.events.filter((event) => {
      const text = [event.name, event.code, event.plan_label, event.stage, join(event.scope), join(event.instruments)].join(" ").toLowerCase();
      const matchesQuery = !needle || text.includes(needle);
      const matchesScope = state.scope === "all" || asArray(event.scope).includes(state.scope);
      const matchesRole = state.role === "all" || asArray(event.ann_roles).includes(state.role);
      return matchesQuery && matchesScope && matchesRole;
    });
  }

  function filteredAnnouncements() {
    const needle = state.query.trim().toLowerCase();
    return state.announcements.filter((row) => {
      const text = [row.name, row.code, row.title, row.summary, join(row.scope)].join(" ").toLowerCase();
      const matchesQuery = !needle || text.includes(needle);
      const matchesScope = state.scope === "all" || asArray(row.scope).includes(state.scope);
      const matchesRole = state.role === "all" || row.ann_role === state.role;
      return matchesQuery && matchesScope && matchesRole;
    });
  }

  function quotaSummary(event) {
    const quotas = asArray(event.quota).filter((item) => item && item.amount !== null && item.amount !== undefined);
    if (!quotas.length) return { value: "未披露", basis: "额度待原文确认" };
    const first = quotas[0];
    return { value: formatAmount(first.amount, first.currency), basis: first.basis || "已抽取额度" };
  }

  function renderEvents() {
    const events = filteredEvents();
    $("#result-count").textContent = `${events.length} 个事件`;
    if (!events.length) {
      $("#event-list").innerHTML = `<div class="empty-copy">没有匹配的事件。换一个公司、代码或类别试试。</div>`;
      return;
    }
    $("#event-list").innerHTML = events.map((event) => {
      const quota = quotaSummary(event);
      const firstScope = asArray(event.scope)[0] || "其他";
      const tags = asArray(event.scope).map((item) => `<span class="tag"><i class="legend-dot ${scopeClass(item)}"></i>${escapeHtml(item)}</span>`).join("");
      return `<article class="event-row">
        <div class="event-date"><span>${escapeHtml(event.anchor_year || "—")}</span><strong>${escapeHtml(formatDate(event.latest_ann_date).slice(5))}</strong></div>
        <div class="event-main">
          <div class="event-company"><strong>${escapeHtml(event.name || "未命名公司")}</strong><span class="code-pill">${escapeHtml(event.code || "—")}</span></div>
          <h3>${escapeHtml(event.stage || "套保业务事件")}</h3>
          <div class="event-meta">${tags}<span class="tag tag--accent">${escapeHtml(event.approval_level || "审批未披露")}</span><span class="tag">${escapeHtml(event.ann_count || 0)} 条关联公告</span></div>
        </div>
        <div class="event-quota"><span>${escapeHtml(firstScope)} · ${escapeHtml(quota.basis)}</span><strong>${escapeHtml(quota.value)}</strong><small>${escapeHtml(event.period_text || "期限未披露")}</small></div>
        <button class="row-action" type="button" data-event-key="${escapeHtml(event.event_key)}">查看证据&nbsp;→</button>
      </article>`;
    }).join("");
  }

  function renderAnnouncements() {
    const rows = filteredAnnouncements();
    $("#result-count").textContent = `${rows.length} 条公告`;
    if (!rows.length) {
      $("#announcement-list").innerHTML = `<div class="empty-copy">没有匹配的公告。换一个公司、代码或类别试试。</div>`;
      return;
    }
    $("#announcement-list").innerHTML = rows.map((row) => {
      const evidenceCount = asArray(row.evidence).length;
      return `<article class="announcement-row">
        <div class="announcement-date">${escapeHtml(formatDate(row.ann_date))}</div>
        <div class="announcement-title"><strong>${escapeHtml(row.title)}</strong><small>${escapeHtml(row.name || "未命名公司")} · ${escapeHtml(row.code || "—")}</small></div>
        <div class="announcement-role">${escapeHtml(row.ann_role || "其他")}</div>
        <div class="announcement-check"><span class="check-pill">${evidenceCount} 条证据</span><span class="check-pill">${escapeHtml(row.confidence || "—")} 置信度</span></div>
        <button class="row-action" type="button" data-ann-id="${escapeHtml(row.ann_id)}">打开详情&nbsp;→</button>
      </article>`;
    }).join("");
  }

  function renderAll() {
    renderMetrics();
    $("#view-title").textContent = state.view === "events" ? "近期套保事件" : "公告原流";
    $("#event-list").hidden = state.view !== "events";
    $("#announcement-list").hidden = state.view !== "announcements";
    if (state.view === "events") renderEvents(); else renderAnnouncements();
  }

  function renderDrawer(title, subtitle, body) {
    $("#drawer-content").innerHTML = `<div class="drawer-kicker">EVIDENCE TRACE</div><h2>${escapeHtml(title)}</h2><div class="drawer-subtitle">${escapeHtml(subtitle)}</div>${body}`;
    $("#detail-drawer").classList.add("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
  }

  function openEvent(event) {
    const quotas = asArray(event.quota);
    const evidence = quotas.length ? `<table class="quota-table"><thead><tr><th>口径</th><th>金额</th><th>证据</th></tr></thead><tbody>${quotas.map((item) => `<tr><td>${escapeHtml(item.scope || "综合")}<br /><span class="muted">${escapeHtml(item.basis || "未披露")}</span></td><td class="amount">${escapeHtml(formatAmount(item.amount, item.currency))}</td><td>${item.amount_verified ? "金额已回验" : "待回验"}<br />${escapeHtml(item.raw_text || "未披露")}</td></tr>`).join("")}</tbody></table>` : `<p class="empty-copy">该事件暂未抽取出可统计额度，页面会保留“未披露”，不会显示为 0。</p>`;
    const meta = `<div class="drawer-meta"><div><span>事件阶段</span><strong>${escapeHtml(event.stage || "未披露")}</strong></div><div><span>审批层级</span><strong>${escapeHtml(event.approval_level || "未披露")}</strong></div><div><span>关联公告</span><strong>${escapeHtml(event.ann_count || 0)} 条</strong></div><div><span>时间范围</span><strong>${escapeHtml(formatDate(event.first_ann_date))} — ${escapeHtml(formatDate(event.latest_ann_date))}</strong></div></div>`;
    renderDrawer(event.name || "未命名公司", `${event.code || "—"} · ${join(event.scope)} · ${event.anchor_year || "—"}`, `<section class="drawer-section"><div class="drawer-label">事件摘要</div><p class="drawer-summary">${escapeHtml(`${event.stage || "套保业务"}，${join(event.instruments)}，${event.period_text || "期限未披露"}。`)}</p>${meta}</section><section class="drawer-section"><div class="drawer-label">额度与口径</div>${evidence}</section><section class="drawer-section"><div class="drawer-label">关联角色</div><div class="event-meta">${asArray(event.ann_roles).map((role) => `<span class="tag">${escapeHtml(role)}</span>`).join("")}</div></section>`);
  }

  function openAnnouncement(row) {
    const evidence = asArray(row.evidence);
    const evidenceHtml = evidence.length ? evidence.map((item) => `<div class="evidence-item"><small>第 ${escapeHtml(item.page || "—")} 页 · ${escapeHtml(item.field || "证据")}</small><p>“${escapeHtml(item.quote || "未提供引文") }”</p></div>`).join("") : `<p class="empty-copy">当前记录没有可展示的证据引文。</p>`;
    const tags = `${asArray(row.scope).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}<span class="tag tag--accent">${escapeHtml(row.ann_role || "其他")}</span>`;
    renderDrawer(row.name || "未命名公司", `${row.code || "—"} · ${formatDate(row.ann_date)}`, `<section class="drawer-section"><div class="event-meta">${tags}</div><p class="drawer-summary">${escapeHtml(row.summary || "暂无摘要")}</p><div class="drawer-meta"><div><span>期限</span><strong>${escapeHtml(row.period_text || "未披露")}</strong></div><div><span>置信度</span><strong>${escapeHtml(row.confidence || "—")}</strong></div><div><span>场所</span><strong>${escapeHtml(row.venue || "未披露")}</strong></div><div><span>循环额度</span><strong>${row.is_revolving === true ? "是" : row.is_revolving === false ? "否" : "未披露"}</strong></div></div></section><section class="drawer-section"><div class="drawer-label">证据引文</div>${evidenceHtml}${row.pdf_url ? `<a class="pdf-link" href="${escapeHtml(row.pdf_url)}" target="_blank" rel="noreferrer">打开原始 PDF&nbsp;↗</a>` : ""}</section>`);
  }

  function closeDrawer() {
    $("#detail-drawer").classList.remove("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
  }

  function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  document.addEventListener("click", (event) => {
    const nav = event.target.closest("[data-view]");
    if (nav) {
      state.view = nav.dataset.view;
      document.querySelectorAll(".nav-link").forEach((item) => item.classList.toggle("is-active", item === nav));
      renderAll();
      return;
    }
    const eventButton = event.target.closest("[data-event-key]");
    if (eventButton) {
      const item = state.events.find((row) => row.event_key === eventButton.dataset.eventKey);
      if (item) openEvent(item);
      return;
    }
    const annButton = event.target.closest("[data-ann-id]");
    if (annButton) {
      const item = state.announcements.find((row) => row.ann_id === annButton.dataset.annId);
      if (item) openAnnouncement(item);
      return;
    }
    if (event.target.closest("[data-close-drawer]")) closeDrawer();
  });

  $("#search-input").addEventListener("input", (event) => { state.query = event.target.value; renderAll(); });
  $("#scope-filter").addEventListener("change", (event) => { state.scope = event.target.value; renderAll(); });
  $("#role-filter").addEventListener("change", (event) => { state.role = event.target.value; renderAll(); });
  $("#refresh-button").addEventListener("click", () => { showToast("正在刷新数据…"); loadData(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });

  loadData();
})();
