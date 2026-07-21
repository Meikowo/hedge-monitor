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
assert.match(html, /app\.js\?v=20260721-2/);
assert.match(html, /styles\.css\?v=20260721-2/);
assert.match(app, /API_TIMEOUT_MS = 20000/);
assert.match(app, /API_MAX_ATTEMPTS = 3/);
assert.match(app, /async function apiCount/);
assert.match(app, /method: "HEAD"/);
assert.doesNotMatch(app, /apiAll\("announcements", \{ select: "status"/);

console.log(`web structure ok: ${new Set(referencedIds).size} referenced ids resolved`);
