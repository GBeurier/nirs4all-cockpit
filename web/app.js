/* nirs4all-cockpit — vanilla dashboard renderer (no framework, no build).
 *
 * Loads data/current.json (the Snapshot written by `n4a-cockpit collect`) and
 * renders:
 *   1. a package x registry matrix of coloured + symboled status pills,
 *   2. a downloads panel, 3. an issues panel, 4. a CI / workflow-health panel,
 *   plus a "generated at" banner and the summary counters.
 *
 * Status is always conveyed by BOTH a colour and a glyph, never colour alone.
 */

"use strict";

// Column order for the matrix. Any registry seen in the data but not listed
// here is appended after these, so the UI never silently drops a target.
const REGISTRY_ORDER = ["pypi", "crates", "npm", "r-universe", "cran", "github-release"];

const STATES = ["green", "stale", "missing", "broken", "unknown", "excluded"];

// Glyph per state (the accessible, colour-independent signal).
const SYMBOL = {
  green: "●", // ● filled
  stale: "◐", // ◐ half
  missing: "○", // ○ hollow
  broken: "✕", // ✕ cross
  unknown: "?", // ?
  excluded: "—", // — dash
};

const LABEL = {
  green: "green",
  stale: "stale",
  missing: "missing",
  broken: "broken",
  unknown: "unknown",
  excluded: "excluded",
};

// ---- tiny DOM helpers ------------------------------------------------------

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text != null) node.textContent = opts.text;
  if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

function pill(state, extraText) {
  const label = LABEL[state] || state;
  const p = el("span", {
    class: "pill",
    attrs: { "data-state": state, title: label, role: "img", "aria-label": label },
  });
  p.appendChild(el("span", { class: "sym", attrs: { "aria-hidden": "true" }, text: SYMBOL[state] || "?" }));
  p.appendChild(el("span", { text: extraText || label }));
  return p;
}

function fmtInt(n) {
  if (n == null) return "n/a";
  return Number(n).toLocaleString("en-US");
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z").replace(/:\d\dZ$/, "Z");
}

// ---- data loading ----------------------------------------------------------

