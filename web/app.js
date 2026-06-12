/* nirs4all-cockpit — vanilla dashboard renderer (no framework, no build).
 *
 * Loads data/current.json (the Snapshot from `n4a-cockpit collect`) and renders
 * the hero scores, the package×registry matrix, downloads (only the metrics each
 * registry reports, with per-version detail for crates), GitHub stats, code &
 * Actions stats, and — when a local data/admin/snapshot.admin.json is present —
 * an Admin section. Status is conveyed by colour AND a dot/shape, never colour
 * alone. */

"use strict";

const REGISTRY_ORDER = ["pypi", "crates", "npm", "r-universe", "cran", "github-release"];
const STATES = ["green", "stale", "missing", "broken", "unknown", "excluded"];
const STATE_COLOR = {
  green: "#10b981", stale: "#d97706", missing: "#94a3b8",
  broken: "#e11d48", unknown: "#06b6d4", excluded: "#b6aa90",
};
const STATE_SYM = { green: "●", stale: "◐", missing: "○", broken: "✕", unknown: "?", excluded: "—" };

// ---- DOM helpers -----------------------------------------------------------

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
  const p = el("span", {
    class: "pill",
    attrs: { "data-state": state, role: "img", "aria-label": state },
  });
  p.appendChild(el("span", { class: "sym", attrs: { "aria-hidden": "true" } }));
  p.appendChild(el("span", { text: extraText || state }));
  return p;
}

function fmtInt(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US");
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ") + "Z";
}

// ---- data loading ----------------------------------------------------------

async function loadJSON(candidates) {
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
  throw lastErr || new Error("not found");
}

const loadSnapshot = () =>
  loadJSON(["../data/current.json", "./current.json", "./data/current.json"]);

async function loadAdmin() {
  try {
    return await loadJSON(["../data/admin/snapshot.admin.json", "./data/admin/snapshot.admin.json"]);
  } catch {
    return null; // admin data is optional and absent from the public site
  }
}

// ---- hero: generated + scores + summary + totals ---------------------------

function renderGenerated(snap) {
  const meta = document.getElementById("generated");
  meta.innerHTML = "";
  meta.appendChild(el("span", { text: `updated ${fmtDate(snap.generated_at)}` }));
  const gen = snap.generator || {};
  if (gen.repo) meta.appendChild(el("span", { text: gen.repo }));
  document.getElementById("schema").textContent = `schema v${snap.schema_version ?? "?"}`;
}

function dial(percent, color, big, cap) {
  const d = el("div", { class: "score" });
  const ring = el("div", { class: "dial" });
  ring.style.setProperty("--p", Math.max(0, Math.min(100, Math.round(percent))));
  ring.style.setProperty("--c", color);
  ring.appendChild(el("span", { text: `${Math.round(percent)}%` }));
  const lbl = el("div", { class: "lbl" });
  lbl.appendChild(el("span", { class: "num", text: big }));
  lbl.appendChild(el("span", { class: "cap", text: cap }));
  d.append(ring, lbl);
  return d;
}

function renderScores(snap) {
  const box = document.getElementById("scores");
  box.innerHTML = "";
  const pkgs = snap.packages || [];
  const greenPkgs = pkgs.filter((p) => p.rollup === "green").length;
  const s = snap.summary || {};
  const tracked = (s.green || 0) + (s.stale || 0) + (s.missing || 0) + (s.broken || 0) + (s.unknown || 0);
  const greenT = s.green || 0;
  box.appendChild(dial(pkgs.length ? (greenPkgs / pkgs.length) * 100 : 0, "var(--teal)", `${greenPkgs}/${pkgs.length}`, "packages current"));
  box.appendChild(dial(tracked ? (greenT / tracked) * 100 : 0, "var(--green)", `${greenT}/${tracked}`, "registry targets green"));
}

