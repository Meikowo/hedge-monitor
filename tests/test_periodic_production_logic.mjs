import assert from "node:assert/strict";
import {
  buildPeriodicRows,
  detailMetricsFor,
  displayMetric,
  filterPeriodicRows,
  metricFor
} from "../web/periodic.js";

const payload = {
  reports: [{
    report_id: "r1",
    code: "688223",
    name: "晶科能源",
    report_period: "2025FY",
    fiscal_year: 2025,
    report_type: "年度报告",
    pdf_url: "https://example.com/jinko.pdf",
    status: "extracted"
  }],
  profiles: [{
    report_id: "r1",
    disclosure_status: "有数值",
    scopes: ["商品", "外汇"],
    instruments: ["期货", "普通远期"],
    underlyings: ["铝", "外汇"],
    hedge_accounting_status: "未应用",
    hedge_accounting_types: [],
    non_application_reason: null,
    evidence: [{ page: 43, field: "scopes", quote: "商品和外汇衍生品" }],
    review_status: "accepted"
  }],
  metrics: [
    {
      report_id: "r1", metric_type: "period_purchase_amount", fact_level: "scope",
      scope: "商品", value: 18083.61, unit: "万元", currency: "CNY",
      page: 43, raw_text: "期货 报告期内购入金额 18,083.61",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r1", metric_type: "period_purchase_amount", fact_level: "scope",
      scope: "外汇", value: 23025.19, unit: "万元", currency: "CNY",
      page: 43, raw_text: "普通远期 报告期内购入金额 23,025.19",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r1", metric_type: "derivative_asset_fv", fact_level: "report",
      scope: null, value: 58922522.23, unit: "元", currency: "CNY",
      page: 260, raw_text: "衍生金融资产 58,922,522.23",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r1", metric_type: "derivative_liability_fv", fact_level: "report",
      scope: null, value: 56128746.61, unit: "元", currency: "CNY",
      page: 261, raw_text: "衍生金融负债 56,128,746.61",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r1", metric_type: "margin_end_cash", fact_level: "report",
      scope: null, value: 999, unit: "元", currency: "CNY",
      page: 200, raw_text: "未通过校验的保证金",
      value_verified: false, quote_verified: true
    }
  ],
  accountingItems: [{
    report_id: "r1",
    application_status: "未应用",
    accounting_type: null,
    page: 259,
    quote: "公司未应用套期会计",
    quote_verified: true,
    need_review: false
  }]
};

const eventRows = [{
  event_key: "688223|2025|商品",
  code: "688223",
  name: "晶科能源",
  anchor_year: 2025,
  scope: ["商品"],
  quota: [{ amount: 100000000, currency: "CNY", basis: "保证金最高占用额" }],
  province: "江西",
  ent_type: "民企",
  ind_l1: "电力设备"
}];

const rows = buildPeriodicRows(payload, eventRows);
assert.equal(rows.length, 2);
assert.deepEqual(rows.map((row) => row.scope), ["商品", "外汇"]);

const commodity = rows.find((row) => row.scope === "商品");
assert.equal(metricFor(commodity, "period_purchase_amount").value, 18083.61);
assert.equal(metricFor(commodity, "derivative_asset_fv").isReportTotal, true);
assert.equal(metricFor(commodity, "margin_end_cash"), null, "unverified metrics must be excluded");
assert.equal(commodity.hedgeAccountingStatus, "未应用");
assert.equal(commodity.nonApplicationReason, null);
assert.equal(commodity.companyMeta.province, "江西");
assert.equal(commodity.planEvents.length, 1);
assert.deepEqual(
  detailMetricsFor(commodity)
    .filter((item) => item.metric_type === "period_purchase_amount")
    .map((item) => item.scope),
  ["商品"],
  "detail must not mix another scope into the selected row"
);

const net = metricFor(commodity, "derivative_net_fv");
assert.equal(net.value, 2793775.62);
assert.equal(net.unit, "元");
assert.equal(net.isComputed, true);
assert.equal(net.isReportTotal, true);
assert.match(displayMetric(net), /2,793,775\.62 元/);
assert.equal(displayMetric(null), "未披露");

assert.equal(filterPeriodicRows(rows, {
  query: "晶科",
  year: "2025",
  scope: "商品",
  accounting: "未应用",
  evidence: "完整"
}).length, 1);
assert.equal(filterPeriodicRows(rows, {
  query: "",
  year: "all",
  scope: "外汇",
  accounting: "已应用",
  evidence: "all"
}).length, 0);

console.log("periodic production logic ok");
