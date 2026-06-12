/* nirs4all-cockpit — vanilla dashboard renderer (no framework, no build).
 * Loads data/current.json and renders the spectral-wave hero, a compact
 * LED release matrix (one LED per registry, links to the registry page), a
 * download dataviz (stacked bars by registry), GitHub & code/CI tables with
 * linked numbers, and an optional local-only Admin section. */

"use strict";

const REGS = ["pypi", "crates", "npm", "r-universe", "cran", "github-release"];
const REG_LABEL = { pypi: "PyPI", crates: "crates.io", npm: "npm", "r-universe": "R-universe", cran: "CRAN", "github-release": "GitHub Releases" };
const REG_COLOR = { pypi: "#0d9488", crates: "#d97706", npm: "#e11d48", "r-universe": "#10b981", cran: "#4f46e5", "github-release": "#64748b" };
const STATE_COLOR = { green: "#10b981", stale: "#e0950c", missing: "#b9c0cb", broken: "#e11d48", unknown: "#06b6d4", excluded: "#cabf9e" };
const STATES = ["green", "stale", "missing", "broken", "unknown", "excluded"];
const RANK = { broken: 5, missing: 4, stale: 3, unknown: 2, green: 1, excluded: 0 };
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
function fmtDate(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : d.toISOString().slice(0, 10); }

function led(state) { return el("span", { class: `led led--${state}`, attrs: { role: "img", "aria-label": state } }); }