function renderSummary(snap) {
  const box = document.getElementById("summary");
  box.innerHTML = "";
  const summary = snap.summary || {};
  for (const state of STATES) {
    const chip = el("span", { class: "chip", attrs: { "data-state": state } });
    chip.style.setProperty("--st", STATE_COLOR[state]);
    chip.appendChild(el("span", { class: "sym", attrs: { "aria-hidden": "true" }, text: STATE_SYM[state] }));
    chip.appendChild(el("span", { class: "count", text: String(summary[state] || 0) }));
    chip.appendChild(el("span", { class: "muted", text: state }));
    box.appendChild(chip);
  }
  box.hidden = false;
}

function renderTotals(snap) {
  const box = document.getElementById("totals");
  const t = snap.totals;
  if (!box || !t) return;
  box.innerHTML = "";
  const items = [
    ["LOC", t.loc_code], ["tests", t.tests], ["files", t.files],
    ["★", t.stars], ["forks", t.forks], ["open issues", t.open_issues],
    ["CI runs", t.workflow_runs], ["dl/mo", t.downloads_last_month],
  ];
  for (const [label, value] of items) {
    const chip = el("span", { class: "chip" });
    chip.appendChild(el("span", { class: "count", text: fmtInt(value) }));
    chip.appendChild(el("span", { class: "muted", text: label }));
    box.appendChild(chip);
  }
  box.hidden = false;
}

function renderLegend() {
  const box = document.getElementById("legend");
  box.innerHTML = "";
  for (const state of STATES) box.appendChild(pill(state));
}

// ---- matrix ----------------------------------------------------------------

function registryColumns(snap) {
  const seen = new Set();
  for (const pkg of snap.packages || []) for (const t of pkg.targets || []) seen.add(t.registry);
  const cols = REGISTRY_ORDER.filter((r) => seen.has(r));
  for (const r of seen) if (!cols.includes(r)) cols.push(r);
  return cols;
}

