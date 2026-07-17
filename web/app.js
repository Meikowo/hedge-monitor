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
  const join = (value, fallback = "鏈姭闇?) => asArray(value).length ? asArray(value).join(" / ") : fallback;
  const formatDate = (value) => value ? String(value).slice(0, 10).replace(/-/g, ".") : "鈥?;
  const formatAmount = (amount, currency = "CNY") => {
    if (amount === null || amount === undefined || amount === "") return "鏈姭闇?;
    const numeric = Number(amount);
    if (!Number.isFinite(numeric)) return escapeHtml(amount);
    const unit = currency === "CNY" ? "楼" : `${currency} `;
    if (Math.abs(numeric) >= 100000000) return `${unit}${(numeric / 100000000).toFixed(2).replace(/\.00$/, "")}浜縛;
    if (Math.abs(numeric) >= 10000) return `${unit}${(numeric / 10000).toFixed(2).replace(/\.00$/, "")}涓嘸;
    return `${unit}${numeric.toLocaleString("zh-CN")}`;
  };
  const scopeClass = (scope) => scope === "鍟嗗搧" ? "legend-dot--commodity" : scope === "澶栨眹" ? "legend-dot--fx" : "legend-dot--rate";

  async function api(path, params = {}) {
    if (!config.supabaseUrl || !config.supabaseKey) throw new Error("缂哄皯 Supabase 鍙閰嶇疆");
    const url = new URL(`${config.supabaseUrl}/rest/v1/${path}`);
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
    const response = await fetch(url, {
      headers: {
        apikey: config.supabaseKey,
        Authorization: `Bearer ${config.supabaseKey}`
      }
    });
    if (!response.ok) throw new Error(`鏁版嵁鎺ュ彛 ${response.status}`);
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
      $("#error-message").textContent = error.message || "璇锋鏌?Supabase 鍙閰嶇疆銆?;
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
    $("#coverage-label").textContent = dates.length ? `${formatDate(dates[dates.length - 1])} 鏁版嵁宸叉帴鍏 : "绛夊緟鏁版嵁鎺ュ叆";
    $("#updated-label").textContent = state.loadedAt ? `鏈€鍚庤鍙?${state.loadedAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : "璇诲彇 Supabase 鍙瑙嗗浘";
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
    if (!quotas.length) return { value: "鏈姭闇?, basis: "棰濆害寰呭師鏂囩‘璁? };
    const first = quotas[0];
    return { value: formatAmount(first.amount, first.currency), basis: first.basis || "宸叉娊鍙栭搴? };
  }

  function renderEvents() {
    const events = filteredEvents();
    $("#result-count").textContent = `${events.length} 涓簨浠禶;
    if (!events.length) {
      $("#event-list").innerHTML = `<div class="empty-copy">娌℃湁鍖归厤鐨勪簨浠躲€傛崲涓€涓叕鍙搞€佷唬鐮佹垨绫诲埆璇曡瘯銆?/div>`;
      return;
    }
    $("#event-list").innerHTML = events.map((event) => {
      const quota = quotaSummary(event);
      const firstScope = asArray(event.scope)[0] || "鍏朵粬";
      const tags = asArray(event.scope).map((item) => `<span class="tag"><i class="legend-dot ${scopeClass(item)}"></i>${escapeHtml(item)}</span>`).join("");
      return `<article class="event-row">
        <div class="event-date"><span>${escapeHtml(event.anchor_year || "鈥?)}</span><strong>${escapeHtml(formatDate(event.latest_ann_date).slice(5))}</strong></div>
        <div class="event-main">
          <div class="event-company"><strong>${escapeHtml(event.name || "鏈懡鍚嶅叕鍙?)}</strong><span class="code-pill">${escapeHtml(event.code || "鈥?)}</span></div>
          <h3>${escapeHtml(event.stage || "濂椾繚涓氬姟浜嬩欢")}</h3>
          <div class="event-meta">${tags}<span class="tag tag--accent">${escapeHtml(event.approval_level || "瀹℃壒鏈姭闇?)}</span><span class="tag">${escapeHtml(event.ann_count || 0)} 鏉″叧鑱斿叕鍛?/span></div>
        </div>
        <div class="event-quota"><span>${escapeHtml(firstScope)} 路 ${escapeHtml(quota.basis)}</span><strong>${escapeHtml(quota.value)}</strong><small>${escapeHtml(event.period_text || "鏈熼檺鏈姭闇?)}</small></div>
        <button class="row-action" type="button" data-event-key="${escapeHtml(event.event_key)}">鏌ョ湅璇佹嵁&nbsp;鈫?/button>
      </article>`;
    }).join("");
  }

  function renderAnnouncements() {
    const rows = filteredAnnouncements();
    $("#result-count").textContent = `${rows.length} 鏉″叕鍛奰;
    if (!rows.length) {
      $("#announcement-list").innerHTML = `<div class="empty-copy">娌℃湁鍖归厤鐨勫叕鍛娿€傛崲涓€涓叕鍙搞€佷唬鐮佹垨绫诲埆璇曡瘯銆?/div>`;
      return;
    }
    $("#announcement-list").innerHTML = rows.map((row) => {
      const evidenceCount = asArray(row.evidence).length;
      return `<article class="announcement-row">
        <div class="announcement-date">${escapeHtml(formatDate(row.ann_date))}</div>
        <div class="announcement-title"><strong>${escapeHtml(row.title)}</strong><small>${escapeHtml(row.name || "鏈懡鍚嶅叕鍙?)} 路 ${escapeHtml(row.code || "鈥?)}</small></div>
        <div class="announcement-role">${escapeHtml(row.ann_role || "鍏朵粬")}</div>
        <div class="announcement-check"><span class="check-pill">${evidenceCount} 鏉¤瘉鎹?/span><span class="check-pill">${escapeHtml(row.confidence || "鈥?)} 缃俊搴?/span></div>
        <button class="row-action" type="button" data-ann-id="${escapeHtml(row.ann_id)}">鎵撳紑璇︽儏&nbsp;鈫?/button>
      </article>`;
    }).join("");
  }

  function renderAll() {
    renderMetrics();
    $("#view-title").textContent = state.view === "events" ? "杩戞湡濂椾繚浜嬩欢" : "鍏憡鍘熸祦";
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
    const evidence = quotas.length ? `<table class="quota-table"><thead><tr><th>鍙ｅ緞</th><th>閲戦</th><th>璇佹嵁</th></tr></thead><tbody>${quotas.map((item) => `<tr><td>${escapeHtml(item.scope || "缁煎悎")}<br /><span class="muted">${escapeHtml(item.basis || "鏈姭闇?)}</span></td><td class="amount">${escapeHtml(formatAmount(item.amount, item.currency))}</td><td>${item.amount_verified ? "閲戦宸插洖楠? : "寰呭洖楠?}<br />${escapeHtml(item.raw_text || "鏈姭闇?)}</td></tr>`).join("")}</tbody></table>` : `<p class="empty-copy">璇ヤ簨浠舵殏鏈娊鍙栧嚭鍙粺璁￠搴︼紝椤甸潰浼氫繚鐣欌€滄湭鎶湶鈥濓紝涓嶄細鏄剧ず涓?0銆?/p>`;
    const meta = `<div class="drawer-meta"><div><span>浜嬩欢闃舵</span><strong>${escapeHtml(event.stage || "鏈姭闇?)}</strong></div><div><span>瀹℃壒灞傜骇</span><strong>${escapeHtml(event.approval_level || "鏈姭闇?)}</strong></div><div><span>鍏宠仈鍏憡</span><strong>${escapeHtml(event.ann_count || 0)} 鏉?/strong></div><div><span>鏃堕棿鑼冨洿</span><strong>${escapeHtml(formatDate(event.first_ann_date))} 鈥?${escapeHtml(formatDate(event.latest_ann_date))}</strong></div></div>`;
    renderDrawer(event.name || "鏈懡鍚嶅叕鍙?, `${event.code || "鈥?} 路 ${join(event.scope)} 路 ${event.anchor_year || "鈥?}`, `<section class="drawer-section"><div class="drawer-label">浜嬩欢鎽樿</div><p class="drawer-summary">${escapeHtml(`${event.stage || "濂椾繚涓氬姟"}锛?{join(event.instruments)}锛?{event.period_text || "鏈熼檺鏈姭闇?}銆俙)}</p>${meta}</section><section class="drawer-section"><div class="drawer-label">棰濆害涓庡彛寰?/div>${evidence}</section><section class="drawer-section"><div class="drawer-label">鍏宠仈瑙掕壊</div><div class="event-meta">${asArray(event.ann_roles).map((role) => `<span class="tag">${escapeHtml(role)}</span>`).join("")}</div></section>`);
  }

  function openAnnouncement(row) {
    const evidence = asArray(row.evidence);
    const evidenceHtml = evidence.length ? evidence.map((item) => `<div class="evidence-item"><small>绗?${escapeHtml(item.page || "鈥?)} 椤?路 ${escapeHtml(item.field || "璇佹嵁")}</small><p>鈥?{escapeHtml(item.quote || "鏈彁渚涘紩鏂?) }鈥?/p></div>`).join("") : `<p class="empty-copy">褰撳墠璁板綍娌℃湁鍙睍绀虹殑璇佹嵁寮曟枃銆?/p>`;
    const tags = `${asArray(row.scope).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}<span class="tag tag--accent">${escapeHtml(row.ann_role || "鍏朵粬")}</span>`;
    renderDrawer(row.name || "鏈懡鍚嶅叕鍙?, `${row.code || "鈥?} 路 ${formatDate(row.ann_date)}`, `<section class="drawer-section"><div class="event-meta">${tags}</div><p class="drawer-summary">${escapeHtml(row.summary || "鏆傛棤鎽樿")}</p><div class="drawer-meta"><div><span>鏈熼檺</span><strong>${escapeHtml(row.period_text || "鏈姭闇?)}</strong></div><div><span>缃俊搴?/span><strong>${escapeHtml(row.confidence || "鈥?)}</strong></div><div><span>鍦烘墍</span><strong>${escapeHtml(row.venue || "鏈姭闇?)}</strong></div><div><span>寰幆棰濆害</span><strong>${row.is_revolving === true ? "鏄? : row.is_revolving === false ? "鍚? : "鏈姭闇?}</strong></div></div></section><section class="drawer-section"><div class="drawer-label">璇佹嵁寮曟枃</div>${evidenceHtml}${row.pdf_url ? `<a class="pdf-link" href="${escapeHtml(row.pdf_url)}" target="_blank" rel="noreferrer">鎵撳紑鍘熷 PDF&nbsp;鈫?/a>` : ""}</section>`);
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
  $("#refresh-button").addEventListener("click", () => { showToast("姝ｅ湪鍒锋柊鏁版嵁鈥?); loadData(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });

  loadData();
})();