function registryUrl(reg, name, repo) {
  switch (reg) {
    case "pypi": return `https://pypi.org/project/${name}/`;
    case "crates": return `https://crates.io/crates/${name}`;
    case "npm": return `https://www.npmjs.com/package/${name}`;
    case "r-universe": return `https://${OWNER.toLowerCase()}.r-universe.dev/${name}`;
    case "cran": return `https://cran.r-project.org/package=${name}`;
    case "github-release": return `https://github.com/${OWNER}/${repo}/releases`;
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
  m.appendChild(el("span", { text: `updated ${fmtDate(snap.generated_at)}` }));
  if (snap.generator && snap.generator.repo) m.appendChild(el("a", { text: snap.generator.repo, attrs: { href: `https://github.com/${snap.generator.repo}` } }));
  document.getElementById("schema").textContent = `schema v${snap.schema_version ?? "?"}`;
}

function dial(pct, color, big, cap) {
  const d = el("div", { class: "score" });
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
  const tracked = (s.green || 0) + (s.stale || 0) + (s.missing || 0) + (s.broken || 0) + (s.unknown || 0);
  box.appendChild(dial(pk.length ? (greenPk / pk.length) * 100 : 0, "var(--teal)", `${greenPk}/${pk.length}`, "packages current"));
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
  const REG_SHORT = { pypi: "PyPI", crates: "crates", npm: "npm", "r-universe": "R-univ", cran: "CRAN", "github-release": "GH rel" };
  const REG_BRAND = { pypi: "#3775A9", crates: "#C16C28", npm: "#CB3837", "r-universe": "#2E73C4", cran: "#1B5390", "github-release": "#24292F" };
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

    // package cell: rollup LED (with a why-tooltip) + name (link to repo)
    const cPkg = el("th", { class: "c-pkg", attrs: { scope: "row" } });
    const a = el("a", { attrs: { href: `https://github.com/${OWNER}/${pkg.repo}`, target: "_blank", rel: "noopener" } });
    const rollLed = led(pkg.rollup || "missing");
    const regWorst = {};
    for (const t of pkg.targets || []) { const r = t.registry; if (regWorst[r] == null || (RANK[t.status] ?? 1) > (RANK[regWorst[r]] ?? 1)) regWorst[r] = t.status; }
    const issues = Object.entries(regWorst)
      .filter(([, st]) => st !== "green" && st !== "excluded")
      .map(([r, st]) => `<div class="tt-row"><span class="led led--${st}"></span> ${REG_LABEL[r]} · ${st}</div>`)
      .join("");
    attachTip(rollLed, `<b>${pkg.id}</b> · rollup = ${pkg.rollup}${issues ? "<div style='margin-top:4px;opacity:.8'>not yet current on:</div>" + issues : "<div class='tt-row'>current on every registry ✓</div>"}`);
    a.append(rollLed, el("span", { class: "pkg-name", text: pkg.id }));
    if ((pkg.flags || []).includes("source_ahead")) a.append(el("span", { class: "pkg-flag", attrs: { title: "repo manifest ahead of the latest prod tag" }, text: "ahead" }));
    cPkg.appendChild(a);
    tr.appendChild(cPkg);

    const src = pkg.source || {};
    tr.appendChild(el("td", { class: "c-ver", text: src.manifest_version ? `v${src.manifest_version}` : "—" }));

    for (const reg of REGS) {
      const td = el("td", { class: "c-led" });
      const targets = byReg.get(reg);
      if (!targets || !targets.length) { td.appendChild(el("span", { class: "led led--none", attrs: { "aria-label": "no target" } })); tr.appendChild(td); continue; }
      const st = worstState(targets);
      const rep = facade(targets);
      const link = el("a", { attrs: { href: registryUrl(reg, rep.name, pkg.repo), target: "_blank", rel: "noopener" } });
      const dot = led(st);
      if (targets.length > 1) { const wrap = el("span", { class: "led-multi" }); wrap.append(dot, el("span", { class: "badge-n", text: `×${targets.length}` })); link.appendChild(wrap); }
      else link.appendChild(dot);
      const rows = targets.map((t) => `<div class="tt-row"><span class="led led--${t.status}"></span> <b>${t.name}</b> · ${t.status}${t.published_version ? " · v" + t.published_version : ""}</div>`).join("");
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
    const segs = [];
    let total = 0, lower = false;
    for (const t of pkg.targets || []) {
      const b = dlBest(t);
      if (b && b.value > 0) { segs.push({ reg: t.registry, name: t.name, ...b }); total += b.value; if (b.lower) lower = true; }
    }
    if (total > 0) rows.push({ pkg, segs, total, lower });
  }
  rows.sort((a, b) => b.total - a.total);
  if (!rows.length) { box.appendChild(el("p", { class: "admin-note", text: "No download stats available." })); return; }
  const max = rows[0].total;

  for (const row of rows) {
    const r = el("div", { class: "dlrow" });
    const prim = row.segs.slice().sort((a, b) => b.value - a.value)[0];
    r.appendChild(el("a", { class: "dl-name", text: row.pkg.id, attrs: { href: registryUrl(prim.reg, prim.name, row.pkg.repo), target: "_blank", rel: "noopener", title: row.pkg.id } }));
    const bar = el("div", { class: "dlbar", attrs: { style: `width:${Math.max(6, (row.total / max) * 100)}%` } });
    for (const s of row.segs.sort((a, b) => b.value - a.value)) {
      const seg = el("a", { class: "dlseg", attrs: { href: registryUrl(s.reg, s.name, row.pkg.repo), target: "_blank", rel: "noopener", style: `width:${(s.value / row.total) * 100}%;background:${REG_COLOR[s.reg]}` } });
      attachTip(seg, `<b>${s.name}</b><div class="tt-row">${REG_LABEL[s.reg]} · ${s.lower ? "&gt;" : ""}${fmtInt(s.value)} <span style="opacity:.6">(${s.window})</span></div>`);
      bar.appendChild(seg);
    }
    r.appendChild(bar);
    r.appendChild(el("span", { class: "dl-tot", text: (row.lower ? ">" : "") + fmtInt(row.total) }));
    box.appendChild(r);
  }

  const axis = el("div", { class: "dl-axis" });
  for (const reg of REGS) {
    if (!rows.some((r) => r.segs.some((s) => s.reg === reg))) continue;
    axis.appendChild(el("span", {}, [el("span", { class: "dl-swatch", attrs: { style: `background:${REG_COLOR[reg]}` } }), el("span", { text: REG_LABEL[reg] })]));
  }
  axis.appendChild(el("span", { class: "admin-note", text: "≈90-day view · > = lower bound (registry reports a shorter window)" }));
  box.appendChild(axis);
}

// ---- GitHub table ----------------------------------------------------------

function numLink(value, href) {
  if (value == null) return el("td", { class: "num", text: "—" });
  const td = el("td", { class: "num" });
  td.appendChild(el("a", { class: "num", text: fmtInt(value), attrs: { href, target: "_blank", rel: "noopener" } }));
  return td;
}
function renderRepoStats(snap) {
  const box = document.getElementById("repostats");
  box.innerHTML = "";
  const table = el("table", { class: "stats" });
  const thead = el("thead"), hr = el("tr");
  for (const h of ["repo", "★ stars", "forks", "watch", "open PR", "merged", "closed", "issues", "license", "pushed"]) hr.appendChild(el("th", { text: h }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody");
  for (const pkg of snap.packages || []) {
    const s = pkg.repo_stats; if (!s) continue;
    const base = `https://github.com/${OWNER}/${pkg.repo}`;
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
    tr.appendChild(el("td", { class: "num", text: s.license || "—" }));
    tr.appendChild(el("td", { class: "num", text: s.pushed_at ? fmtDate(s.pushed_at) : "—" }));
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
    tr.appendChild(langCell(c && c.by_language ? Object.keys(c.by_language)[0] : null));
    tr.appendChild(el("td", { class: "num", text: fmtInt(a.workflows) }));
    tr.appendChild(numLink(a.total_runs, `${base}/actions`));
    tr.appendChild(el("td", { class: "num", text: a.success_rate != null ? `${a.success_rate}%` : "—" }));
    const concl = (a.last_conclusion || "—").toLowerCase();
    tr.appendChild(el("td", {}, [el("span", { class: "conclusion", attrs: { "data-ok": concl === "success" ? "success" : concl === "failure" ? "failure" : "other" }, text: concl })]));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody); box.appendChild(table);
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
    sb.appendChild(el("p", { class: "admin-note", text: `${fmtInt(s.unresolved)} unresolved (14d)` }));
    for (const i of (s.issues || []).slice(0, 8)) {
      const row = el("div", { class: "kv" });
      row.appendChild(el("div", { class: "kv__head" }, [el("span", { class: "kv__name", text: i.title || "—" }), el("span", { class: "conclusion", attrs: { "data-ok": "failure" }, text: i.level || "issue" })]));
      row.appendChild(el("span", { class: "admin-note", text: `${fmtInt(i.count)}× · ${fmtInt(i.userCount)} users` }));
      sb.appendChild(row);
    }
  } else sb.appendChild(el("p", { class: "admin-note", text: `unavailable — ${s.error || "set SENTRY_AUTH_TOKEN"}` }));
  body.appendChild(sb);

  // visits (GoatCounter)
  const v = admin.visits || {};
  const vb = el("div", { class: "card panel" });
  vb.appendChild(el("h3", { class: "section-h", text: "Pages visits — GoatCounter" }));
  if (v.available) {
    const w = v.windows || {};
    const row = el("div", { class: "chips" });
    for (const [lab, key] of [["7 d", "7d"], ["30 d", "30d"], ["365 d", "365d"], ["all-time", "total"]]) {
      const c = el("span", { class: "chip" });
      c.append(el("span", { class: "count", text: fmtInt(w[key]) }), el("span", { class: "muted", text: lab }));
      row.appendChild(c);
    }
    vb.appendChild(row);
  } else {
    vb.appendChild(el("p", { class: "admin-note", text: `unavailable — ${v.error || "set GOATCOUNTER_TOKEN"}` }));
  }
  body.appendChild(vb);

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
  function frame(now) {
    waves.forEach((w, i) => { lines[i].setAttribute("d", linePath(w, now)); areas[i].setAttribute("d", areaPath(w, now)); });
    if (now - last > 360 && dots.length < 14) {
      last = now;
      const w = waves[(Math.random() * 3) | 0], x = 80 + Math.random() * (W - 160);
      const e = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      e.setAttribute("r", "3"); e.setAttribute("fill", w.dot); e.classList.add("wave-dot"); e.style.color = w.col;
      dotsG.appendChild(e); dots.push({ e, w, x, born: now });
    }
    for (let i = dots.length - 1; i >= 0; i--) {
      const d = dots[i], age = now - d.born, life = 2600;
      if (age > life) { d.e.remove(); dots.splice(i, 1); continue; }
      d.e.setAttribute("cx", d.x); d.e.setAttribute("cy", yAt(d.w, d.x, now).toFixed(1));
      d.e.setAttribute("opacity", (Math.sin((age / life) * Math.PI) * 0.9).toFixed(2));
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