function renderMatrix(snap) {
  const table = document.getElementById("matrix");
  table.innerHTML = "";
  const cols = registryColumns(snap);

  const thead = el("thead");
  const hrow = el("tr");
  hrow.appendChild(el("th", { class: "pkg-head", attrs: { scope: "col" }, text: "package" }));
  for (const c of cols) hrow.appendChild(el("th", { attrs: { scope: "col" }, text: c }));
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const tr = el("tr");
    const th = el("th", { class: "pkg-head", attrs: { scope: "row" } });
    th.appendChild(el("span", { class: "pkg-id", text: pkg.id }));
    const sub = el("div", { class: "pkg-sub" });
    const src = pkg.source || {};
    sub.appendChild(el("span", { class: "pkg-ver", text: src.manifest_version ? `v${src.manifest_version}` : "—" }));
    if (Array.isArray(pkg.flags) && pkg.flags.includes("source_ahead")) {
      sub.appendChild(el("span", { class: "badge", attrs: { title: "repo manifest is ahead of the latest prod tag" }, text: "source-ahead" }));
    }
    if (pkg.rollup) {
      const roll = el("span", { class: "badge badge--rollup" });
      roll.style.setProperty("color", STATE_COLOR[pkg.rollup] || "");
      roll.textContent = pkg.rollup;
      sub.appendChild(roll);
    }
    th.appendChild(sub);
    tr.appendChild(th);

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
          cell.appendChild(el("span", { class: "cell-ver", text: t.published_version ? `v${t.published_version}` : "—" }));
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

// ---- downloads (only the metrics each registry reports) --------------------

function metricChip(label, value) {
  const m = el("span", { class: "metric" });
  m.appendChild(document.createTextNode(label + " "));
  m.appendChild(el("b", { text: fmtInt(value) }));
  return m;
}

function renderDownloads(snap) {
  const box = document.getElementById("downloads");
  box.innerHTML = "";
  let any = false;
  for (const pkg of snap.packages || []) {
    for (const t of pkg.targets || []) {
      const d = t.downloads || {};
      const metrics = [];
      if (d.last_day != null) metrics.push(["day", d.last_day]);
      if (d.last_week != null) metrics.push(["week", d.last_week]);
      if (d.last_month != null) metrics.push([d.source === "crates.io" ? "90d" : "month", d.last_month]);
      if (d.total != null) metrics.push(["total", d.total]);
      const versions = (d.by_version || []).filter((v) => v.downloads != null);
      if (metrics.length === 0 && versions.length === 0) continue;
      any = true;

      const row = el("div", { class: "kv" });
      const head = el("div", { class: "kv__head" });
      head.appendChild(el("span", { class: "kv__name", text: t.name }));
      head.appendChild(el("span", { class: "dl-src", text: d.source || t.registry }));
      row.appendChild(head);

      const line = el("div", { class: "kv__line" });
      for (const [lab, val] of metrics) line.appendChild(metricChip(lab, val));
      row.appendChild(line);

      if (versions.length) {
        const btn = el("button", { class: "dl-toggle", attrs: { "aria-expanded": "false", type: "button" } });
        btn.appendChild(el("span", { class: "chev", attrs: { "aria-hidden": "true" }, text: "▸" }));
        btn.appendChild(document.createTextNode(` per-version (${versions.length})`));
        const grid = el("div", { class: "dl-versions" });
        grid.hidden = true;
        for (const v of versions) {
          const vr = el("div", { class: "vrow" });
          vr.appendChild(el("span", { text: v.version }));
          vr.appendChild(el("b", { text: fmtInt(v.downloads) }));
          grid.appendChild(vr);
        }
        btn.addEventListener("click", () => {
          const open = grid.hidden;
          grid.hidden = !open;
          btn.setAttribute("aria-expanded", String(open));
        });
        row.appendChild(btn);
        row.appendChild(grid);
      }
      box.appendChild(row);
    }
  }
  if (!any) box.appendChild(el("p", { class: "admin-note", text: "No download stats available." }));
}

// ---- GitHub stats ----------------------------------------------------------

function renderRepoStats(snap) {
  const box = document.getElementById("repostats");
  if (!box) return;
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["repo", "★ stars", "forks", "watch", "open PR", "merged", "closed", "issues", "license", "pushed"]) {
    hr.appendChild(el("th", { attrs: { scope: "col" }, text: h }));
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const s = pkg.repo_stats;
    if (!s) continue;
    const tr = el("tr");
    tr.appendChild(el("th", { class: "stats-repo", attrs: { scope: "row" }, text: pkg.repo }));
    const cells = [s.stars, s.forks, s.watchers, s.open_prs, s.merged_prs, s.closed_prs, pkg.issues ? pkg.issues.open : null];
    for (const v of cells) tr.appendChild(el("td", { class: "num", text: fmtInt(v) }));
    tr.appendChild(el("td", { class: "num", text: s.license || "—" }));
    tr.appendChild(el("td", { class: "num", text: s.pushed_at ? fmtDate(s.pushed_at).slice(0, 10) : "—" }));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  box.appendChild(table);
}

// ---- code & actions --------------------------------------------------------

function renderCodeStats(snap) {
  const box = document.getElementById("codestats");
  if (!box) return;
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["package", "LOC", "comments", "tests", "coverage", "top lang", "workflows", "runs", "success", "last"]) {
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
    const topLang = c && c.by_language ? Object.keys(c.by_language)[0] || "—" : "—";
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.loc_code) : "—" }));
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.loc_comment) : "—" }));
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.tests) : "—" }));
    const covTd = el("td", { class: "num" });
    if (c && c.coverage_pct != null) {
      const wrap = el("span", { attrs: { style: "display:inline-flex;align-items:center;gap:7px;justify-content:flex-end" } });
      const bar = el("span", { class: "bar" });
      bar.appendChild(el("i", { attrs: { style: `width:${Math.max(2, Math.min(100, c.coverage_pct))}%` } }));
      wrap.append(`${c.coverage_pct}%`, bar);
      covTd.appendChild(wrap);
    } else covTd.textContent = "—";
    tr.appendChild(covTd);
    tr.appendChild(el("td", { class: "num", text: topLang }));
    tr.appendChild(el("td", { class: "num", text: fmtInt(a.workflows) }));
    tr.appendChild(el("td", { class: "num", text: fmtInt(a.total_runs) }));
    tr.appendChild(el("td", { class: "num", text: a.success_rate != null ? `${a.success_rate}%` : "—" }));
    const concl = (a.last_conclusion || "—").toLowerCase();
    const last = el("td");
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

