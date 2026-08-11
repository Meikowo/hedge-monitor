import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../web/app.js", import.meta.url), "utf8");
const periodic = fs.readFileSync(new URL("../web/periodic.js", import.meta.url), "utf8");
const risk = fs.readFileSync(new URL("../web/risk.js", import.meta.url), "utf8");

const referencedIds = [app, periodic, risk]
  .flatMap((source) => [...source.matchAll(/(?:\$|document\.querySelector)\("#([A-Za-z0-9_-]+)"\)/g)].map((match) => match[1]));
for (const id of new Set(referencedIds)) {
  const idPattern = new RegExp(`id=(?:\\\\?["'])${id}(?:\\\\?["'])`);
  assert.ok(idPattern.test(html) || idPattern.test(app), `Missing static or dynamically rendered element #${id}`);
}

assert.match(html, /id="dashboard-year-filter"/);
assert.match(html, /id="province-chart"/);
assert.equal((html.match(/<th>省份<\/th>/g) || []).length, 2);
assert.match(app, /row\.province/);
assert.match(app, /"省份"/);
assert.match(html, /data-view="actuals"/);
assert.match(html, /id="periodic-view"/);
assert.match(html, /id="periodic-loading"/);
assert.match(html, /id="periodic-error"/);
assert.match(html, /id="periodic-search"/);
assert.match(html, /id="periodic-year-filter"/);
assert.match(html, /id="periodic-scope-filter"/);
assert.match(html, /id="periodic-accounting-filter"/);
assert.match(html, /id="periodic-evidence-filter"/);
assert.match(html, /id="periodic-body"/);
assert.match(html, /id="periodic-export-button"/);
assert.match(html, /periodic\.js\?v=20260811-1/);
assert.match(html, /risk\.js\?v=20260811-1/);
assert.match(html, /app\.js\?v=20260811-1/);
assert.match(html, /styles\.css\?v=20260811-1/);
assert.match(app, /API_TIMEOUT_MS = 20000/);
assert.match(app, /API_MAX_ATTEMPTS = 3/);
assert.match(app, /async function apiCount/);
assert.match(app, /method: "HEAD"/);
assert.match(app, /window\.HedgeShell/);
assert.match(app, /HedgePeriodic\?\.activate/);
assert.match(app, /HedgePeriodic\?\.refresh/);
assert.doesNotMatch(app, /apiAll\("announcements", \{ select: "status"/);
for (const table of [
  "periodic_reports",
  "periodic_derivatives",
  "periodic_metric_items",
  "periodic_hedge_accounting_items"
]) {
  assert.match(periodic, new RegExp(`apiAll\\("${table}"`));
}
assert.match(periodic, /value_verified: "eq\.true"/);
assert.match(periodic, /quote_verified: "eq\.true"/);
assert.match(periodic, /#periodic-error-message/);
assert.match(periodic, /#periodic-export-button/);
assert.match(periodic, /periodicRowsToCsv/);
assert.match(periodic, /data-periodic-row/);
assert.match(periodic, /window\.HedgePeriodic/);
assert.match(periodic, /Object\.freeze\(\{ activate, refresh \}\)/);
assert.match(html, /data-view="risk"/);
assert.match(html, /id="risk-view"/);
assert.match(html, /id="risk-loading"/);
assert.match(html, /id="risk-error"/);
assert.match(html, /id="risk-search"/);
assert.match(html, /id="risk-year-filter"/);
assert.match(html, /id="risk-type-filter"/);
assert.match(html, /id="risk-source-filter"/);
assert.match(html, /id="risk-status-filter"/);
assert.match(html, /id="risk-evidence-filter"/);
assert.match(html, /id="risk-export-button"/);
assert.match(html, /id="risk-body"/);
assert.match(app, /HedgeRisk\?\.activate/);
assert.match(app, /HedgeRisk\?\.refresh/);
for (const table of [
  "risk_source_documents",
  "derivative_risk_cases",
  "risk_case_documents",
  "risk_case_evidence",
  "risk_media_reports",
  "risk_media_report_sources",
]) {
  assert.match(risk, new RegExp(`apiAll\\("${table}"`));
}
assert.doesNotMatch(risk, /apiAll\("risk_media_leads"/);
assert.doesNotMatch(risk, /apiAll\("risk_media_backfill_windows"/);
assert.match(risk, /window\.HedgeRisk/);
assert.match(risk, /Object\.freeze\(\{ activate, refresh \}\)/);

console.log(`web structure ok: ${new Set(referencedIds).size} referenced ids resolved`);