async function loadSnapshot() {
  // Pages can serve either the repo root (web reads ../data/current.json) or a
  // build that copies data/ next to web/ (./current.json). Try both.
  const candidates = ["../data/current.json", "./current.json", "./data/current.json"];
  let lastErr = null;
  for (const url of candidates) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return await res.json();
      lastErr = new Error(`${url} → HTTP ${res.status}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("no snapshot found");
}

// ---- renderers -------------------------------------------------------------

function renderBanner(snap) {
  const meta = document.getElementById("generated");
  meta.innerHTML = "";
  meta.appendChild(el("div", { text: `generated ${fmtDate(snap.generated_at)}` }));
  const gen = snap.generator || {};
  const bits = [gen.repo, gen.workflow, gen.run_id ? `run ${gen.run_id}` : null].filter(Boolean);
  if (bits.length) meta.appendChild(el("div", { class: "muted", text: bits.join(" · ") }));
  document.getElementById("schema").textContent = `schema v${snap.schema_version ?? "?"}`;
}

function renderSummary(snap) {
  const box = document.getElementById("summary");
  box.innerHTML = "";
  const summary = snap.summary || {};
  for (const state of STATES) {
    const count = summary[state] || 0;
    const chip = el("span", { class: "chip", attrs: { "data-state": state } });
    chip.appendChild(el("span", { class: "sym", attrs: { "aria-hidden": "true" }, text: SYMBOL[state] }));
    chip.appendChild(el("span", { class: "count", text: String(count) }));
    chip.appendChild(el("span", { class: "muted", text: LABEL[state] }));
    box.appendChild(chip);
  }
  box.hidden = false;
}

function renderLegend() {
  const box = document.getElementById("legend");
  box.innerHTML = "";
  for (const state of STATES) box.appendChild(pill(state));
}

function registryColumns(snap) {
  const seen = new Set();
  for (const pkg of snap.packages || []) {
    for (const t of pkg.targets || []) seen.add(t.registry);
  }
  const cols = REGISTRY_ORDER.filter((r) => seen.has(r));
  for (const r of seen) if (!cols.includes(r)) cols.push(r);
  return cols;
}

function renderMatrix(snap) {
  const table = document.getElementById("matrix");
  table.innerHTML = "";
  const cols = registryColumns(snap);

  // header
  const thead = el("thead");
  const hrow = el("tr");
  hrow.appendChild(el("th", { class: "pkg-head", attrs: { scope: "col" }, text: "package" }));
  for (const c of cols) hrow.appendChild(el("th", { attrs: { scope: "col" }, text: c }));
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const tr = el("tr");

    // row header: id + manifest_version + source-ahead badge + rollup
    const th = el("th", { class: "pkg-head", attrs: { scope: "row" } });
    th.appendChild(el("span", { class: "pkg-id", text: pkg.id }));
    const sub = el("div", { class: "pkg-sub" });
    const src = pkg.source || {};
    sub.appendChild(el("span", { class: "pkg-ver", text: `manifest ${src.manifest_version || "—"}` }));
    if (Array.isArray(pkg.flags) && pkg.flags.includes("source_ahead")) {
      sub.appendChild(el("span", { class: "badge", attrs: { title: "repo manifest is ahead of the latest prod tag" }, text: "source-ahead" }));
    }
    if (pkg.rollup) sub.appendChild(el("span", { class: "badge badge--rollup", text: pkg.rollup }));
    th.appendChild(sub);
    tr.appendChild(th);

    // index targets by registry; a registry can hold several names (e.g. crates)
    const byReg = new Map();
    for (const t of pkg.targets || []) {
      if (!byReg.has(t.registry)) byReg.set(t.registry, []);
      byReg.get(t.registry).push(t);
    }

    for (const c of cols) {
      const td = el("td");
      const targets = byReg.get(c);
      if (!targets || targets.length === 0) {
        td.appendChild(el("span", { class: "cell-empty", attrs: { "aria-label": "no target" }, text: "·" }));
      } else {
        for (const t of targets) {
          const cell = el("div", { class: "cell" });
          const p = pill(t.status);
          if (t.planned) p.appendChild(el("span", { class: "tag-planned", text: "planned" }));
          cell.appendChild(p);
          cell.appendChild(el("span", { class: "cell-name", text: t.name }));
          cell.appendChild(
            el("span", { class: "cell-ver", text: t.published_version ? `v${t.published_version}` : "—" })
          );
          if (t.error) cell.appendChild(el("span", { class: "cell-err", text: t.error }));
          td.appendChild(cell);
        }
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
}

function renderRepoStats(snap) {
  const box = document.getElementById("repostats");
  if (!box) return;
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["repo", "★ stars", "forks", "watchers", "open PRs", "views 14d", "clones 14d", "pushed"]) {
    hr.appendChild(el("th", { attrs: { scope: "col" }, text: h }));
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el("tbody");
  let any = false;
  for (const pkg of snap.packages || []) {
    const s = pkg.repo_stats;
    if (!s) continue;
    any = true;
    const tr = el("tr");
    tr.appendChild(el("th", { class: "stats-repo", attrs: { scope: "row" }, text: pkg.repo || pkg.id }));
    const views = s.traffic_views_14d != null ? `${fmtInt(s.traffic_views_14d)} (${fmtInt(s.traffic_views_uniques)}u)` : "—";
    const clones = s.traffic_clones_14d != null ? `${fmtInt(s.traffic_clones_14d)} (${fmtInt(s.traffic_clones_uniques)}u)` : "—";
    for (const v of [fmtInt(s.stars), fmtInt(s.forks), fmtInt(s.watchers), fmtInt(s.open_prs), views, clones]) {
      tr.appendChild(el("td", { class: "num", text: v }));
    }
    tr.appendChild(el("td", { class: "muted", text: fmtDate(s.pushed_at) }));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  if (!any) {
    box.appendChild(el("p", { class: "muted", text: "No GitHub stats available." }));
  } else {
    box.appendChild(table);
  }
}

function renderTotals(snap) {
  const box = document.getElementById("totals");
  if (!box) return;
  const t = snap.totals;
  if (!t) return;
  box.innerHTML = "";
  const items = [
    ["LOC (code)", t.loc_code],
    ["tests", t.tests],
    ["files", t.files],
    ["★ stars", t.stars],
    ["forks", t.forks],
    ["open issues", t.open_issues],
    ["workflow runs", t.workflow_runs],
    ["dl / month", t.downloads_last_month],
    ["packages", t.packages],
  ];
  for (const [label, value] of items) {
    const chip = el("span", { class: "chip" });
    chip.appendChild(el("span", { class: "count", text: fmtInt(value) }));
    chip.appendChild(el("span", { class: "muted", text: label }));
    box.appendChild(chip);
  }
  box.hidden = false;
}

function renderCodeStats(snap) {
  const box = document.getElementById("codestats");
  if (!box) return;
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["package", "LOC code", "comments", "tests", "coverage", "top language", "workflows", "runs", "success", "last"]) {
    hr.appendChild(el("th", { attrs: { scope: "col" }, text: h }));
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const c = pkg.code_stats;
    const a = pkg.actions_stats || {};
    const tr = el("tr");
    tr.appendChild(el("th", { class: "stats-repo", attrs: { scope: "row" }, text: pkg.id }));
    const topLang = c && c.by_language ? (Object.keys(c.by_language)[0] || "—") : "—";
    const cov = c && c.coverage_pct != null ? `${c.coverage_pct}%` : "—";
    const rate = a.success_rate != null ? `${a.success_rate}%` : "—";
    const cells = [
      c ? fmtInt(c.loc_code) : "n/a",
      c ? fmtInt(c.loc_comment) : "—",
      c ? fmtInt(c.tests) : "—",
      cov,
      topLang,
      fmtInt(a.workflows),
      fmtInt(a.total_runs),
      rate,
    ];
    for (const v of cells) tr.appendChild(el("td", { class: "num", text: v }));
    const last = el("td");
    const concl = (a.last_conclusion || "—").toLowerCase();
    last.appendChild(el("span", {
      class: "conclusion",
      attrs: { "data-ok": concl === "success" ? "success" : concl === "failure" ? "failure" : "other" },
      text: concl,
    }));
    tr.appendChild(last);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  box.appendChild(table);
}

function renderDownloads(snap) {
  const box = document.getElementById("downloads");
  box.innerHTML = "";
  let any = false;
  for (const pkg of snap.packages || []) {
    for (const t of pkg.targets || []) {
      const d = t.downloads || {};
      const has = [d.last_day, d.last_week, d.last_month, d.total].some((x) => x != null);
      if (!has) continue;
      any = true;
      const row = el("div", { class: "kv" });
      row.appendChild(el("span", { class: "kv__name", text: `${t.name}` }));
      row.appendChild(el("span", { class: "dl-src", text: d.source || "unknown source" }));
      const line = el("div", { class: "kv__line" });
      line.appendChild(spanKV("day", d.last_day));
      line.appendChild(spanKV("week", d.last_week));
      line.appendChild(spanKV("month", d.last_month));
      line.appendChild(spanKV("total", d.total));
      row.appendChild(line);
      box.appendChild(row);
    }
  }
  if (!any) box.appendChild(el("p", { class: "muted", text: "No download stats available." }));
}

function spanKV(label, value) {
  const s = el("span");
  s.appendChild(document.createTextNode(`${label} `));
  s.appendChild(el("b", { text: fmtInt(value) }));
  return s;
}

function renderIssues(snap) {
  const box = document.getElementById("issues");
  box.innerHTML = "";
  let any = false;
  for (const pkg of snap.packages || []) {
    const iss = pkg.issues || {};
    if (iss.open == null && iss.bugs == null) continue;
    any = true;
    const row = el("div", { class: "kv" });
    row.appendChild(el("span", { class: "kv__name", text: pkg.repo || pkg.id }));
    const line = el("div", { class: "kv__line" });
    line.appendChild(spanKV("open", iss.open ?? 0));
    line.appendChild(spanKV("bugs", iss.bugs ?? 0));
    row.appendChild(line);
    box.appendChild(row);
  }
  if (!any) box.appendChild(el("p", { class: "muted", text: "No issue data." }));
}

function renderCI(snap) {
  const box = document.getElementById("ci");
  box.innerHTML = "";
  let any = false;
  for (const pkg of snap.packages || []) {
    const wfs = pkg.workflows || [];
    if (wfs.length === 0) continue;
    any = true;
    box.appendChild(el("div", { class: "kv__name", text: pkg.repo || pkg.id }));
    for (const w of wfs) {
      const concl = (w.conclusion || "unknown").toLowerCase();
      const okKind = concl === "success" ? "success" : concl === "failure" ? "failure" : "other";
      const row = el("div", { class: "ci-row" });
      row.appendChild(el("span", { class: "ci-file", text: w.file }));
      row.appendChild(el("span", { class: "conclusion", attrs: { "data-ok": okKind }, text: concl }));
      row.appendChild(el("span", { class: "muted", text: fmtDate(w.created_at) }));
      if (w.head_sha) row.appendChild(el("span", { class: "muted", text: String(w.head_sha).slice(0, 7) }));
      box.appendChild(row);
    }
  }
  if (!any) box.appendChild(el("p", { class: "muted", text: "No workflow runs recorded." }));
}

// ---- admin (local-only) ----------------------------------------------------

// The admin snapshot (traffic / PRs / security / Sentry) is gitignored and only
// present on a local run. Fetch it best-effort; if absent (e.g. the public Pages
// site), the admin section simply stays hidden.
async function loadAdmin() {
  const candidates = ["../data/admin/snapshot.admin.json", "./data/admin/snapshot.admin.json"];
  for (const url of candidates) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (e) {
      /* ignore — admin data is optional */
    }
  }
  return null;
}

function renderAdmin(admin) {
  const section = document.getElementById("admin");
  const body = document.getElementById("admin-body");
  if (!admin || !body) return;
  body.innerHTML = "";
  section.hidden = false;

  // Sentry panel
  const s = admin.sentry || {};
  const sentryBox = el("div", { class: "panel" });
  sentryBox.appendChild(el("h3", { class: "section-h", text: `Sentry — ${s.project || "?"}` }));
  if (s.available) {
    sentryBox.appendChild(el("p", { text: `${fmtInt(s.unresolved)} unresolved (14d)` }));
    for (const iss of (s.issues || []).slice(0, 8)) {
      const row = el("div", { class: "ci-row" });
      row.appendChild(el("span", { class: "conclusion", attrs: { "data-ok": "failure" }, text: iss.level || "issue" }));
      row.appendChild(el("span", { class: "ci-file", text: iss.title || "—" }));
      row.appendChild(el("span", { class: "muted", text: `${fmtInt(iss.count)}× / ${fmtInt(iss.userCount)}u` }));
      sentryBox.appendChild(row);
    }
  } else {
    sentryBox.appendChild(el("p", { class: "muted", text: `unavailable — ${s.error || "set SENTRY_AUTH_TOKEN"}` }));
  }
  body.appendChild(sentryBox);

  // Per-repo admin table
  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["repo", "open PRs", "drafts", "dependabot", "code-scan", "views 14d", "clones 14d"]) {
    hr.appendChild(el("th", { attrs: { scope: "col" }, text: h }));
  }
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  for (const r of admin.repos || []) {
    const p = r.pulls || {}, sec = r.security || {}, tr_ = r.traffic || {};
    const row = el("tr");
    row.appendChild(el("th", { class: "stats-repo", attrs: { scope: "row" }, text: r.repo }));
    for (const v of [fmtInt(p.open), fmtInt(p.draft), fmtInt(sec.dependabot_open), fmtInt(sec.code_scanning_open), fmtInt(tr_.views_14d), fmtInt(tr_.clones_14d)]) {
      row.appendChild(el("td", { class: "num", text: v }));
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  const tableBox = el("div", { class: "panel panel--wide" });
  tableBox.appendChild(el("h3", { class: "section-h", text: "Per-repo (traffic / PRs / security)" }));
  tableBox.appendChild(table);
  body.appendChild(tableBox);
}

// ---- boot ------------------------------------------------------------------

async function main() {
  const errBox = document.getElementById("error");
  try {
    const snap = await loadSnapshot();
    renderBanner(snap);
    renderSummary(snap);
    renderLegend();
    renderMatrix(snap);
    renderTotals(snap);
    renderRepoStats(snap);
    renderCodeStats(snap);
    renderDownloads(snap);
    renderIssues(snap);
    renderCI(snap);
    renderAdmin(await loadAdmin());
  } catch (e) {
    errBox.hidden = false;
    errBox.textContent =
      `Could not load data/current.json (${e && e.message ? e.message : e}). ` +
      `Run "n4a-cockpit collect" to generate it, then reload.`;
    document.getElementById("generated").innerHTML = '<span class="muted">no data</span>';
  }
}

document.addEventListener("DOMContentLoaded", main);