// ---- admin (local-only) ----------------------------------------------------

function renderAdmin(admin) {
  const section = document.getElementById("admin");
  const body = document.getElementById("admin-body");
  if (!admin || !body) return;
  body.innerHTML = "";
  section.hidden = false;

  const s = admin.sentry || {};
  const sentryBox = el("div", { class: "card panel" });
  sentryBox.appendChild(el("h3", { class: "section-h", text: `Sentry — ${s.project || "?"}` }));
  if (s.available) {
    sentryBox.appendChild(el("p", { class: "admin-note", text: `${fmtInt(s.unresolved)} unresolved (14d)` }));
    for (const iss of (s.issues || []).slice(0, 8)) {
      const row = el("div", { class: "kv" });
      const head = el("div", { class: "kv__head" });
      head.appendChild(el("span", { class: "kv__name", text: iss.title || "—" }));
      head.appendChild(el("span", { class: "conclusion", attrs: { "data-ok": "failure" }, text: iss.level || "issue" }));
      row.appendChild(head);
      row.appendChild(el("span", { class: "dl-src", text: `${fmtInt(iss.count)}× · ${fmtInt(iss.userCount)} users` }));
      sentryBox.appendChild(row);
    }
  } else {
    sentryBox.appendChild(el("p", { class: "admin-note", text: `unavailable — ${s.error || "set SENTRY_AUTH_TOKEN"}` }));
  }
  body.appendChild(sentryBox);

  const table = el("table", { class: "stats" });
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["repo", "open PR", "drafts", "dependabot", "code-scan", "views 14d", "clones 14d"]) {
    hr.appendChild(el("th", { attrs: { scope: "col" }, text: h }));
  }
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  for (const r of admin.repos || []) {
    const p = r.pulls || {}, sec = r.security || {}, tr_ = r.traffic || {};
    const row = el("tr");
    row.appendChild(el("th", { class: "stats-repo", attrs: { scope: "row" }, text: r.repo }));
    for (const v of [p.open, p.draft, sec.dependabot_open, sec.code_scanning_open, tr_.views_14d, tr_.clones_14d]) {
      row.appendChild(el("td", { class: "num", text: fmtInt(v) }));
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  const wrap = el("div", { class: "card panel panel--wide" });
  wrap.appendChild(el("h3", { class: "section-h", text: "Per-repo — traffic · PRs · security" }));
  wrap.appendChild(table);
  body.appendChild(wrap);
}

// ---- boot ------------------------------------------------------------------

async function main() {
  const errBox = document.getElementById("error");
  try {
    const snap = await loadSnapshot();
    renderGenerated(snap);
    renderScores(snap);
    renderSummary(snap);
    renderTotals(snap);
    renderLegend();
    renderMatrix(snap);
    renderDownloads(snap);
    renderRepoStats(snap);
    renderCodeStats(snap);
    renderAdmin(await loadAdmin());
  } catch (e) {
    errBox.hidden = false;
    errBox.textContent =
      `Could not load data/current.json (${e && e.message ? e.message : e}). ` +
      `Run "n4a-cockpit collect" to generate it, then reload.`;
    document.getElementById("generated").innerHTML = "<span>no data</span>";
  }
}

document.addEventListener("DOMContentLoaded", main);
