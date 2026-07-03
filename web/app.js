/* nirs4all-cockpit — vanilla dashboard renderer (no framework, no build).
 * Loads data/current.json and renders the spectral-wave hero, a compact
 * LED release matrix (one LED per registry, links to the registry page), a
 * download dataviz (stacked bars by registry), GitHub & code/CI tables with
 * linked numbers, and an optional local-only Admin section. */

"use strict";

const REGS = ["readthedocs", "pypi", "crates", "npm", "r-universe", "cran", "github-release", "pages"];
const REG_LABEL = { readthedocs: "Read the Docs", pypi: "PyPI", crates: "crates.io", npm: "npm", "r-universe": "R-universe", cran: "CRAN", "github-release": "GitHub Releases", pages: "GitHub Pages" };
const REG_COLOR = { readthedocs: "#8ca1af", pypi: "#0d9488", crates: "#d97706", npm: "#e11d48", "r-universe": "#10b981", cran: "#4f46e5", "github-release": "#64748b" };
// Registries that actually report download counts. Pure web/docs projects whose
// only targets are `pages` / `readthedocs` are not packages and are excluded
// from the downloads dataviz.
const DOWNLOAD_REGS = new Set(["pypi", "crates", "npm", "r-universe", "cran"]);
const STATE_COLOR = { green: "#10b981", stale: "#e0950c", pending: "#8b5cf6", missing: "#b9c0cb", broken: "#e11d48", unknown: "#06b6d4", excluded: "#cabf9e" };
const STATES = ["green", "stale", "pending", "missing", "broken", "unknown", "excluded"];
const RANK = { broken: 6, missing: 5, stale: 4, pending: 3, unknown: 2, green: 1, excluded: 0 };
const ECOSYSTEM_LICENSE_LABEL = "AGPL-3.0";
const ECOSYSTEM_LICENSE_FULL = "CeCILL-2.1 OR AGPL-3.0-or-later";
const COMMERCIAL_CONTACT = "nirs4all-admin@cirad.fr";
const PAGES_URLS = {
  "nirs4all-org": "https://nirs4all.org/",
  "nirs4all-datasets": "https://datasets.nirs4all.org/",
  "nirs4all-formats": "https://formats.nirs4all.org/",
  "nirs4all-io": "https://io.nirs4all.org/",
  "nirs4all-methods": "https://methods.nirs4all.org/",
  "nirs4all-cockpit": "https://cockpit.nirs4all.org/",
  "nirs4all-web": "https://web.nirs4all.org/",
  "nirs4all-repository": "https://repository.nirs4all.org/",
  "nirs4all-papers": "https://papers.nirs4all.org/",
  "nirs4all-benchmarks": "https://benchmarks.nirs4all.org/",
};
let OWNER = "GBeurier";

// ---- helpers ---------------------------------------------------------------

function el(tag, opts = {}, children = []) {
  const n = document.createElement(tag);
  if (opts.class) n.className = opts.class;
  if (opts.text != null) n.textContent = opts.text;
  if (opts.html != null) n.innerHTML = opts.html;
  if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) n.setAttribute(k, v);
  for (const c of [].concat(children)) { if (c == null) continue; n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
  return n;
}
const fmtInt = (x) => (x == null ? "—" : Number(x).toLocaleString("en-US"));
const fmtPct = (x) => (x == null ? "—" : `${(Number(x) * 100).toFixed(Number(x) < 0.01 ? 2 : 1)}%`);
const fmtPos = (x) => (x == null ? "—" : Number(x).toFixed(1));
function fmtDate(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : d.toISOString().slice(0, 10); }
function fmtDateTime(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`; }
function fmtMonthYear(iso) { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? String(iso).slice(0, 7) : d.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" }); }
function versionDateLabel(src) {
  if (!src || !src.latest_version_at) return null;
  return fmtDate(src.latest_version_at);
}

function led(state) { return el("span", { class: `led led--${state}`, attrs: { role: "img", "aria-label": state } }); }

function registryUrl(reg, name, repo) {
  switch (reg) {
    case "pypi": return `https://pypi.org/project/${name}/`;
    case "crates": return `https://crates.io/crates/${name}`;
    case "npm": return `https://www.npmjs.com/package/${name}`;
    case "r-universe": return `https://${OWNER.toLowerCase()}.r-universe.dev/${name}`;
    case "cran": return `https://cran.r-project.org/package=${name}`;
    case "readthedocs": return `https://${name}.readthedocs.io/`;
    case "github-release": return `https://github.com/${OWNER}/${repo}/releases`;
    case "pages": return PAGES_URLS[repo] || `https://${OWNER.toLowerCase()}.github.io/${repo}/`;
    default: return `https://github.com/${OWNER}/${repo}`;
  }
}

