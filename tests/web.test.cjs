const assert = require("node:assert/strict");
const test = require("node:test");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const context = vm.createContext({ document: { addEventListener() {} }, URLSearchParams });
vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8"), context);

test("repository rows keep the canonical product once", () => {
  const result = vm.runInContext(`repositoryPackages([
    {repo: "methods", id: "methods"}, {repo: "methods", id: "n4m"}, {repo: "preflight", id: "preflight"}
  ]).map(p => p.id).join(",")`, context);
  assert.equal(result, "methods,preflight");
});

test("stale admin and carried-forward counters keep their observation date", () => {
  const now = Date.parse("2026-10-29T00:00:00Z");
  const result = vm.runInContext(`freshnessText("2026-09-12T00:00:00Z", true, ${now})`, context);
  assert.match(result, /stale/);
  assert.match(result, /last successful observation/);
  assert.equal(vm.runInContext("freshnessText(null)", context), "observation date unknown");
  assert.doesNotMatch(vm.runInContext(`freshnessText("2026-10-29T00:00:00Z", false, ${now})`, context), /stale/);
});

test("public Sentry links preserve the observed project and period", () => {
  const url = vm.runInContext(`sentryUnresolvedUrl({org: "org", project: "studio", stats_period: "14d"})`, context);
  assert.equal(new URL(url).searchParams.get("statsPeriod"), "14d");
  assert.equal(new URL(url).searchParams.get("query"), "is:unresolved project:studio");
});


test("repository links and deduplication preserve independent owners", () => {
  const url = vm.runInContext('registryUrl("github-release", "domains", "nirs4all-domains", "dcornet")', context);
  assert.equal(url, "https://github.com/dcornet/nirs4all-domains/releases");
  const count = vm.runInContext('repositoryPackages([{repo: "same", owner: "first"}, {repo: "same", owner: "second"}]).length', context);
  assert.equal(count, 2);
});

test("manual completion cannot hide negative checks or the current Studio hold", () => {
  const result = vm.runInContext(`JSON.stringify([
    {status: "done", resolved: null, auto_check: null},
    {status: "done", resolved: false, auto_check: {registry: "pypi"}},
    {status: "done", resolved: null, auto_check: {registry: "pypi"}},
    {status: "blocked", resolved: null, auto_check: null},
    {status: "todo", resolved: true, auto_check: {registry: "pypi"}}
  ].map(isManualActionPending))`, context);
  assert.equal(result, "[false,true,true,true,false]");
});
