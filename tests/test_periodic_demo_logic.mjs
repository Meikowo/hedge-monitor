import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const context = vm.createContext({ console });
const dataSource = fs.readFileSync(new URL("../web-demo/periodic-actuals/data.js", import.meta.url), "utf8");
const appSource = fs.readFileSync(new URL("../web-demo/periodic-actuals/app.js", import.meta.url), "utf8");
vm.runInContext(dataSource, context, { filename: "data.js" });
vm.runInContext(appSource, context, { filename: "app.js" });

const periodicActualRows = context.periodicActualRows;
const {
  accountingLabel,
  displayValue,
  evidenceProgress,
  filterRows,
  renderDrawer,
  renderTableRow,
} = context.PeriodicActualsDemo;

assert.equal(periodicActualRows.length, 7, "fixture should cover seven category-level research rows");

const jinkoRows = filterRows(periodicActualRows, {
  period: "2025FY",
  category: "外汇",
  accounting: "未应用",
  match: "部分匹配",
  search: "晶科",
});
assert.deepEqual(Array.from(jinkoRows, (row) => row.id), ["jinko-2025fy-fx"]);

const allJinkoRows = filterRows(periodicActualRows, { search: "晶科能源" });
assert.deepEqual(Array.from(allJinkoRows, (row) => row.id), [
  "jinko-2025fy-fx",
  "jinko-2025fy-commodity",
]);

const copperRows = filterRows(periodicActualRows, {
  period: "all",
  category: "all",
  accounting: "all",
  match: "all",
  search: "铜",
});
assert.deepEqual(Array.from(copperRows, (row) => row.id), ["jiangxi-copper-2025fy-commodity"]);

assert.equal(displayValue(null, "万元"), "未披露");
assert.equal(displayValue(-3474.88, "万元"), "-3,474.88 万元");

const jinko = periodicActualRows.find((row) => row.id === "jinko-2025fy-fx");
assert.ok(jinko);
assert.equal(jinko.purchaseAmount, 23025.19);
assert.equal(jinko.saleAmount, 25141.68);
assert.equal(jinko.netFairValue, -2166.24);
assert.equal(jinko.comprehensivePnl, -9875.41);
assert.equal(jinko.disposalIncome, null);
assert.equal(jinko.fvChangePnl, null);
assert.equal(jinko.reportTotals.disposalIncome, 2392.96);
assert.equal(jinko.reportTotals.fvChangePnl, -5867.84);
assert.equal(jinko.reportTotals.derivativeAssets, 5892.25);
assert.equal(jinko.reportTotals.derivativeLiabilities, 5612.87);
assert.equal(jinko.reportTotals.netFairValue, 279.38);
assert.equal(jinko.marginBalance, null);
assert.equal(accountingLabel(jinko), "未应用 · 原因未披露");
assert.equal(evidenceProgress(jinko), "7/7");

const jinkoCommodity = periodicActualRows.find((row) => row.id === "jinko-2025fy-commodity");
assert.ok(jinkoCommodity);
assert.equal(jinkoCommodity.category, "商品");
assert.deepEqual(Array.from(jinkoCommodity.instrument), ["期货"]);
assert.equal(jinkoCommodity.purchaseAmount, 18083.61);
assert.equal(jinkoCommodity.saleAmount, 21655.95);
assert.equal(jinkoCommodity.netFairValue, 2445.61);
assert.equal(jinkoCommodity.comprehensivePnl, 6400.53);

const tableRow = renderTableRow(jinko);
assert.match(tableRow, /data-row-id="jinko-2025fy-fx"/);
assert.match(tableRow, /-9,875\.41 万元/);
assert.match(tableRow, /报告级合计/);
assert.match(tableRow, /期末保证金未披露/);
assert.match(tableRow, /衍生金融资产：报告级合计/);
assert.match(tableRow, /衍生金融负债：报告级合计/);
assert.match(tableRow, /公允价值净额：-2,166\.24 万元/);
assert.match(tableRow, /未应用/);
assert.match(tableRow, /7\/7/);

const drawer = renderDrawer(jinko);
for (const heading of ["公告计划", "定期报告实际", "套期会计", "核对与证据"]) {
  assert.match(drawer, new RegExp(heading));
}
assert.match(drawer, /2,392\.96 − 5,867\.84 = −3,474\.88 万元/);
assert.match(drawer, /报告级合计（未按类别分摊）/);
assert.match(drawer, /期末保证金/);
assert.match(drawer, /43–44/);
assert.match(drawer, /235–236/);
assert.match(drawer, /259/);
assert.match(drawer, /260–261/);

const headerFiltered = filterRows(periodicActualRows, {
  company: "晶科能源",
  underlying: "期货",
  netState: "positive",
  pnlState: "positive",
  disposalState: "missing",
  fvState: "missing",
  evidenceState: "complete",
});
assert.deepEqual(Array.from(headerFiltered, (row) => row.id), ["jinko-2025fy-commodity"]);

const marginSnapshotRows = filterRows(periodicActualRows, {
  marginState: "positive",
  assetState: "positive",
  liabilityState: "positive",
});
assert.ok(marginSnapshotRows.some((row) => row.id === "jiangxi-copper-2025fy-commodity"));
assert.ok(!marginSnapshotRows.some((row) => row.id === "jinko-2025fy-fx"));

const missingFlow = filterRows(periodicActualRows, { flowState: "missing" });
assert.deepEqual(Array.from(missingFlow, (row) => row.id), ["sample-manufacturing-2024fy-rates"]);

const cashFlowAccounting = filterRows(periodicActualRows, { method: "现金流量套期" });
assert.deepEqual(Array.from(cashFlowAccounting, (row) => row.id), [
  "jiangxi-copper-2025fy-commodity",
  "sample-air-2025fy-fx",
  "sample-manufacturing-2024fy-rates",
]);

const columnIntersection = filterRows(periodicActualRows, {
  columnPeriod: "2024FY",
  columnAccounting: "需复核",
  columnMatch: "仅有实际",
});
assert.deepEqual(Array.from(columnIntersection, (row) => row.id), ["sample-manufacturing-2024fy-rates"]);

console.log("periodic actuals demo logic ok");