// shared tooltip
const tip = () => document.getElementById("tooltip");
function attachTip(node, html) {
  node.addEventListener("mouseenter", () => { const t = tip(); t.innerHTML = html; t.hidden = false; });
  node.addEventListener("mousemove", (e) => { const t = tip(); t.style.left = e.clientX + "px"; t.style.top = e.clientY + "px"; });
  node.addEventListener("mouseleave", () => { tip().hidden = true; });
}

// ---- data ------------------------------------------------------------------

async function loadJSON(cands) {
  let err = null;
  for (const u of cands) { try { const r = await fetch(u, { cache: "no-store" }); if (r.ok) return await r.json(); err = new Error(`${u} ${r.status}`); } catch (e) { err = e; } }
  throw err || new Error("not found");
}
const loadSnapshot = () => loadJSON(["../data/current.json", "./current.json", "./data/current.json"]);
async function loadAdmin() { try { return await loadJSON(["../data/admin/snapshot.admin.json", "./data/admin/snapshot.admin.json"]); } catch { return null; } }

// ---- hero: meta, scores, summary -------------------------------------------

function renderMeta(snap) {
  const m = document.getElementById("generated");
  m.innerHTML = "";
  m.appendChild(el("span", { text: `updated ${fmtDateTime(snap.generated_at)}` }));
  if (snap.generator && snap.generator.repo) m.appendChild(el("a", { text: snap.generator.repo, attrs: { href: `https://github.com/${snap.generator.repo}` } }));
  document.getElementById("schema").textContent = `schema v${snap.schema_version ?? "?"}`;
}

function dial(pct, color, big, cap) {
  const d = el("div", { class: "score" });
  d.style.setProperty("--accent", color);
  const r = el("div", { class: "dial" });
  r.style.setProperty("--p", Math.max(0, Math.min(100, Math.round(pct))));
  r.style.setProperty("--c", color);
  r.appendChild(el("span", { text: `${Math.round(pct)}%` }));
  d.append(r, el("div", {}, [el("div", { class: "num", text: big }), el("div", { class: "cap", text: cap })]));
  return d;
}
function renderScores(snap) {
  const box = document.getElementById("scores");
  box.innerHTML = "";
  const pk = snap.packages || [];
  const greenPk = pk.filter((p) => p.rollup === "green").length;
  const s = snap.summary || {};
  const tracked = (s.green || 0) + (s.stale || 0) + (s.pending || 0) + (s.missing || 0) + (s.broken || 0) + (s.unknown || 0);
  box.appendChild(dial(pk.length ? (greenPk / pk.length) * 100 : 0, "var(--teal)", `${greenPk}/${pk.length}`, "package roll-ups green"));
  box.appendChild(dial(tracked ? ((s.green || 0) / tracked) * 100 : 0, "var(--green)", `${s.green || 0}/${tracked}`, "registry targets green"));
}

function renderSummary(snap) {
  const box = document.getElementById("summary");
  box.innerHTML = "";
  const t = snap.totals;
  if (t) {
    for (const [lab, v] of [["LOC", t.loc_code], ["tests", t.tests], ["★", t.stars], ["CI runs", t.workflow_runs], ["dl/mo", t.downloads_last_month]]) {
      const c = el("span", { class: "chip" });
      c.append(el("span", { class: "count", text: fmtInt(v) }), el("span", { class: "muted", text: lab }));
      box.appendChild(c);
    }
  }
  box.hidden = false;
}

// Legend doubles as the status totals: each state shows an LED + its count.
function renderLegend(snap) {
  const box = document.getElementById("legend");
  box.innerHTML = "";
  const s = snap.summary || {};
  for (const st of STATES) {
    const item = el("span", { class: "leg" });
    item.append(led(st), el("b", { class: "leg-n", text: String(s[st] || 0) }), el("span", { class: "leg-l", text: st }));
    box.appendChild(item);
  }
}

// ---- matrix ----------------------------------------------------------------

function worstState(targets) {
  const real = targets.filter((t) => t.status !== "excluded");
  if (!real.length) return "excluded";
  let w = "green", wr = RANK.green;
  for (const t of real) { const r = RANK[t.status] ?? 1; if (r > wr) { wr = r; w = t.status; } }
  return w;
}
function facade(targets) {
  return targets.slice().sort((a, b) => a.name.length - b.name.length)[0];
}

