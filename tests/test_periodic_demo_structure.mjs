import assert from "node:assert/strict";
import fs from "node:fs";

const htmlUrl = new URL("../web-demo/periodic-actuals/index.html", import.meta.url);
const html = fs.readFileSync(htmlUrl, "utf8");

const requiredIds = [
  "period-filter",
  "category-filter",
  "accounting-filter",
  "match-filter",
  "search-input",
  "actuals-body",
  "result-count",
  "detail-drawer",
  "drawer-content",
  "drawer-close",
  "column-period-filter",
  "column-company-filter",
  "column-underlying-filter",
  "column-plan-basis-filter",
  "column-flow-filter",
  "column-margin-filter",
  "column-asset-filter",
  "column-liability-filter",
  "column-net-filter",
  "column-pnl-filter",
  "column-disposal-filter",
  "column-fv-filter",
  "column-accounting-filter",
  "column-method-filter",
  "column-match-filter",
  "column-evidence-filter",
];

for (const id of requiredIds) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `missing #${id}`);
}

assert.match(html, /data-workspace=["']actuals["'][^>]*aria-current=["']page["']/);
assert.match(html, /<table[^>]*class=["'][^"']*actuals-table/);
assert.match(html, /class=["'][^"']*column-filter-row/);
for (const heading of ["期末保证金", "衍生金融资产", "衍生金融负债", "公允价值净额"]) {
  assert.match(html, new RegExp(`<th>${heading}</th>`), `missing ${heading} column`);
}
assert.match(html, /href=["']styles\.css["']/);
assert.match(html, /src=["']data\.js["'][\s\S]*src=["']app\.js["']/);
assert.match(html, /src=["']app\.js["']/);
assert.doesNotMatch(html, /<script[^>]+type=["']module["']/i);
assert.doesNotMatch(html, /supabase/i);
assert.doesNotMatch(html, /config\.js/i);
assert.doesNotMatch(html, /service[_-]?role/i);
assert.doesNotMatch(html, /<script[^>]+src=["']https?:/i);

console.log("periodic actuals demo structure ok");
