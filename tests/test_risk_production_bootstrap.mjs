import assert from "node:assert/strict";
import fs from "node:fs";
import { buildRiskRows } from "../web/risk.js";

const configSource = fs.readFileSync(new URL("../web/config.js", import.meta.url), "utf8");
const configValue = (name) => {
  const match = configSource.match(new RegExp(`${name}:\\s*"([^"]+)"`));
  assert.ok(match, `Missing ${name} in public config`);
  return match[1];
};
const base = configValue("supabaseUrl");
const key = configValue("supabaseKey");

async function request(table, params = {}) {
  const url = new URL(`${base}/rest/v1/${table}`);
  Object.entries(params).forEach(([name, value]) => url.searchParams.set(name, value));
  return fetch(url, { headers: { apikey: key }, signal: AbortSignal.timeout(60000) });
}

async function rows(table, params = {}) {
  const response = await request(table, params);
  if (!response.ok) {
    assert.fail(`${table} failed with ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

const startedAt = Date.now();
const [cases, sourceDocuments, documents, evidence, reports, sources] = await Promise.all([
  rows("derivative_risk_cases", { select: "case_key,code,company_name,event_date,first_disclosure_date,risk_type,instruments,underlyings,summary,amount,currency,unit,regulatory_action,outcome,case_status" }),
  rows("risk_source_documents", { select: "source_doc_id,source_org,source_type,title,publish_date,document_url" }),
  rows("risk_case_documents", { select: "case_key,source_doc_id,relation_type" }),
  rows("risk_case_evidence", { select: "id,case_key,source_doc_id,field,page,quote,extracted_value,source_url,quote_verified,value_verified" }),
  rows("risk_media_reports", { select: "media_key,code,company_name,event_date,risk_type,instruments,underlyings,summary,verification_status,official_case_key,publish_status", publish_status: "in.(published,corroborated)" }),
  rows("risk_media_report_sources", { select: "source_key,media_key,publisher_name,source_domain,title,published_at,url,short_excerpt,matched_derivative_terms,matched_risk_terms" }),
]);

assert.ok(Date.now() - startedAt < 60000, "risk bootstrap exceeded 60 seconds");
assert.ok(reports.length > 0, "expected at least one published media risk record");
assert.ok(reports.every((row) => ["published", "corroborated"].includes(row.publish_status)));
assert.ok(sources.every((row) => reports.some((report) => report.media_key === row.media_key)));
const normalized = buildRiskRows({ cases, sourceDocuments, documents, evidence, reports, sources });
assert.equal(normalized.length, cases.length + reports.filter((report) => !report.official_case_key).length);

for (const privateTable of ["risk_media_leads", "risk_media_backfill_windows"]) {
  const response = await request(privateTable, { select: "*", limit: "1" });
  assert.ok([401, 403].includes(response.status), `${privateTable} unexpectedly exposed with status ${response.status}`);
}

console.log(`risk bootstrap ok: ${cases.length} official, ${reports.length} media, ${sources.length} sources in ${Date.now() - startedAt} ms`);
