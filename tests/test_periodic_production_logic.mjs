import assert from "node:assert/strict";
import {
  buildPeriodicRows,
  detailMetricsFor,
  displayMetric,
  filterPeriodicRows,
  metricFor,
  periodicRowsToCsv,
  resolveYearFilter
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

const ruixinPayload = {
  reports: [{
    report_id: "r2",
    code: "300828",
    name: "锐新科技",
    report_period: "2025FY",
    fiscal_year: 2025,
    report_type: "annual",
    pdf_url: "https://example.com/ruixin.pdf",
    status: "extracted"
  }],
  profiles: [{
    report_id: "r2",
    disclosure_status: "有数值",
    scopes: ["商品"],
    instruments: ["期货"],
    underlyings: ["铝", "铜", "铜材", "铝材"],
    hedge_accounting_status: "已应用",
    hedge_accounting_types: ["现金流量套期"],
    evidence: [{ page: 31, field: "scopes", quote: "铜、铝期货套期保值" }],
    review_status: "accepted"
  }],
  metrics: [
    {
      report_id: "r2", metric_type: "period_purchase_amount", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铝期货", value: 2379.62, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铝期货报告期购入 2,379.62 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "period_purchase_amount", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铜期货", value: 1125.48, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铜期货报告期购入 1,125.48 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "period_sale_amount", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铝期货", value: 2398.17, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铝期货报告期售出 2,398.17 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "period_sale_amount", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铜期货", value: 1160.47, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铜期货报告期售出 1,160.47 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "derivative_fv_change_pnl", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铝期货", value: 18.55, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铝期货公允价值变动损益 18.55 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "derivative_fv_change_pnl", fact_level: "scope",
      scope: "商品", underlying: null, account_name: "铜期货", value: 34.99, unit: "万元", currency: "CNY",
      time_basis: "报告期", page: 31, raw_text: "铜期货公允价值变动损益 34.99 万元",
      value_verified: true, quote_verified: true
    }
  ],
  accountingItems: []
};

const ruixinRows = buildPeriodicRows(ruixinPayload, []);
assert.equal(ruixinRows.length, 1);
const ruixin = ruixinRows[0];
const purchaseTotal = metricFor(ruixin, "period_purchase_amount");
const saleTotal = metricFor(ruixin, "period_sale_amount");
const fvChangeTotal = metricFor(ruixin, "derivative_fv_change_pnl");
assert.equal(purchaseTotal.value, 3505.1);
assert.equal(saleTotal.value, 3558.64);
assert.equal(fvChangeTotal.value, 53.54);
assert.equal(fvChangeTotal.isAggregated, true);
assert.equal(fvChangeTotal.multipleCount, 2);
assert.equal(displayMetric(fvChangeTotal), "53.54 万元");
assert.equal(
  detailMetricsFor(ruixin).filter((item) => item.metric_type === "derivative_fv_change_pnl").length,
  2,
  "aggregation must not remove the underlying evidence facts"
);

const incompatibleRow = {
  ...ruixin,
  verifiedMetrics: [
    ruixin.verifiedMetrics.find((item) => item.metric_type === "derivative_fv_change_pnl"),
    {
      ...ruixin.verifiedMetrics.find((item) => (
        item.metric_type === "derivative_fv_change_pnl" && item.account_name === "铜期货"
      )),
      unit: "元"
    }
  ]
};
const incompatibleMetric = metricFor(incompatibleRow, "derivative_fv_change_pnl");
assert.equal(incompatibleMetric.value, null);
assert.equal(displayMetric(incompatibleMetric), "2 项事实");

const missingValueRow = {
  ...ruixin,
  verifiedMetrics: ruixin.verifiedMetrics
    .filter((item) => item.metric_type === "derivative_fv_change_pnl")
    .map((item, index) => index === 1 ? { ...item, value: null } : item)
};
const missingValueMetric = metricFor(missingValueRow, "derivative_fv_change_pnl");
assert.equal(missingValueMetric.value, null, "missing values must not be converted to zero");
assert.equal(displayMetric(missingValueMetric), "2 项事实");

const reportTotalRow = {
  ...ruixin,
  verifiedMetrics: [
    {
      report_id: "r2", metric_type: "derivative_asset_fv", fact_level: "report",
      scope: null, account_name: "流动衍生金融资产", value: 10, unit: "万元",
      currency: "CNY", time_basis: "期末", raw_text: "流动衍生金融资产 10 万元",
      value_verified: true, quote_verified: true
    },
    {
      report_id: "r2", metric_type: "derivative_asset_fv", fact_level: "report",
      scope: null, account_name: "衍生金融资产合计", value: 10, unit: "万元",
      currency: "CNY", time_basis: "期末", raw_text: "衍生金融资产合计 10 万元",
      value_verified: true, quote_verified: true
    }
  ]
};
const ambiguousReportTotal = metricFor(reportTotalRow, "derivative_asset_fv");
assert.equal(ambiguousReportTotal.value, null, "report totals must not be summed with possible subtotals");
assert.equal(displayMetric(ambiguousReportTotal), "2 项事实");

const csv = periodicRowsToCsv(ruixinRows);
assert.ok(csv.startsWith("\uFEFF"), "CSV must include a UTF-8 BOM");
assert.match(csv, /"公司代码","公司名称"/);
assert.match(csv, /"300828","锐新科技"/);
assert.match(csv, /"3505\.1","CNY","万元","2"/);
assert.match(csv, /"3558\.64","CNY","万元","2"/);
assert.match(csv, /"53\.54","CNY","万元","2"/);
assert.match(csv, /"https:\/\/example\.com\/ruixin\.pdf"/);
const missingValueCsv = periodicRowsToCsv([missingValueRow]);
assert.match(missingValueCsv, /"","","","2","已应用"/, "ambiguous metrics must export blank, not zero");
const escapedCsv = periodicRowsToCsv([{
  ...ruixin,
  report: { ...ruixin.report, name: '锐新科技,"测试"' }
}]);
assert.match(escapedCsv, /"锐新科技,""测试"""/, "CSV must escape commas and quotes");
const negativeCsv = periodicRowsToCsv([{
  ...ruixin,
  verifiedMetrics: [
    ...ruixin.verifiedMetrics,
    {
      report_id: "r2", metric_type: "reported_derivative_comprehensive_pnl",
      fact_level: "scope", scope: "商品", value: -12.34, unit: "万元", currency: "CNY",
      time_basis: "报告期", raw_text: "测试综合损益 -12.34 万元",
      value_verified: true, quote_verified: true
    }
  ]
}]);
assert.match(negativeCsv, /"-12\.34","CNY","万元","1"/, "negative numeric values must remain numeric in CSV");
const formulaSafeCsv = periodicRowsToCsv([{
  ...ruixin,
  report: { ...ruixin.report, name: "\t=FORMULA" }
}]);
assert.match(formulaSafeCsv, /"'\t=FORMULA"/, "whitespace-prefixed spreadsheet formulas must be neutralized");
assert.equal(resolveYearFilter([2025, 2024], "2025"), "2025");
assert.equal(resolveYearFilter([2025, 2024], "2023"), "all");

console.log("periodic production logic ok");
