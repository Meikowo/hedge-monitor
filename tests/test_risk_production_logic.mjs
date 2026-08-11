import assert from "node:assert/strict";

const {
  buildRiskRows,
  filterRiskRows,
  loadPayload,
  riskRowsToCsv,
  summarizeRiskRows,
} = await import("../web/risk.js");

const apiCalls = [];
globalThis.window = {
  HedgeShell: {
    apiAll: async (table, params) => {
      apiCalls.push({ table, params });
      return [];
    },
  },
};
await loadPayload();
delete globalThis.window;
assert.deepEqual(
  apiCalls.find((call) => call.table === "risk_source_documents")?.params,
  {
    select: "source_doc_id,source_org,source_type,title,publish_date,document_url",
    status: "eq.extracted",
    order: "publish_date.desc.nullslast,source_doc_id.asc",
  },
);

const officialPayload = {
  cases: [{
    case_key: "case:official",
    code: "002176",
    company_name: "江特电机",
    event_date: "2025-12-28",
    first_disclosure_date: "2025-12-29",
    risk_type: "重大衍生品损失",
    instruments: ["商品期货"],
    underlyings: ["碳酸锂"],
    summary: "公司期货交易出现重大损失。",
    amount: 1000,
    currency: "CNY",
    unit: "万元",
    regulatory_action: "监管问询",
    outcome: "待回复",
    case_status: "进行中",
  }],
  documents: [{ case_key: "case:official", source_doc_id: "doc:1", relation_type: "inquiry" }],
  sourceDocuments: [{
    source_doc_id: "doc:1",
    source_org: "SZSE",
    source_type: "inquiry",
    title: "关于江特电机的问询函",
    publish_date: "2025-12-29",
    document_url: "https://example.com/official",
  }],
  evidence: [{
    id: 1,
    case_key: "case:official",
    source_doc_id: "doc:1",
    field: "损失金额",
    page: 2,
    quote: "累计损失超过一千万元。",
    source_url: "https://example.com/official",
    quote_verified: true,
    value_verified: true,
  }],
};

const mediaPayload = {
  reports: [{
    media_key: "media:duplicate",
    code: "002176",
    company_name: "江特电机",
    event_date: "2025-12-28",
    risk_type: "loss",
    instruments: ["商品期货"],
    underlyings: ["碳酸锂"],
    summary: "媒体报道同一事件。",
    verification_status: "officially_corroborated",
    official_case_key: "case:official",
    publish_status: "corroborated",
  }, {
    media_key: "media:standalone",
    code: "300791",
    company_name: "仙乐健康",
    event_date: "2026-04-28",
    risk_type: "loss",
    instruments: ["外汇远期"],
    underlyings: [],
    summary: "据媒体公开报告，外汇远期合同产生损益。",
    verification_status: "media_unverified",
    official_case_key: null,
    publish_status: "published",
  }],
  sources: [{
    source_key: "source:1",
    media_key: "media:standalone",
    publisher_name: "新浪财经",
    source_domain: "finance.sina.com.cn",
    title: "仙乐健康一季度报告",
    published_at: "2026-04-28T00:00:00Z",
    url: "https://example.com/media",
    short_excerpt: "据新浪财经报道：外汇远期合同产生投资收益与公允价值变动。",
    matched_derivative_terms: ["外汇远期"],
    matched_risk_terms: ["损失"],
  }],
};

const rows = buildRiskRows({ ...officialPayload, ...mediaPayload });
assert.equal(rows.length, 2, "officially linked media duplicate should be hidden");
assert.equal(rows[0].id, "media:standalone", "rows should sort newest first");
assert.equal(rows[0].evidenceLevel, "media_unverified");
assert.equal(rows[0].status, "媒体报道／未核实");
assert.equal(rows[0].documents.length, 1);
assert.equal(rows[1].id, "case:official");
assert.equal(rows[1].evidenceLevel, "official_verified");
assert.equal(rows[1].documents[0].title, "关于江特电机的问询函");
assert.equal(rows[1].evidence[0].verified, true);

assert.deepEqual(
  filterRiskRows(rows, { search: "仙乐", year: "2026", riskType: "all", source: "all", status: "all", evidence: "media_unverified" }).map((row) => row.id),
  ["media:standalone"],
);
assert.deepEqual(
  filterRiskRows(rows, { search: "", year: "all", riskType: "重大衍生品损失", source: "all", status: "进行中", evidence: "official_verified" }).map((row) => row.id),
  ["case:official"],
);

assert.deepEqual(summarizeRiskRows(rows), {
  official: 1,
  media: 1,
  companies: 2,
  loss: 2,
});

const csv = riskRowsToCsv([{ ...rows[0], company: "=cmd" }]);
assert.ok(csv.startsWith("\uFEFF"));
assert.match(csv, /"'=cmd"/);
assert.match(csv, /媒体报道／未核实/);
assert.match(csv, /https:\/\/example\.com\/media/);

console.log("risk production logic ok");
