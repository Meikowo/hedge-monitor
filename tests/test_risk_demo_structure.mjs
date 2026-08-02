import assert from "node:assert/strict";
import fs from "node:fs";

const htmlUrl = new URL("../web-demo/risk-cases/index.html", import.meta.url);
const html = fs.readFileSync(htmlUrl, "utf8");

const requiredIds = [
  "search-input",
  "year-filter",
  "risk-filter",
  "source-filter",
  "status-filter",
  "reset-filters",
  "export-button",
  "metric-cases",
  "metric-companies",
  "metric-loss",
  "metric-regulatory",
  "result-count",
  "cases-body",
  "empty-state",
  "detail-drawer",
  "drawer-content",
  "drawer-close",
  "drawer-overlay",
];

for (const id of requiredIds) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `missing #${id}`);
}

assert.match(html, /data-workspace=["']risk-cases["'][^>]*aria-current=["']page["']/);
assert.match(html, /<table[^>]*class=["'][^"']*risk-table/);
for (const heading of ["事件日期", "公司", "风险类型", "工具 / 品种", "损失或涉案金额", "监管措施", "处理结果", "来源机构", "案例状态", "证据"]) {
  assert.match(html, new RegExp(`<th>${heading.replace(" / ", " \/ ")}</th>`), `missing ${heading} column`);
}
assert.match(html, /固定演示数据/);
assert.match(html, /href=["']styles\.css["']/);
assert.match(html, /src=["']data\.js["'][\s\S]*src=["']app\.js["']/);
assert.doesNotMatch(html, /supabase/i);
assert.doesNotMatch(html, /config\.js/i);
assert.doesNotMatch(html, /service[_-]?role/i);
assert.doesNotMatch(html, /<script[^>]+src=["']https?:/i);

console.log("risk case demo structure ok");
