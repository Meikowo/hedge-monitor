import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../web/app.js", import.meta.url), "utf8");

const referencedIds = [...app.matchAll(/\$\("#([A-Za-z0-9_-]+)"\)/g)].map((match) => match[1]);
for (const id of new Set(referencedIds)) {
  const idPattern = new RegExp(`id=(?:\\\\?["'])${id}(?:\\\\?["'])`);
  assert.ok(idPattern.test(html) || idPattern.test(app), `Missing static or dynamically rendered element #${id}`);
}

assert.match(html, /id="dashboard-year-filter"/);
assert.match(html, /id="province-chart"/);
assert.equal((html.match(/<th>省份<\/th>/g) || []).length, 2);
assert.match(app, /row\.province/);
assert.match(app, /"省份"/);

console.log(`web structure ok: ${new Set(referencedIds).size} referenced ids resolved`);
