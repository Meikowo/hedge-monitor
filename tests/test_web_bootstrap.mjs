import assert from "node:assert/strict";
import fs from "node:fs";

class FakeClassList {
  add() {}
  remove() {}
  toggle() {}
  contains() { return false; }
}

class FakeElement {
  constructor() {
    this.hidden = false;
    this.textContent = "";
    this.innerHTML = "";
    this.value = "";
    this.disabled = false;
    this.dataset = {};
    this.classList = new FakeClassList();
  }
  addEventListener() {}
  setAttribute() {}
  focus() {}
  scrollIntoView() {}
  appendChild() {}
  remove() {}
}

const html = fs.readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
const configSource = fs.readFileSync(new URL("../web/config.js", import.meta.url), "utf8");
const ids = [...html.matchAll(/id="([^"]+)"/g)].map((match) => match[1]);
const elements = new Map(ids.map((id) => [id, new FakeElement()]));
for (const id of ["dashboard-view", "error-state", "events-table-wrap", "announcements-table-wrap", "pagination"]) {
  elements.get(id).hidden = true;
}

const loadingTitle = new FakeElement();
const loadingSubtitle = new FakeElement();
const statusDot = new FakeElement();
const body = new FakeElement();

globalThis.document = {
  body,
  activeElement: null,
  querySelector(selector) {
    if (selector === ".status-dot") return statusDot;
    if (selector === "#loading-state strong") return loadingTitle;
    if (selector === "#loading-state span:last-child") return loadingSubtitle;
    if (selector.startsWith("#")) return elements.get(selector.slice(1)) || null;
    return new FakeElement();
  },
  querySelectorAll() { return []; },
  addEventListener() {},
  createElement() { return new FakeElement(); }
};

const configValue = (name) => {
  const match = configSource.match(new RegExp(`${name}:\\s*"([^"]+)"`));
  assert.ok(match, `Missing ${name} in public config`);
  return match[1];
};

globalThis.window = {
  HEDGE_CONFIG: {
    supabaseUrl: configValue("supabaseUrl"),
    supabaseKey: configValue("supabaseKey")
  },
  setTimeout,
  clearTimeout,
  addEventListener() {},
  scrollTo() {}
};
globalThis.requestAnimationFrame = (callback) => callback();

await import(new URL("../web/app.js", import.meta.url));

const deadline = Date.now() + 60000;
while (!elements.get("loading-state").hidden && elements.get("error-state").hidden && Date.now() < deadline) {
  await new Promise((resolve) => setTimeout(resolve, 50));
}

assert.equal(elements.get("loading-state").hidden, true, "Loading state did not finish");
assert.equal(elements.get("error-state").hidden, true, elements.get("error-message").textContent || "Unexpected load error");
assert.ok(Number(elements.get("metric-events").textContent.replaceAll(",", "")) > 0, "Event metric was not populated");
assert.ok(Number(elements.get("metric-extracted").textContent.replaceAll(",", "")) > 0, "Extracted metric was not populated");
assert.match(elements.get("events-body").innerHTML, /data-label="省份"/);

console.log(`web bootstrap ok: ${elements.get("metric-events").textContent} events, ${elements.get("metric-extracted").textContent} extracted`);
