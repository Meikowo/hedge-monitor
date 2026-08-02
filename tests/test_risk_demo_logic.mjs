import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const context = vm.createContext({ console });
const dataSource = fs.readFileSync(new URL("../web-demo/risk-cases/data.js", import.meta.url), "utf8");
const appSource = fs.readFileSync(new URL("../web-demo/risk-cases/app.js", import.meta.url), "utf8");
vm.runInContext(dataSource, context, { filename: "data.js" });
vm.runInContext(appSource, context, { filename: "app.js" });

const riskCaseRows = context.riskCaseRows;
const {
  casesToCsv,
  displayAmount,
  filterCases,
  renderDrawer,
  renderTableRow,
  sortDocuments,
  summarizeRows,
} = context.RiskCasesDemo;

assert.equal(riskCaseRows.length, 7, "fixture should contain six official shapes and one media shape");

const metrics = summarizeRows(riskCaseRows);
assert.deepEqual(
  { official: metrics.official, media: metrics.media, companies: metrics.companies },
  { official: 6, media: 1, companies: 7 },
);

const lossCase = filterCases(riskCaseRows, {
  year: "2023",
  riskType: "重大衍生品损失",
  sourceOrg: "上海证券交易所",
  caseStatus: "已结案",
  search: "境外商品",
});
assert.deepEqual(Array.from(lossCase, (row) => row.id), ["demo-loss-2023"]);

const marginCase = filterCases(riskCaseRows, { search: "保证金" });
assert.deepEqual(Array.from(marginCase, (row) => row.id), ["demo-margin-2022"]);

const mediaRows = filterCases(riskCaseRows, {
  evidenceLevel: "media_unverified",
  year: "2025",
  sourceOrg: "新浪财经",
  search: "碳酸锂",
});
assert.deepEqual(Array.from(mediaRows, (row) => row.id), ["demo-media-loss-2025"]);
assert.equal(filterCases(riskCaseRows, { evidenceLevel: "official_verified" }).length, 6);

assert.equal(displayAmount(null, "人民币", "万元"), "未披露");
assert.equal(displayAmount(0, "人民币", "万元"), "0 万元 · 人民币");
assert.equal(displayAmount(2.43, "人民币", "亿元"), "2.43 亿元 · 人民币");

const documents = sortDocuments([
  { date: "2023-05-08", title: "整改报告" },
  { date: "2023-03-10", title: "问询函" },
  { date: "2023-04-02", title: "公司回复" },
]);
assert.deepEqual(Array.from(documents, (item) => item.title), ["问询函", "公司回复", "整改报告"]);

const csv = casesToCsv([riskCaseRows[0]]);
assert.ok(csv.startsWith("\uFEFF"));
assert.match(csv, /案例键,事件日期,公司名称/);
assert.match(csv, /证据级别,核实状态,来源名称,来源日期,来源URL/);
assert.match(csv, /https:\/\/example\.invalid\//);
assert.doesNotMatch(csv, /媒体线索|Tavily/);

const mediaRow = riskCaseRows.find((row) => row.id === "demo-media-loss-2025");
const mediaCsv = casesToCsv([mediaRow]);
assert.match(mediaCsv, /媒体报道／未核实/);
assert.match(mediaCsv, /新浪财经/);
assert.match(mediaCsv, /https:\/\/example\.invalid\/media\//);

const tableRow = renderTableRow(riskCaseRows[0]);
assert.match(tableRow, /data-case-id="demo-loss-2023"/);
assert.match(tableRow, /重大衍生品损失/);
assert.match(tableRow, /2\.43 亿元 · 人民币/);
assert.match(renderTableRow(mediaRow), /媒体报道／未核实/);

const drawer = renderDrawer(riskCaseRows[0]);
for (const heading of ["事件事实", "监管文档链", "逐字段证据"]) {
  assert.match(drawer, new RegExp(heading));
}
assert.match(drawer, /问询函/);
assert.match(drawer, /已回验/);
assert.match(drawer, /固定演示数据/);

const mediaDrawer = renderDrawer(mediaRow);
assert.match(mediaDrawer, /媒体来源/);
assert.match(mediaDrawer, /新浪财经/);
assert.match(mediaDrawer, /尚未找到官方依据/);
assert.doesNotMatch(mediaDrawer, /监管文档链/);
assert.doesNotMatch(mediaDrawer, /逐字段证据/);

console.log("risk case demo logic ok");