function renderMatrix(snap) {
  const table = document.getElementById("mxtable");
  table.innerHTML = "";
  const thead = el("thead");
  const hr = el("tr");
  hr.append(el("th", { class: "h-pkg", text: "package" }), el("th", { class: "h-ver", text: "version" }));
  const REG_SHORT = { readthedocs: "RTD", pypi: "PyPI", crates: "crates", npm: "npm", "r-universe": "R-univ", cran: "CRAN", "github-release": "GH rel", pages: "Pages" };
  const REG_BRAND = { readthedocs: "#8ca1af", pypi: "#3775A9", crates: "#C16C28", npm: "#CB3837", "r-universe": "#2E73C4", cran: "#1B5390", "github-release": "#24292F", pages: "#0ea5e9" };
  for (const reg of REGS) {
    const col = REG_BRAND[reg] || "var(--text-2)";
    const th = el("th", { class: "reg-head", attrs: { scope: "col", title: REG_LABEL[reg] } });
    th.appendChild(el("span", { class: "reg-ico", attrs: { style: `color:${col}` }, html: `<svg viewBox="0 0 24 24">${REGISTRY_ICONS[reg] ? `<path d="${REGISTRY_ICONS[reg]}"/>` : ""}</svg>` }));
    th.appendChild(el("span", { class: "reg-name", attrs: { style: `color:${col}` }, text: REG_SHORT[reg] || reg }));
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const tr = el("tr");
    const byReg = new Map();
    for (const t of pkg.targets || []) { if (!byReg.has(t.registry)) byReg.set(t.registry, []); byReg.get(t.registry).push(t); }

    // package cell: just the name (link to repo) — the registry cells already
    // show what's published/missing, so no redundant left-hand rollup LED.
    const cPkg = el("th", { class: "c-pkg", attrs: { scope: "row" } });
    const a = el("a", { attrs: { href: `https://github.com/${OWNER}/${pkg.repo}`, target: "_blank", rel: "noopener" } });
    a.append(el("span", { class: "pkg-name", text: pkg.id }));
    if (pkg.repo && pkg.repo !== pkg.id) a.append(el("span", { class: "pkg-repo", text: `repo ${pkg.repo}` }));
    cPkg.appendChild(a);
    tr.appendChild(cPkg);

    const src = pkg.source || {};
    const verTd = el("td", { class: "c-ver" });
    verTd.appendChild(el("span", { class: "ver-main", text: src.manifest_version ? `v${src.manifest_version}` : "—" }));
    const vdate = versionDateLabel(src);
    if (vdate) verTd.appendChild(el("span", { class: "ver-date", text: vdate }));
    tr.appendChild(verTd);

    for (const reg of REGS) {
      const td = el("td", { class: "c-led" });
      const targets = byReg.get(reg);
      if (!targets || !targets.length) { td.appendChild(el("span", { class: "led led--none", attrs: { "aria-label": "no target" } })); tr.appendChild(td); continue; }
      const st = worstState(targets);
      const rep = facade(targets);
      const href = (reg === "pages" || reg === "readthedocs") && rep.evidence && rep.evidence.version_endpoint
        ? rep.evidence.version_endpoint
        : registryUrl(reg, rep.name, pkg.repo);
      const link = el("a", { attrs: { href, target: "_blank", rel: "noopener" } });
      const dot = led(st);
      if (targets.length > 1) { const wrap = el("span", { class: "led-multi" }); wrap.append(dot, el("span", { class: "badge-n", text: `×${targets.length}` })); link.appendChild(wrap); }
      else link.appendChild(dot);
      const rows = targets.map((t) => `<div class="tt-row"><span class="led led--${t.status}"></span> <b>${t.name}</b> · ${t.status}${t.planned ? " · planned" : ""}${t.published_version ? " · v" + t.published_version : ""}</div>`).join("");
      attachTip(link, `<b>${REG_LABEL[reg]}</b>${rows}<div class="tt-row" style="margin-top:5px;opacity:.7">click → open registry page</div>`);
      td.appendChild(link);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
}

// ---- downloads dataviz (stacked bars by registry) --------------------------

// Each registry reports its own window; we show a ~90-day view. When a registry
// only reports a shorter window, we use that value and mark it a lower bound (>).
function dlBest(t) {
  const w = (t.downloads && t.downloads.windows) || {};
  if (w["90d"] != null) return { value: w["90d"], window: "90 d", lower: false };
  if (w["total"] != null) return { value: w["total"], window: "all-time", lower: false };
  if (w["30d"] != null) return { value: w["30d"], window: "30 d", lower: true };
  if (w["7d"] != null) return { value: w["7d"], window: "7 d", lower: true };
  return null;
}

function renderDownloads(snap) {
  const box = document.getElementById("downloads");
  box.innerHTML = "";
  const rows = [];
  for (const pkg of snap.packages || []) {
    // Skip web/docs-only projects (e.g. nirs4all-org / -web / -cockpit) — they
    // publish no package, so they have no place in the downloads dataviz.
    if (!(pkg.targets || []).some((t) => DOWNLOAD_REGS.has(t.registry))) continue;
    const segs = [];
    let total = 0, lower = false;
    for (const t of pkg.targets || []) {
      const b = dlBest(t);
      if (b && b.value > 0) { segs.push({ reg: t.registry, name: t.name, ...b }); total += b.value; if (b.lower) lower = true; }
    }
    rows.push({ pkg, segs, total, lower });
  }
  if (!rows.length) { box.appendChild(el("p", { class: "admin-note", text: "No packages in snapshot." })); return; }
  rows.sort((a, b) => b.total - a.total || a.pkg.id.localeCompare(b.pkg.id));
  const max = Math.max(1, ...rows.map((r) => r.total));

  for (const row of rows) {
    const r = el("div", { class: "dlrow" });
    const prim = row.segs.slice().sort((a, b) => b.value - a.value)[0];
    const href = prim ? registryUrl(prim.reg, prim.name, row.pkg.repo) : `https://github.com/${OWNER}/${row.pkg.repo}`;
    r.appendChild(el("a", { class: "dl-name", text: row.pkg.id, attrs: { href, target: "_blank", rel: "noopener", title: row.pkg.id } }));
    const bar = el("div", { class: "dlbar", attrs: { style: `width:${row.total > 0 ? Math.max(6, (row.total / max) * 100) : 0}%` } });
    for (const s of row.segs.sort((a, b) => b.value - a.value)) {
      const seg = el("a", { class: "dlseg", attrs: { href: registryUrl(s.reg, s.name, row.pkg.repo), target: "_blank", rel: "noopener", style: `width:${(s.value / row.total) * 100}%;background:${REG_COLOR[s.reg]}` } });
      attachTip(seg, `<b>${s.name}</b><div class="tt-row">${REG_LABEL[s.reg]} · ${s.lower ? "&gt;" : ""}${fmtInt(s.value)} <span style="opacity:.6">(${s.window})</span></div>`);
      bar.appendChild(seg);
    }
    r.appendChild(bar);
    r.appendChild(el("span", { class: "dl-tot", text: row.total > 0 ? (row.lower ? ">" : "") + fmtInt(row.total) : "—" }));
    box.appendChild(r);
  }

  const axis = el("div", { class: "dl-axis" });
  for (const reg of REGS) {
    if (!rows.some((r) => r.segs.some((s) => s.reg === reg))) continue;
    axis.appendChild(el("span", {}, [el("span", { class: "dl-swatch", attrs: { style: `background:${REG_COLOR[reg]}` } }), el("span", { text: REG_LABEL[reg] })]));
  }
  axis.appendChild(el("span", { class: "admin-note", text: "Sorted by reported package-registry downloads · > = lower bound" }));
  box.appendChild(axis);
}

// ---- GitHub table ----------------------------------------------------------

function numLink(value, href) {
  if (value == null) return el("td", { class: "num", text: "—" });
  const td = el("td", { class: "num" });
  td.appendChild(el("a", { class: "num", text: fmtInt(value), attrs: { href, target: "_blank", rel: "noopener" } }));
  return td;
}

function licenseCell(rawLicense) {
  const td = el("td", { class: "num" });
  const badge = el("span", { class: "license-badge", text: ECOSYSTEM_LICENSE_LABEL, attrs: { title: ECOSYSTEM_LICENSE_FULL } });
  const observed = rawLicense && rawLicense !== ECOSYSTEM_LICENSE_LABEL
    ? `<div class="tt-row">GitHub API: ${rawLicense}</div>`
    : "";
  attachTip(
    badge,
    `<b>${ECOSYSTEM_LICENSE_LABEL}</b><div class="tt-row">Open-source: ${ECOSYSTEM_LICENSE_FULL}</div><div class="tt-row">Commercial: ${COMMERCIAL_CONTACT}</div>${observed}`,
  );
  td.appendChild(badge);
  return td;
}

function dateCell(iso, href) {
  const td = el("td", { class: "num datecell" });
  const wrap = href
    ? el("a", { class: "datecell-link", attrs: { href, target: "_blank", rel: "noopener" } })
    : el("span");
  wrap.appendChild(el("span", { class: "datecell-main", text: iso ? fmtDate(iso) : "—" }));
  td.appendChild(wrap);
  return td;
}

function renderRepoStats(snap) {
  const box = document.getElementById("repostats");
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead"), hr = el("tr");
  for (const h of ["repo", "★ stars", "forks", "watch", "open PR", "merged", "closed", "issues", "license", "last commit", "ahead"]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const s = pkg.repo_stats; if (!s) continue;
    const src = pkg.source || {};
    const base = `https://github.com/${OWNER}/${pkg.repo}`;
    const commitHref = src.commit ? `${base}/commit/${src.commit}` : null;
    const branch = s.default_branch || "main";
    const aheadHref = src.latest_prod_tag ? `${base}/compare/${encodeURIComponent(src.latest_prod_tag)}...${encodeURIComponent(branch)}` : null;
    const tr = el("tr");
    const repoTd = el("th", { class: "s-repo", attrs: { scope: "row" } });
    repoTd.appendChild(el("a", { text: pkg.repo, attrs: { href: base, target: "_blank", rel: "noopener" } }));
    tr.appendChild(repoTd);
    tr.appendChild(numLink(s.stars, `${base}/stargazers`));
    tr.appendChild(numLink(s.forks, `${base}/forks`));
    tr.appendChild(numLink(s.watchers, `${base}/watchers`));
    tr.appendChild(numLink(s.open_prs, `${base}/pulls?q=is%3Apr+is%3Aopen`));
    tr.appendChild(numLink(s.merged_prs, `${base}/pulls?q=is%3Apr+is%3Amerged`));
    tr.appendChild(numLink(s.closed_prs, `${base}/pulls?q=is%3Apr+is%3Aclosed`));
    tr.appendChild(numLink(pkg.issues ? pkg.issues.open : null, `${base}/issues`));
    tr.appendChild(licenseCell(s.license));
    tr.appendChild(dateCell(src.last_commit_at, commitHref));
    tr.appendChild(numLink(src.commits_ahead_of_latest_prod_tag, aheadHref || `${base}/commits/${branch}`));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody); box.appendChild(table);
}

// ---- code & actions --------------------------------------------------------

function langCell(lang) {
  const td = el("td", { class: "num" });
  if (!lang) { td.textContent = "—"; return td; }
  const ic = typeof LANG_ICONS !== "undefined" ? LANG_ICONS[lang] : null;
  const wrap = el("span", { class: "langcell" });
  if (ic) wrap.appendChild(el("span", { class: "lang-ico", attrs: { style: `color:${ic.c}` }, html: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="${ic.d}"/></svg>` }));
  wrap.appendChild(el("span", { text: lang }));
  td.appendChild(wrap);
  return td;
}

function renderCodeStats(snap) {
  const box = document.getElementById("codestats");
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead"), hr = el("tr");
  for (const h of ["package", "LOC", "comments", "tests", "coverage", "top lang", "workflows", "runs", "success", "last"]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const c = pkg.code_stats, a = pkg.actions_stats || {};
    const base = `https://github.com/${OWNER}/${pkg.repo}`;
    const tr = el("tr");
    const pkgTd = el("th", { class: "s-repo", attrs: { scope: "row" } });
    pkgTd.appendChild(el("a", { text: pkg.id, attrs: { href: base, target: "_blank", rel: "noopener" } }));
    tr.appendChild(pkgTd);
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.loc_code) : "—" }));
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.loc_comment) : "—" }));
    tr.appendChild(el("td", { class: "num", text: c ? fmtInt(c.tests) : "—" }));
    const cov = el("td", { class: "num" });
    if (c && c.coverage_pct != null) {
      const w = el("span", { attrs: { style: "display:inline-flex;align-items:center;gap:7px;justify-content:flex-end" } });
      const bar = el("span", { class: "bar" }); bar.appendChild(el("i", { attrs: { style: `width:${Math.max(2, Math.min(100, c.coverage_pct))}%` } }));
      w.append(`${c.coverage_pct}%`, bar); cov.appendChild(w);
    } else cov.textContent = "—";
    tr.appendChild(cov);
    const primaryLanguage = (pkg.repo_stats && pkg.repo_stats.language) ||
      (c && c.by_language ? Object.keys(c.by_language)[0] : null);
    tr.appendChild(langCell(primaryLanguage));
    tr.appendChild(el("td", { class: "num", text: fmtInt(a.workflows) }));
    tr.appendChild(numLink(a.total_runs, `${base}/actions`));
    tr.appendChild(el("td", { class: "num", text: a.success_rate != null ? `${a.success_rate}%` : "—" }));
    const concl = (a.last_conclusion || "—").toLowerCase();
    tr.appendChild(el("td", {}, [el("span", { class: "conclusion", attrs: { "data-ok": concl === "success" ? "success" : concl === "failure" ? "failure" : "other" }, text: concl })]));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody); box.appendChild(table);
}

// ---- pages visits (public · GoatCounter) -----------------------------------

// The full ecosystem roster — every page is listed even at 0 views. `path` is the
// explicit GoatCounter path each site reports; `repo` maps to its public URL.
const ECO_PAGES = [
  ["/org", "nirs4all.org", "nirs4all-org"],
  ["/web", "web.nirs4all.org", "nirs4all-web"],
  ["/formats", "formats.nirs4all.org", "nirs4all-formats"],
  ["/io", "io.nirs4all.org", "nirs4all-io"],
  ["/datasets", "datasets.nirs4all.org", "nirs4all-datasets"],
  ["/methods", "methods.nirs4all.org", "nirs4all-methods"],
  ["/cockpit", "cockpit.nirs4all.org", "nirs4all-cockpit"],
  ["/repository", "repository.nirs4all.org", "nirs4all-repository"],
  ["/papers", "papers.nirs4all.org", "nirs4all-papers"],
  ["/benchmarks", "benchmarks.nirs4all.org", "nirs4all-benchmarks"],
];

function renderVisits(snap) {
  const v = snap.visits || {};
  const block = document.getElementById("visits-block"), box = document.getElementById("visits");
  if (!box || !v.available) return; // no GoatCounter token at collect time → section stays hidden
  block.hidden = false;
  box.innerHTML = "";

  const w = v.windows || {};
  const chips = el("div", { class: "vchips" });
  const vacc = ["var(--teal)", "var(--cyan)", "var(--indigo)", "var(--amber)"];
  const sinceLabel = v.since ? `all-time · since ${fmtMonthYear(v.since)}` : "all-time";
  [["7 days", "7d"], ["30 days", "30d"], ["365 days", "365d"], [sinceLabel, "total"]].forEach(([lab, key], i) => {
    const c = el("div", { class: "vchip" });
    c.style.setProperty("--accent", vacc[i % vacc.length]);
    c.append(el("span", { class: "vchip__n", text: fmtInt(w[key]) }), el("span", { class: "vchip__l", text: lab }));
    chips.appendChild(c);
  });
  box.appendChild(chips);

  // Every ecosystem page, even at 0 views; counts come from the snapshot.
  const counts = new Map((v.pages || []).map((p) => [p.path, p.count || 0]));
  const rows = ECO_PAGES
    .map(([path, label, repo]) => ({ path, label, repo, count: counts.get(path) || 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  const table = el("table", { class: "stats visits-table" });
  const thead = el("thead"), hr = el("tr");
  for (const h of ["page", "views"]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const r of rows) {
    const row = el("tr");
    const href = PAGES_URLS[r.repo] || `${(v.site || "").replace(/\/$/, "")}${r.path}`;
    const pageTd = el("th", { class: "s-repo", attrs: { scope: "row" } });
    pageTd.appendChild(el("a", { text: r.label, attrs: { href, target: "_blank", rel: "noopener", title: r.path } }));
    row.appendChild(pageTd);
    row.appendChild(el("td", { class: "num", text: fmtInt(r.count) }));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  box.appendChild(table);
  box.appendChild(el("p", { class: "vcap", text: `${v.site || "GoatCounter"} · daily snapshot · all ecosystem pages` }));
}

// ---- Google Search Console (public aggregate) ------------------------------

function pageLabel(url) {
  try {
    const u = new URL(url);
    return `${u.hostname}${u.pathname === "/" ? "" : u.pathname}`.replace(/\/$/, "");
  } catch {
    return url;
  }
}

function metricChip(value, label, accent) {
  const c = el("div", { class: "vchip" });
  c.style.setProperty("--accent", accent);
  c.append(el("span", { class: "vchip__n", text: value }), el("span", { class: "vchip__l", text: label }));
  return c;
}

function renderMetricTable(rows, kind) {
  const table = el("table", { class: "stats visits-table" });
  const thead = el("thead"), hr = el("tr");
  const first = kind === "query" ? "query" : "page";
  for (const h of [first, "clicks", "impr.", "CTR", "pos."]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const r of rows) {
    const row = el("tr");
    const name = kind === "query" ? r.query : pageLabel(r.url);
    const head = el("th", { class: "s-repo", attrs: { scope: "row" } });
    if (kind === "page") {
      head.appendChild(el("a", { text: name, attrs: { href: r.url, target: "_blank", rel: "noopener" } }));
    } else {
      head.textContent = name;
    }
    row.appendChild(head);
    row.appendChild(el("td", { class: "num", text: fmtInt(r.clicks) }));
    row.appendChild(el("td", { class: "num", text: fmtInt(r.impressions) }));
    row.appendChild(el("td", { class: "num", text: fmtPct(r.ctr) }));
    row.appendChild(el("td", { class: "num", text: fmtPos(r.position) }));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  return table;
}

function renderSearchConsole(snap) {
  const g = snap.search_console || {};
  const block = document.getElementById("search-console-block"), box = document.getElementById("search-console");
  if (!box || !g.available) return;
  block.hidden = false;
  box.innerHTML = "";

  const w = g.windows || {};
  const [windowLabel, m] = w["28d"] ? ["28 d", w["28d"]] : w["7d"] ? ["7 d", w["7d"]] : ["90 d", w["90d"] || {}];
  const chips = el("div", { class: "vchips" });
  chips.append(
    metricChip(fmtInt(m.clicks), `clicks · ${windowLabel}`, "var(--teal)"),
    metricChip(fmtInt(m.impressions), `impressions · ${windowLabel}`, "var(--cyan)"),
    metricChip(fmtPct(m.ctr), `CTR · ${windowLabel}`, "var(--indigo)"),
    metricChip(fmtPos(m.position), "avg. position", "var(--amber)"),
  );
  box.appendChild(chips);

  const pages = (g.pages || []).slice(0, 12);
  if (pages.length) {
    box.appendChild(el("p", { class: "vcap", text: "Top pages · 90 d" }));
    box.appendChild(renderMetricTable(pages, "page"));
  }

  const queries = (g.queries || []).slice(0, 10);
  if (queries.length) {
    box.appendChild(el("p", { class: "vcap", text: "Top queries · 90 d" }));
    box.appendChild(renderMetricTable(queries, "query"));
  }

  box.appendChild(el("p", { class: "vcap", text: `${g.site_url || "Search Console"} · ${g.start_date || "?"} → ${g.end_date || "?"} · finalized Google Search data` }));
}

// ---- errors (public · Sentry) ----------------------------------------------

function sentryStat(n, label, alert, accent, href) {
  const tag = href ? "a" : "div";
  const attrs = href ? { href, target: "_blank", rel: "noopener" } : undefined;
  const c = el(tag, { class: `sentry-stat${alert ? " sentry-stat--alert" : ""}${href ? " sentry-stat--link" : ""}`, attrs });
  c.style.setProperty("--accent", accent || "var(--teal)");
  c.append(el("span", { class: "sentry-stat__n", text: fmtInt(n) }), el("span", { class: "sentry-stat__l", text: label }));
  return c;
}

// Org-scoped Sentry issue stream filtered to unresolved (the org has a single project).
function sentryUnresolvedUrl(s) {
  return s && s.org ? `https://${s.org}.sentry.io/issues/?query=is%3Aunresolved&statsPeriod=90d` : null;
}

function renderSentry(snap) {
  const s = snap.sentry || {};
  const block = document.getElementById("sentry-block"), box = document.getElementById("sentry");
  if (!box || !s.available) return; // no auth token at collect time → section stays hidden
  block.hidden = false;
  box.innerHTML = "";

  const head = el("div", { class: "sentry-head" });
  head.append(
    sentryStat(s.unresolved, "unresolved", (s.unresolved || 0) > 0, (s.unresolved || 0) > 0 ? "var(--broken)" : "var(--green)", sentryUnresolvedUrl(s)),
    sentryStat(s.resolved, "resolved", false, "var(--green)"),
    sentryStat(s.events, "events", false, "var(--indigo)"),
    sentryStat(s.users_affected, "users affected", false, "var(--amber)"),
  );
  box.appendChild(head);
  box.appendChild(el("p", { class: "vcap", text: `${s.project || "nirs4all-studio"} · aggregate Sentry counters only` }));
}

// ---- admin (local) ---------------------------------------------------------

function renderAdmin(admin) {
  const section = document.getElementById("admin"), body = document.getElementById("admin-body");
  if (!admin || !body) return;
  body.innerHTML = ""; section.hidden = false;
  const s = admin.sentry || {};
  const sb = el("div", { class: "card panel" });
  sb.appendChild(el("h3", { class: "section-h", text: `Sentry — ${s.project || "?"}` }));
  if (s.available) {
    const head = el("div", { class: "sentry-head" });
    head.append(
      sentryStat(s.unresolved, "unresolved", (s.unresolved || 0) > 0),
      sentryStat(s.resolved, "resolved", false),
      sentryStat(s.events, "events", false),
      sentryStat(s.users_affected, "users affected", false),
    );
    sb.appendChild(head);
    sb.appendChild(el("p", { class: "admin-note", text: "Aggregate Sentry counters only; issue titles and user details are not displayed." }));
  } else sb.appendChild(el("p", { class: "admin-note", text: `unavailable — ${s.error || "set SENTRY_AUTH_TOKEN"}` }));
  body.appendChild(sb);

  const wrap = el("div", { class: "card panel" });
  wrap.appendChild(el("h3", { class: "section-h", text: "Per-repo — traffic · PRs · security" }));
  const table = el("table", { class: "stats" });
  const thead = el("thead"), hr = el("tr");
  for (const h of ["repo", "open PR", "drafts", "dependabot", "code-scan", "views 14d", "clones 14d"]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const r of admin.repos || []) {
    const p = r.pulls || {}, sec = r.security || {}, tr_ = r.traffic || {};
    const row = el("tr");
    row.appendChild(el("th", { class: "s-repo", attrs: { scope: "row" }, text: r.repo }));
    for (const v of [p.open, p.draft, sec.dependabot_open, sec.code_scanning_open, tr_.views_14d, tr_.clones_14d]) row.appendChild(el("td", { class: "num", text: fmtInt(v) }));
    tbody.appendChild(row);
  }
  table.appendChild(tbody); wrap.appendChild(table); body.appendChild(wrap);
}

// ---- spectral wave animation (ported from nirs4all.org) --------------------

function startWave() {
  const W = 1440, H = 400, STEP = 6;
  const lines = [0, 1, 2].map((i) => document.getElementById("line" + i));
  const areas = [0, 1, 2].map((i) => document.getElementById("area" + i));
  const dotsG = document.getElementById("wave-dots");
  if (!lines[0] || !dotsG) return;
  const waves = [
    { baseY: 250, amp: 52, freq: 0.0044, phase: 0, speed: 0.00090, dot: "rgba(15,118,110,.95)", col: "#0f766e" },
    { baseY: 285, amp: 40, freq: 0.0038, phase: 2.1, speed: 0.00072, dot: "rgba(8,145,178,.85)", col: "#0891b2" },
    { baseY: 225, amp: 32, freq: 0.0052, phase: 4.2, speed: 0.00056, dot: "rgba(5,150,105,.75)", col: "#059669" },
  ];
  const yAt = (w, x, now) => w.baseY + Math.sin(x * w.freq + w.phase + now * w.speed) * w.amp + Math.sin(x * w.freq * 1.7 + w.phase * 0.6 + now * w.speed * 0.7) * w.amp * 0.2;
  const linePath = (w, now) => { let d = ""; for (let x = 0; x <= W; x += STEP) d += (x === 0 ? "M" : "L") + x + "," + yAt(w, x, now).toFixed(1); return d; };
  const areaPath = (w, now) => linePath(w, now) + `L${W},${H}L0,${H}Z`;
  const dots = [];
  let last = 0;
  const MAX_DX = 240; // SVG-space window for cross-spectral connectors
  function frame(now) {
    waves.forEach((w, i) => { lines[i].setAttribute("d", linePath(w, now)); areas[i].setAttribute("d", areaPath(w, now)); });
    if (now - last > 320 && dots.length < 16) {
      last = now;
      const wi = (Math.random() * 3) | 0, w = waves[wi], x = 80 + Math.random() * (W - 160);
      const e = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      e.setAttribute("r", "3"); e.setAttribute("fill", w.dot); e.classList.add("wave-dot"); e.style.color = w.col;
      dotsG.appendChild(e); dots.push({ e, wi, x, born: now, conns: [] });
    }
    // move dots; cull the dead
    for (let i = dots.length - 1; i >= 0; i--) {
      const d = dots[i], age = now - d.born, life = 2600;
      if (age > life) { d.e.remove(); d.conns.forEach((c) => c.remove()); dots.splice(i, 1); continue; }
      d.y = yAt(waves[d.wi], d.x, now);
      d.op = Math.sin((age / life) * Math.PI) * 0.9;
      d.e.setAttribute("cx", d.x); d.e.setAttribute("cy", d.y.toFixed(1)); d.e.setAttribute("opacity", d.op.toFixed(2));
    }
    // dotted connector traces between dots living on DIFFERENT waves (cross-spectral)
    dots.forEach((d) => { d.conns.forEach((c) => c.remove()); d.conns = []; });
    const seen = new Set();
    for (let i = 0; i < dots.length; i++) {
      const a = dots[i]; if (a.op < 0.18) continue;
      let best = null;
      for (let j = 0; j < dots.length; j++) {
        if (i === j) continue;
        const b = dots[j];
        if (b.wi === a.wi || b.op < 0.18) continue;
        const dx = Math.abs(a.x - b.x); if (dx > MAX_DX) continue;
        if (!best || dx < best.dx) best = { b, j, dx };
      }
      if (!best) continue;
      const key = i < best.j ? i + ":" + best.j : best.j + ":" + i;
      if (seen.has(key)) continue;
      seen.add(key);
      const op = Math.min(a.op, best.b.op) * 0.55 * (0.35 + 0.65 * (1 - best.dx / MAX_DX));
      if (op < 0.03) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      line.setAttribute("d", `M${a.x.toFixed(1)},${a.y.toFixed(1)} L${best.b.x.toFixed(1)},${best.b.y.toFixed(1)}`);
      line.setAttribute("stroke", waves[a.wi].col);
      line.setAttribute("stroke-width", "0.75");
      line.setAttribute("opacity", op.toFixed(3));
      line.classList.add("wave-connector");
      dotsG.insertBefore(line, dotsG.firstChild);
      a.conns.push(line);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ---- boot ------------------------------------------------------------------

async function main() {
  const errBox = document.getElementById("error");
  startWave();
  try {
    const snap = await loadSnapshot();
    if (snap.generator && snap.generator.repo) OWNER = snap.generator.repo.split("/")[0];
    renderMeta(snap);
    renderScores(snap);
    renderSummary(snap);
    renderLegend(snap);
    renderMatrix(snap);
    renderDownloads(snap);
    renderVisits(snap);
    renderSearchConsole(snap);
    renderSentry(snap);
    renderRepoStats(snap);
    renderCodeStats(snap);
    renderAdmin(await loadAdmin());
  } catch (e) {
    errBox.hidden = false;
    errBox.textContent = `Could not load data/current.json (${e && e.message ? e.message : e}). Run "n4a-cockpit collect", then reload.`;
    document.getElementById("generated").innerHTML = "<span>no data</span>";
  }
}
document.addEventListener("DOMContentLoaded", main);
