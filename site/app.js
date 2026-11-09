/* Round-Trip AI dashboard. Vanilla JS plus D3, both vendored locally.
 * Every figure carries a "show sources" affordance that resolves to the ledger
 * rows that produced it. */
(function () {
"use strict";

const S = { ledger: null, metrics: null, stress: null, news: null, history: null };
const tip = document.getElementById("tip");
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const FAM_VAR = { ownership: "--series-1", credit: "--series-2", demand: "--series-3" };

/* ---------- formatting ---------- */
function usd(x) {
  if (x === null || x === undefined || isNaN(x)) return "n/a";
  const a = Math.abs(x);
  if (a === 0) return "$0";
  for (const [c, s] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (a >= c) return "$" + (x / c).toFixed(a >= 1e12 ? 2 : 1) + s;
  }
  return "$" + Math.round(x).toLocaleString();
}
const pct = (x, d) => (x === null || x === undefined || isNaN(x))
  ? "n/a" : (100 * x).toFixed(d === undefined ? 1 : d) + "%";
const esc = (s) => String(s === null || s === undefined ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

/* ---------- tooltip ---------- */
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
  tip.style.left = Math.max(8, x) + "px";
  tip.style.top = Math.max(8, y) + "px";
}
const hideTip = () => tip.classList.remove("on");
function hoverable(sel, html) {
  sel.on("mousemove", (ev, d) => showTip(html(d), ev))
     .on("mouseleave", hideTip)
     .on("focus", function (ev, d) { showTip(html(d), { clientX: this.getBoundingClientRect().left,
       clientY: this.getBoundingClientRect().top }); })
     .on("blur", hideTip);
}

/* ---------- source affordance ---------- */
function edgeLine(e) {
  const amt = e.amount_undisclosed ? "<em>no disclosed amount</em>"
    : (e.low === e.high ? usd(e.high) : usd(e.low) + " to " + usd(e.high));
  return `<li><strong>${esc(e.source)} &rarr; ${esc(e.target)}</strong>
    <span class="mono">${esc(e.edge_type)}</span> &middot; ${amt} &middot;
    <span class="pill ${e.conditional ? "cond" : "def"}">${esc(e.status)}</span>
    <span class="tier ${e.tier}">${e.tier}</span>
    <br><span class="note">as of ${esc(e.as_of)}${e.accession ? " &middot; " + esc(e.accession) : ""}
    &middot; <a href="${esc(e.url)}" target="_blank" rel="noopener">source</a></span>
    <div class="q" style="color:var(--text-secondary);font-style:italic">&ldquo;${esc(e.quote)}&rdquo;</div></li>`;
}
function sourceList(edges, intro) {
  if (!edges.length) return `<p class="note">${esc(intro || "No ledger rows.")}</p>`;
  return (intro ? `<p class="note">${esc(intro)}</p>` : "") +
    `<ul class="tight">${edges.map(edgeLine).join("")}</ul>`;
}

/* ---------- small chart helpers ---------- */
function svgRoot(sel, height) {
  const el = d3.select(sel);
  el.selectAll("*").remove();
  const w = Math.max(280, el.node().clientWidth || 520);
  const svg = el.append("svg").attr("viewBox", `0 0 ${w} ${height}`)
    .attr("preserveAspectRatio", "xMinYMin meet");
  return { svg, w, h: height };
}
function xGrid(svg, x, m, h, fmt) {
  const g = svg.append("g");
  x.ticks(5).forEach(t => {
    g.append("line").attr("class", "gridline")
      .attr("x1", x(t)).attr("x2", x(t)).attr("y1", m.top).attr("y2", h - m.bottom);
    g.append("text").attr("class", "axislabel").attr("x", x(t)).attr("y", h - m.bottom + 13)
      .attr("text-anchor", "middle").text(fmt ? fmt(t) : t);
  });
  svg.append("line").attr("class", "baseline")
    .attr("x1", x(x.domain()[0])).attr("x2", x(x.domain()[0]))
    .attr("y1", m.top).attr("y2", h - m.bottom);
}

/* ================= HEADLINE ================= */
function renderHeadline() {
  const m = S.metrics, L = S.ledger;
  const eco = m.ecosystem;
  const c = eco.CENTRAL.rte, lo = eco.RANGE.min, hi = eco.RANGE.max;
  document.getElementById("heroFigure").textContent = pct(c);
  document.getElementById("heroRange").innerHTML =
    `range <strong>${pct(lo)}</strong> to <strong>${pct(hi)}</strong> &middot; ` +
    (eco.RANGE.ordered ? "" : `<span class="pill cond" title="LOWER exceeds CENTRAL for at least one supplier">readings not nested</span> &middot; `) +
    `${usd(eco.CENTRAL.backlog_at_risk)} of ${usd(eco.CENTRAL.backlog_total)} of disclosed backlog`;
  document.getElementById("heroSentence").innerHTML =
    `Roughly <strong>${pct(c)}</strong> (range ${pct(lo)} to ${pct(hi)}) of disclosed ` +
    `backlog depends on a counterparty whose funding traces back to the seller.`;
  const cov = m.coverage;
  document.getElementById("heroCaveat").innerHTML =
    `That percentage is computed over the <strong>${pct(cov.named_share_weighted)}</strong> ` +
    `of this backlog universe that any filing ties to a named customer. The other ` +
    `<strong>${pct(cov.unattributable_weighted)}</strong> names nobody, so the headline is a ` +
    `floor on what is visible, not a measurement of what exists.`;
  document.getElementById("heroAsOf").innerHTML =
    `As of ${esc(m.as_of)} &middot; ${L.counts.edges} ledger edges, tier gate ` +
    `${esc(m.tier_gate.join(" and "))} &middot; T3 sensitivity: ` +
    `${pct(m.sensitivity_T3.ecosystem.CENTRAL.rte)} central`;

  const contributing = [];
  m.suppliers.forEach(s => {
    if (s.rte_central > 0) s.top_counterparties.forEach(t => {
      if (t.rte > 0) contributing.push([s.supplier, t.customer]);
    });
  });
  const relevant = L.edges.filter(e =>
    contributing.some(([i, j]) => (e.source === j && e.target === i) || (e.source === i && e.target === j)));
  document.getElementById("heroSources").innerHTML = sourceList(relevant,
    "Edges that produce a non-zero contribution to the headline:");

  const tiles = [
    { k: "Ledger edges", v: L.counts.edges,
      n: Object.entries(L.counts.by_tier).map(([t, n]) => `${t} ${n}`).join(", ") },
    { k: "Backlog universe", v: usd(cov.backlog_total_high),
      n: `${m.suppliers.length} suppliers with a disclosed figure` },
    { k: "No named customer", v: pct(cov.unattributable_weighted),
      n: cov.suppliers_with_no_named_customer.length
        ? "entirely unnamed: " + cov.suppliers_with_no_named_customer.join(", ")
        : "all suppliers name at least one" },
    { k: "Buyer financed by a seller", v: pct(cov.network_financed_weighted),
      n: "secondary metric, any seller not just this one" },
  ];
  document.getElementById("heroTiles").innerHTML = tiles.map(t =>
    `<div class="tile"><p class="k">${esc(t.k)}</p><div class="v">${esc(t.v)}</div>
     <div class="n">${esc(t.n)}</div></div>`).join("");

  renderBounds();
  renderCoverage();
  renderHistory();
  renderCannotSee();
}

function renderBounds() {
  const data = S.metrics.suppliers.slice().sort((a, b) => b.rte_range_max - a.rte_range_max);
  const m = { top: 8, right: 56, bottom: 26, left: 92 };
  const rowH = 26, h = m.top + m.bottom + data.length * rowH;
  const { svg, w } = svgRoot("#boundsChart", h);
  const maxX = Math.max(0.05, d3.max(data, d => d.rte_range_max) * 1.12);
  const x = d3.scaleLinear([0, maxX], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => (100 * v).toFixed(0) + "%");

  const rows = svg.selectAll("g.row").data(data).join("g").attr("class", "row")
    .attr("transform", (d, i) => `translate(0,${m.top + i * rowH})`);
  rows.append("text").attr("x", m.left - 8).attr("y", rowH / 2 + 4)
    .attr("text-anchor", "end").text(d => d.supplier)
    .style("fill", d => d.confidence === "low" ? css("--text-muted") : css("--text-secondary"));
  rows.append("rect")
    .attr("x", d => x(d.rte_range_min)).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(2, x(d.rte_range_max) - x(d.rte_range_min)))
    .attr("height", 10).attr("rx", 4).attr("fill", css("--band-strong"));
  rows.append("circle")
    .attr("cx", d => x(d.rte_central)).attr("cy", rowH / 2)
    .attr("r", 5).attr("fill", css("--series-1"))
    .attr("stroke", css("--surface-1")).attr("stroke-width", 2);
  rows.append("text").attr("class", "vallabel")
    .attr("x", d => x(d.rte_range_max) + 7).attr("y", rowH / 2 + 4)
    .text(d => pct(d.rte_central));
  hoverable(rows.attr("tabindex", 0), d => `<strong>${esc(d.supplier)}</strong><br>
    LOWER ${pct(d.rte_low)} &middot; CENTRAL ${pct(d.rte_central)} &middot; UPPER ${pct(d.rte_high)}
    ${d.bounds_unordered ? '<br><span class="pill cond">readings not nested</span> LOWER exceeds CENTRAL: this seller funded this buyer heavily relative to the one commitment, but the buyer has many other funders' : ""}<br>
    backlog ${usd(d.backlog_high)} (${esc(d.backlog_basis)}, as of ${esc(d.backlog_as_of)})<br>
    named customers cover ${pct(d.named_customer_share)} of it
    ${d.backlog_flag ? "<br><em>flag: " + esc(d.backlog_flag) + "</em>" : ""}`);

  const used = new Set();
  S.metrics.suppliers.forEach(s => s.top_counterparties.forEach(t => used.add(s.supplier + "|" + t.customer)));
  const rel = S.ledger.edges.filter(e => used.has(e.target + "|" + e.source) || used.has(e.source + "|" + e.target));
  document.getElementById("boundsSources").innerHTML = sourceList(rel,
    "Every demand and funding edge touching a measured supplier:");
}

function renderCoverage() {
  const cov = S.metrics.coverage;
  const data = S.metrics.suppliers.map(s => ({
    supplier: s.supplier, named: s.named_customer_share,
    unnamed: s.unattributable_share, backlog: s.backlog_high,
  })).sort((a, b) => b.backlog - a.backlog);
  const m = { top: 8, right: 70, bottom: 26, left: 92 };
  const rowH = 26, h = m.top + m.bottom + data.length * rowH;
  const { svg, w } = svgRoot("#coverageChart", h);
  const x = d3.scaleLinear([0, 1], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => (100 * v).toFixed(0) + "%");
  const rows = svg.selectAll("g.row").data(data).join("g").attr("class", "row")
    .attr("transform", (d, i) => `translate(0,${m.top + i * rowH})`).attr("tabindex", 0);
  rows.append("text").attr("x", m.left - 8).attr("y", rowH / 2 + 4)
    .attr("text-anchor", "end").text(d => d.supplier);
  // 2px surface gap between the two stacked segments
  rows.append("rect").attr("x", x(0)).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(0, x(d.named) - x(0)))
    .attr("height", 10).attr("rx", 4).attr("fill", css("--series-3"));
  rows.append("rect").attr("x", d => x(d.named) + 2).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(0, x(1) - x(d.named) - 2))
    .attr("height", 10).attr("rx", 4).attr("fill", css("--grid"));
  rows.append("text").attr("class", "vallabel")
    .attr("x", x(1) + 7).attr("y", rowH / 2 + 4).text(d => pct(d.named, 0) + " named");
  hoverable(rows, d => `<strong>${esc(d.supplier)}</strong><br>
    backlog ${usd(d.backlog)}<br>named customers ${pct(d.named)}<br>
    unattributable ${pct(d.unnamed)}`);
  document.getElementById("coverageNote").innerHTML =
    `Weighted by backlog, <strong>${pct(cov.unattributable_weighted)}</strong> of this ` +
    `universe is owed by customers no filing names. ` +
    (cov.suppliers_with_no_named_customer.length
      ? `<strong>${esc(cov.suppliers_with_no_named_customer.join(" and "))}</strong> ` +
        `name no customer at all, so their exposure is unmeasurable rather than low.`
      : "");
}

function renderHistory() {
  const v = (S.history && S.history.vintages) || [];
  if (v.length < 2) { document.getElementById("historyChart").innerHTML =
    '<p class="note">Not enough vintages yet.</p>'; return; }
  const m = { top: 12, right: 18, bottom: 30, left: 46 };
  const h = 240;
  const { svg, w } = svgRoot("#historyChart", h);
  const xs = v.map(d => new Date(d.snapshot));
  const x = d3.scaleTime(d3.extent(xs), [m.left, w - m.right]);
  const y = d3.scaleLinear([0, Math.max(0.05, d3.max(v, d => d.upper) * 1.1)], [h - m.bottom, m.top]);
  y.ticks(4).forEach(t => {
    svg.append("line").attr("class", "gridline").attr("x1", m.left).attr("x2", w - m.right)
      .attr("y1", y(t)).attr("y2", y(t));
    svg.append("text").attr("class", "axislabel").attr("x", m.left - 7).attr("y", y(t) + 3)
      .attr("text-anchor", "end").text((100 * t).toFixed(0) + "%");
  });
  x.ticks(Math.min(6, v.length)).forEach(t => {
    svg.append("text").attr("class", "axislabel").attr("x", x(t)).attr("y", h - m.bottom + 14)
      .attr("text-anchor", "middle").text(d3.timeFormat("%b %Y")(t));
  });
  const area = d3.area().x((d, i) => x(xs[i])).y0(d => y(d.lower)).y1(d => y(d.upper))
    .curve(d3.curveMonotoneX);
  svg.append("path").datum(v).attr("d", area).attr("fill", css("--band")).attr("opacity", 0.55);
  const line = d3.line().x((d, i) => x(xs[i])).y(d => y(d.central)).curve(d3.curveMonotoneX);
  svg.append("path").datum(v).attr("d", line).attr("fill", "none")
    .attr("stroke", css("--series-1")).attr("stroke-width", 2);
  const pts = svg.selectAll("circle.pt").data(v).join("circle").attr("class", "pt")
    .attr("cx", (d, i) => x(xs[i])).attr("cy", d => y(d.central)).attr("r", 4.5)
    .attr("fill", css("--series-1")).attr("stroke", css("--surface-1"))
    .attr("stroke-width", 2).attr("tabindex", 0);
  hoverable(pts, d => `<strong>${esc(d.snapshot)}</strong><br>
    central ${pct(d.central)} (${pct(d.lower)} to ${pct(d.upper)})<br>
    ${d.edges} edges &middot; backlog ${usd(d.backlog_total)}`);
  svg.append("text").attr("class", "vallabel").attr("x", x(xs[xs.length - 1]) - 4)
    .attr("y", y(v[v.length - 1].central) - 11).attr("text-anchor", "end")
    .text(pct(v[v.length - 1].central));
  document.getElementById("historyNote").innerHTML =
    `The early points are high for a mechanical reason, not a substantive one: in ` +
    `late 2025 only a few backlog denominators had been filed, so the same handful ` +
    `of deals was divided by a much smaller base. The backlog universe grows from ` +
    `${usd(v[0].backlog_total)} to ${usd(v[v.length - 1].backlog_total)} across this ` +
    `series. Read the trend as a statement about disclosure arriving, not about ` +
    `exposure falling.`;
}

function renderCannotSee() {
  const items = S.ledger.cannot_see || [];
  document.getElementById("cannotSee").innerHTML = items.map(g =>
    `<div style="border-left:3px solid var(--grid);padding:6px 0 6px 12px;margin-bottom:12px">
      <strong>${esc(g.gap)}</strong>
      ${g.size_usd ? ` <span class="chip">${usd(g.size_usd)}</span>` : ""}
      <div class="note" style="color:var(--text-secondary);margin-top:3px">${esc(g.detail)}</div>
      <div class="chiprow" style="margin-top:6px">${(g.affects || []).map(a =>
        `<span class="chip">${esc(a)}</span>`).join("")}</div>
    </div>`).join("");
}

/* ================= GRAPH ================= */
const G = { tiers: new Set(["T1", "T2"]), fams: new Set(["ownership", "credit", "demand"]),
            view: "force", undisclosed: true, sim: null };

function visibleEdges() {
  return S.ledger.edges.filter(e =>
    G.tiers.has(e.tier) && G.fams.has(e.family) &&
    (G.undisclosed || !e.amount_undisclosed));
}

function renderGraphControls() {
  const tiers = ["T1", "T2", "T3"];
  document.getElementById("tierToggles").innerHTML = tiers.map(t =>
    `<button class="btn" data-tier="${t}" aria-pressed="${G.tiers.has(t)}">${t}</button>`).join("");
  document.querySelectorAll("[data-tier]").forEach(b => b.onclick = () => {
    const t = b.dataset.tier;
    if (G.tiers.has(t)) G.tiers.delete(t); else G.tiers.add(t);
    b.setAttribute("aria-pressed", G.tiers.has(t));
    drawGraph();
  });
  const fams = S.ledger.families;
  const shortFam = S.ledger.families_short || fams;
  document.getElementById("familyToggles").innerHTML = Object.keys(fams).map(k =>
    `<button class="btn" data-fam="${k}" aria-pressed="true">${esc(shortFam[k] || fams[k])}</button>`).join("");
  document.querySelectorAll("[data-fam]").forEach(b => b.onclick = () => {
    const f = b.dataset.fam;
    if (G.fams.has(f)) G.fams.delete(f); else G.fams.add(f);
    b.setAttribute("aria-pressed", G.fams.has(f));
    drawGraph();
  });
  document.getElementById("showUndisclosed").onchange = (e) => {
    G.undisclosed = e.target.checked; drawGraph();
  };
  document.getElementById("viewForce").onclick = () => setView("force");
  document.getElementById("viewSankey").onclick = () => setView("sankey");
  document.getElementById("graphLegend").innerHTML =
    Object.entries(fams).map(([k, v]) =>
      `<span class="item"><span class="swatch" style="background:${css(FAM_VAR[k])}"></span>${esc(v)}</span>`).join("") +
    `<span class="item"><svg width="26" height="8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4"
      stroke="${css("--text-muted")}" stroke-width="2" stroke-dasharray="5 4"/></svg>conditional or letter of intent</span>` +
    `<span class="item"><span class="swatch" style="background:${css("--text-muted")};height:1px"></span>no disclosed amount</span>`;
}
function setView(v) {
  G.view = v;
  document.getElementById("viewForce").setAttribute("aria-pressed", v === "force");
  document.getElementById("viewSankey").setAttribute("aria-pressed", v === "sankey");
  drawGraph();
}

function drawGraph() {
  const edges = visibleEdges();
  const el = d3.select("#graph");
  el.selectAll("*").remove();
  if (G.sim) { G.sim.stop(); G.sim = null; }
  if (!edges.length) {
    el.append("text").attr("x", 20).attr("y", 30).text("No edges match these filters.");
    return;
  }
  const W = el.node().clientWidth || 900, H = 540;
  el.attr("viewBox", `0 0 ${W} ${H}`);
  const names = Array.from(new Set(edges.flatMap(e => [e.source, e.target]))).sort();
  const meta = new Map(S.ledger.nodes.map(n => [n.node, n]));
  const maxAmt = d3.max(edges, e => e.weighted_central) || 1;
  const width = d3.scaleSqrt([0, maxAmt], [1.2, 13]);
  const nodeR = d3.scaleSqrt([0, d3.max(names, n => {
    const m = meta.get(n) || {};
    return (m.funding_out || 0) + (m.demand_in || 0) + (m.funding_in || 0) + (m.demand_out || 0);
  }) || 1], [6, 22]);

  const g = el.append("g");
  const defs = el.append("defs");
  Object.entries(FAM_VAR).forEach(([k, v]) => {
    defs.append("marker").attr("id", "arw-" + k).attr("viewBox", "0 0 10 10")
      .attr("refX", 9).attr("refY", 5).attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto-start-reverse")
      .append("path").attr("d", "M0,1L9,5L0,9z").attr("fill", css(v));
  });

  if (G.view === "sankey") { drawSankey(g, edges, names, W, H, width); return; }

  const nodes = names.map(n => ({ id: n, meta: meta.get(n) || {} }));
  const links = edges.map(e => ({ ...e, sourceId: e.source, targetId: e.target }));
  const byId = new Map(nodes.map(n => [n.id, n]));
  links.forEach(l => { l.source = byId.get(l.sourceId); l.target = byId.get(l.targetId); });

  const link = g.append("g").selectAll("path").data(links).join("path")
    .attr("class", "link")
    .attr("stroke", d => css(FAM_VAR[d.family]))
    .attr("stroke-width", d => d.amount_undisclosed ? 1 : width(d.weighted_central))
    .attr("stroke-dasharray", d => d.conditional ? "6 5" : null)
    .attr("marker-end", d => `url(#arw-${d.family})`)
    .attr("tabindex", 0);
  hoverable(link, edgeTipHtml);
  link.on("click", (ev, d) => selectEdge(d));
  link.on("keydown", (ev, d) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectEdge(d); } });

  const node = g.append("g").selectAll("g").data(nodes).join("g").attr("class", "node")
    .attr("tabindex", 0);
  node.append("circle")
    .attr("r", d => nodeR((d.meta.funding_out || 0) + (d.meta.demand_in || 0) +
                          (d.meta.funding_in || 0) + (d.meta.demand_out || 0)))
    .attr("fill", d => d.meta.is_private ? css("--text-muted") : css("--series-1"));
  node.append("text").attr("x", d => nodeR(1) + 6).attr("y", 4)
    .text(d => d.id + (d.meta.is_private ? " •" : ""));
  hoverable(node, d => `<strong>${esc(d.id)}</strong>
    ${d.meta.is_private ? '<span class="pill priv">private, does not file</span>' : ""}<br>
    funding out ${usd(d.meta.funding_out)} &middot; funding in ${usd(d.meta.funding_in)}<br>
    commitments out ${usd(d.meta.demand_out)} &middot; backlog in ${usd(d.meta.demand_in)}<br>
    ${d.meta.cik ? "CIK " + esc(d.meta.cik) : "no SEC filings"}`);

  node.on("mouseenter", (ev, d) => link.classed("dim", l => l.sourceId !== d.id && l.targetId !== d.id))
      .on("mouseleave", () => link.classed("dim", false));

  /* Buyers drift left, sellers right, so the picture reads as money flowing
     left to right rather than as a hairball. Then the simulation is run to
     convergence synchronously before the first paint, so the layout does not
     visibly settle and a headless capture sees the finished graph. */
  const outDeg = new Map(nodes.map(n => [n.id, 0]));
  const inDeg = new Map(nodes.map(n => [n.id, 0]));
  links.forEach(l => {
    outDeg.set(l.sourceId, (outDeg.get(l.sourceId) || 0) + 1);
    inDeg.set(l.targetId, (inDeg.get(l.targetId) || 0) + 1);
  });
  const bias = d => {
    const o = outDeg.get(d.id) || 0, i = inDeg.get(d.id) || 0;
    return (o + i) === 0 ? 0 : (i - o) / (i + o);     // +1 pure seller, -1 pure funder
  };
  nodes.forEach(d => { d.x = W / 2 + bias(d) * W * 0.3; d.y = H / 2 + (Math.random() - 0.5) * H * 0.6; });

  G.sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(150).strength(0.25))
    .force("charge", d3.forceManyBody().strength(-1400).distanceMax(560))
    .force("x", d3.forceX(d => W / 2 + bias(d) * W * 0.32).strength(0.16))
    .force("y", d3.forceY(H / 2).strength(0.05))
    .force("collide", d3.forceCollide(46).strength(0.9))
    .alpha(1).alphaDecay(0.022)
    .on("tick", () => {
      link.attr("d", d => {
        const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
        const dr = Math.hypot(dx, dy) * 1.9 || 1;
        return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
      });
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });
  G.sim.stop();
  for (let i = 0; i < 320; i++) G.sim.tick();
  const pad = 46;
  nodes.forEach(d => {
    d.x = Math.max(pad + 40, Math.min(W - pad - 60, d.x));
    d.y = Math.max(pad, Math.min(H - pad, d.y));
  });
  G.sim.tick();
  G.sim.restart().alpha(0.05);
  node.call(d3.drag()
    .on("start", (ev, d) => { if (!ev.active) G.sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
    .on("end", (ev, d) => { if (!ev.active) G.sim.alphaTarget(0); d.fx = null; d.fy = null; }));
}

function drawSankey(g, edges, names, W, H, width) {
  /* Three columns: funders on the left, labs and intermediaries in the middle,
     sellers on the right. A node that is both appears in the middle. */
  const isFunder = new Set(edges.filter(e => e.direction === "funding").map(e => e.source));
  const isSeller = new Set(edges.filter(e => e.direction === "demand").map(e => e.target));
  const col = new Map();
  names.forEach(n => {
    if (isFunder.has(n) && isSeller.has(n)) col.set(n, 1);
    else if (isFunder.has(n)) col.set(n, 0);
    else if (isSeller.has(n)) col.set(n, 2);
    else col.set(n, 1);
  });
  const cols = [[], [], []];
  names.forEach(n => cols[col.get(n)].push(n));
  const xs = [W * 0.14, W * 0.5, W * 0.86];
  const pos = new Map();
  cols.forEach((list, ci) => {
    const step = (H - 60) / Math.max(1, list.length);
    list.sort().forEach((n, i) => pos.set(n, { x: xs[ci], y: 36 + step * (i + 0.5) }));
  });
  const link = g.append("g").selectAll("path").data(edges).join("path")
    .attr("class", "link")
    .attr("d", d => {
      const a = pos.get(d.source), b = pos.get(d.target);
      const mx = (a.x + b.x) / 2;
      return `M${a.x},${a.y}C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`;
    })
    .attr("stroke", d => css(FAM_VAR[d.family]))
    .attr("stroke-width", d => d.amount_undisclosed ? 1 : width(d.weighted_central))
    .attr("stroke-dasharray", d => d.conditional ? "6 5" : null)
    .attr("marker-end", d => `url(#arw-${d.family})`)
    .attr("tabindex", 0);
  hoverable(link, edgeTipHtml);
  link.on("click", (ev, d) => selectEdge(d));
  const meta = new Map(S.ledger.nodes.map(n => [n.node, n]));
  const node = g.append("g").selectAll("g").data(names).join("g").attr("class", "node")
    .attr("transform", n => `translate(${pos.get(n).x},${pos.get(n).y})`);
  node.append("circle").attr("r", 7)
    .attr("fill", n => (meta.get(n) || {}).is_private ? css("--text-muted") : css("--series-1"));
  node.append("text")
    .attr("x", n => col.get(n) === 2 ? 11 : (col.get(n) === 0 ? -11 : 0))
    .attr("y", n => col.get(n) === 1 ? -12 : 4)
    .attr("text-anchor", n => col.get(n) === 0 ? "end" : (col.get(n) === 2 ? "start" : "middle"))
    .text(n => n);
  ["Funders", "Labs and intermediaries", "Sellers"].forEach((t, i) => {
    g.append("text").attr("class", "axislabel").attr("x", xs[i]).attr("y", 16)
      .attr("text-anchor", "middle").text(t);
  });
}

function edgeTipHtml(d) {
  const amt = d.amount_undisclosed ? "<em>no disclosed amount</em>"
    : (d.low === d.high ? usd(d.high) : usd(d.low) + " to " + usd(d.high));
  return `<strong>${esc(d.source)} &rarr; ${esc(d.target)}</strong><br>
    <span class="mono">${esc(d.edge_type)}</span><br>${amt} &middot; ${esc(d.basis)}<br>
    <span class="pill ${d.conditional ? "cond" : "def"}">${esc(d.status)}</span>
    <span class="tier ${d.tier}">${d.tier}</span><br>
    <span class="q">&ldquo;${esc(d.quote)}&rdquo;</span><br>
    <span class="note">click for the source</span>`;
}

function selectEdge(d) {
  document.getElementById("edgeDetail").innerHTML =
    `<div style="border:1px solid var(--border);border-radius:10px;padding:13px">
      <h3 style="margin-top:0">${esc(d.source)} &rarr; ${esc(d.target)}</h3>
      <dl class="kv">
        <dt>Edge type</dt><dd class="mono">${esc(d.edge_type)}</dd>
        <dt>Amount</dt><dd>${d.amount_undisclosed ? "no disclosed amount"
          : (d.low === d.high ? usd(d.high) : usd(d.low) + " to " + usd(d.high))} (${esc(d.basis)})</dd>
        <dt>Weighted, central</dt><dd>${usd(d.weighted_central)}</dd>
        <dt>Status</dt><dd>${esc(d.status)}</dd>
        <dt>Conditions</dt><dd>${esc(d.conditions) || "none disclosed"}</dd>
        <dt>Evidence</dt><dd><span class="tier ${d.tier}">${d.tier}</span>
          ${d.accession ? " &middot; " + esc(d.accession) : ""}</dd>
        <dt>As of</dt><dd>${esc(d.as_of)}</dd>
        <dt>Term</dt><dd>${d.term_start || d.term_end
          ? esc(d.term_start) + " to " + esc(d.term_end) + (d.term_assumed ? " (assumed)" : "")
          : "not disclosed"}</dd>
      </dl>
      <p style="font-style:italic;color:var(--text-secondary);margin:9px 0 4px">&ldquo;${esc(d.quote)}&rdquo;</p>
      <p><a href="${esc(d.url)}" target="_blank" rel="noopener">Open the source document</a></p>
      ${d.notes ? `<p class="note">${esc(d.notes)}</p>` : ""}
      <p class="mono note">${esc(d.edge_id)}</p>
    </div>`;
  document.getElementById("edgeDetail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ================= SUPPLIER CARDS ================= */
function renderSuppliers() {
  const html = S.metrics.suppliers.map(s => {
    const tops = s.top_counterparties.slice().sort((a, b) => b.D - a.D);
    const rel = S.ledger.edges.filter(e => e.target === s.supplier || e.source === s.supplier);
    const gaps = (S.ledger.cannot_see || []).filter(g => (g.affects || []).includes(s.supplier));
    return `<div class="card">
      <h2>${esc(s.supplier)} ${s.confidence === "low"
        ? '<span class="pill cond">low confidence</span>' : ""}</h2>
      <dl class="kv">
        <dt>Disclosed backlog</dt><dd>${s.backlog_low === s.backlog_high
          ? usd(s.backlog_high) : usd(s.backlog_low) + " to " + usd(s.backlog_high)}</dd>
        <dt>Basis</dt><dd class="mono">${esc(s.backlog_basis)}</dd>
        <dt>As of</dt><dd>${esc(s.backlog_as_of)}</dd>
        <dt>Round-trip exposure</dt><dd><strong>${pct(s.rte_central)}</strong>
          (range ${pct(s.rte_range_min)} to ${pct(s.rte_range_max)})</dd>
        <dt>Three readings</dt><dd>LOWER ${pct(s.rte_low)} &middot; CENTRAL ${pct(s.rte_central)}
          &middot; UPPER ${pct(s.rte_high)}${s.bounds_unordered
            ? ' <span class="pill cond">not nested</span>' : ""}</dd>
        <dt>Named customers cover</dt><dd>${pct(s.named_customer_share)}</dd>
        <dt>Buyer financed by any seller</dt><dd>${pct(s.network_financed_share)}</dd>
      </dl>
      <h3>Top counterparties</h3>
      ${tops.length ? `<div class="tablewrap"><table>
        <thead><tr><th>Customer</th><th class="num">Share of backlog</th>
        <th class="num">Provenance</th><th class="num">Contribution</th></tr></thead>
        <tbody>${tops.map(t => `<tr>
          <td>${esc(t.customer)}${t.is_private ? ' <span class="pill priv">private</span>' : ""}</td>
          <td class="num">${pct(t.D)}</td><td class="num">${pct(t.provenance)}</td>
          <td class="num">${pct(t.rte)}</td></tr>`).join("")}</tbody></table></div>`
        : '<p class="note">No customer is named in any filing retrieved. Its exposure is unmeasurable, not zero.</p>'}
      ${(s.financiers_by_customer && Object.keys(s.financiers_by_customer).length)
        ? `<p class="note" style="margin-top:8px">Customers financed by a seller of compute: ` +
          Object.entries(s.financiers_by_customer).map(([c, f]) =>
            `${esc(c)} (by ${esc(f.join(", "))})`).join("; ") + `.</p>` : ""}
      <h3>What we cannot see</h3>
      ${gaps.length ? `<ul class="tight">${gaps.map(g =>
        `<li><strong>${esc(g.gap)}</strong> ${esc(g.detail)}</li>`).join("")}</ul>`
        : '<p class="note">No supplier-specific gap recorded beyond the ecosystem-wide ones.</p>'}
      <details class="sources"><summary>Show sources</summary>
        <div>${sourceList(rel)}
        ${s.backlog_quote ? `<p class="note">Backlog denominator:
          &ldquo;${esc(s.backlog_quote)}&rdquo;
          ${s.backlog_source_url ? `<a href="${esc(s.backlog_source_url)}" target="_blank" rel="noopener">source</a>` : ""}
          ${s.backlog_accession ? " &middot; " + esc(s.backlog_accession) : ""}</p>` : ""}</div>
      </details>
    </div>`;
  }).join("");
  document.getElementById("supplierCards").innerHTML = html;
}

/* ================= CYCLES ================= */
function renderCycles() {
  const st = S.metrics.structure;
  document.getElementById("cycLen").textContent = S.ledger.config.structure
    ? S.ledger.config.structure.max_cycle_len : 6;
  const cyc = st.cycles;
  if (!cyc.length) {
    document.getElementById("cyclesList").innerHTML = '<p class="note">No cycles detected.</p>';
  } else {
    document.getElementById("cyclesList").innerHTML = cyc.map((c, i) => {
      const path = c.nodes.concat([c.nodes[0]]);
      const legEdges = c.legs.flatMap(l => S.ledger.edges.filter(e =>
        e.source === l.source && e.target === l.target));
      return `<div style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:11px">
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;justify-content:space-between">
          <strong>${path.map(esc).join(" &rarr; ")}</strong>
          <span class="chip">bottleneck ${usd(c.bottleneck_usd)}</span>
        </div>
        <p class="note" style="margin:6px 0 0">${c.is_round_trip
          ? "Round trip: at least one leg is funding and at least one is committed demand."
          : "Not a round trip: every leg is the same family."} Length ${c.length}.</p>
        <div class="tablewrap" style="margin-top:8px"><table>
          <thead><tr><th>Leg</th><th>Families</th><th class="num">Weighted amount</th></tr></thead>
          <tbody>${c.legs.map(l => `<tr>
            <td>${esc(l.source)} &rarr; ${esc(l.target)}</td>
            <td class="mono" style="font-size:0.78rem">${esc(l.edge_types.join(", "))}</td>
            <td class="num">${usd(l.amount)}${Math.abs(l.amount - c.bottleneck_usd) < 1
              ? ' <span class="pill cond">bottleneck</span>' : ""}</td></tr>`).join("")}
          </tbody></table></div>
        <details class="sources"><summary>Show sources</summary><div>${sourceList(legEdges)}</div></details>
      </div>`;
    }).join("");
  }
  barChart("#prChart", Object.entries(st.pagerank_funding).map(([k, v]) => ({ k, v })),
    v => v.toFixed(3), "--series-1");
  barChart("#btChart", Object.entries(st.betweenness).filter(([, v]) => v > 0)
    .map(([k, v]) => ({ k, v })), v => v.toFixed(3), "--series-2");
  document.getElementById("sccNote").textContent = st.sccs.length
    ? "Strongly connected components with more than one node: " +
      st.sccs.map(c => c.join(", ")).join(" | ") +
      ". Every member of such a component can reach every other, so none of them can be analysed in isolation."
    : "No multi-node strongly connected component, so no mutual-dependency cluster.";
}

function barChart(sel, data, fmt, colourVar) {
  data = data.slice().sort((a, b) => b.v - a.v).slice(0, 10);
  if (!data.length) { d3.select(sel).html('<p class="note">No data.</p>'); return; }
  const m = { top: 6, right: 54, bottom: 22, left: 86 };
  const rowH = 23, h = m.top + m.bottom + data.length * rowH;
  const { svg, w } = svgRoot(sel, h);
  const x = d3.scaleLinear([0, d3.max(data, d => d.v) * 1.12], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => fmt(v));
  const rows = svg.selectAll("g").data(data).join("g")
    .attr("transform", (d, i) => `translate(0,${m.top + i * rowH})`).attr("tabindex", 0);
  rows.append("text").attr("x", m.left - 8).attr("y", rowH / 2 + 4)
    .attr("text-anchor", "end").text(d => d.k);
  rows.append("rect").attr("x", x(0)).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(1, x(d.v) - x(0))).attr("height", 10)
    .attr("rx", 4).attr("fill", css(colourVar));
  rows.append("text").attr("class", "vallabel").attr("x", d => x(d.v) + 7)
    .attr("y", rowH / 2 + 4).text(d => fmt(d.v));
  hoverable(rows, d => `<strong>${esc(d.k)}</strong><br>${fmt(d.v)}`);
}

/* ================= STRESS LAB ================= */
const SL = { net: null, scenario: null, custom: false };

function renderStress() {
  const sc = S.stress.scenarios;
  document.getElementById("scenarioBtns").innerHTML =
    Object.entries(sc).map(([k, v]) =>
      `<button class="btn" data-sc="${k}" aria-pressed="false">${esc(v.label)}</button>`).join("") +
    `<button class="btn" data-sc="__custom" aria-pressed="false">Custom</button>`;
  document.querySelectorAll("[data-sc]").forEach(b => b.onclick = () => applyScenario(b.dataset.sc));
  ["sShock", "sPass", "sCap", "sLoi", "sCond"].forEach(id =>
    document.getElementById(id).oninput = () => { SL.custom = true; runStress(); });
  document.getElementById("sBound").onchange = () => runStress();
  document.getElementById("mcDraws").textContent =
    (S.stress.monte_carlo.draws || 0).toLocaleString();
  renderMonteCarlo();
  renderTornado();
  renderMethodTable();
  document.getElementById("baselineNote").innerHTML = esc(S.stress.baseline_no_shock.note);
  applyScenario(Object.keys(sc)[0]);
}

function applyScenario(key) {
  document.querySelectorAll("[data-sc]").forEach(b =>
    b.setAttribute("aria-pressed", b.dataset.sc === key));
  if (key === "__custom") { SL.custom = true; SL.scenario = null; runStress(); return; }
  const p = S.stress.scenarios[key];
  SL.scenario = key; SL.custom = false;
  const vals = Object.values(p.shock);
  const mean = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  document.getElementById("sShock").value = Math.round(mean * 100);
  document.getElementById("sPass").value = Math.round(p.passthrough * 100);
  document.getElementById("sCap").value = Math.round(p.capacity_to_invest * 100);
  const sw = S.ledger.status_weights;
  document.getElementById("sLoi").value = Math.round(sw.LOI_nonbinding.central * 100);
  document.getElementById("sCond").value = Math.round(sw.conditional.central * 100);
  runStress();
}

function currentShock() {
  const x = +document.getElementById("sShock").value / 100;
  if (SL.scenario && !SL.custom) {
    const base = S.stress.scenarios[SL.scenario].shock;
    const vals = Object.values(base);
    const mean = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    if (mean > 0) {
      const scale = x / mean;
      const out = {};
      Object.entries(base).forEach(([k, v]) => { out[k] = Math.min(1, v * scale); });
      return out;
    }
    return base;
  }
  const labs = S.ledger.nodes.filter(n => n.is_private && n.role !== "investor").map(n => n.node);
  const out = {}; labs.forEach(l => { out[l] = x; });
  return out;
}

function runStress() {
  const L = S.ledger;
  const bound = document.getElementById("sBound").value;
  const pass = +document.getElementById("sPass").value / 100;
  const cap = +document.getElementById("sCap").value / 100;
  const loi = +document.getElementById("sLoi").value / 100;
  const cond = +document.getElementById("sCond").value / 100;
  ["Shock", "Pass", "Cap", "Loi", "Cond"].forEach(k => {
    const el = document.getElementById("o" + k);
    const src = document.getElementById("s" + k);
    el.textContent = (+src.value) + "%";
  });
  const net = Cascade.buildNetwork(L.edges, L.backlog_rows, {
    bound, tiers: L.config.tiers.headline_allowed, weights: L.status_weights,
    assumedTerm: L.config.amounts.assumed_term_years,
    loiWeight: loi, conditionalWeight: cond,
  });
  const shock = currentShock();
  const res = Cascade.cascade(net, shock, pass, cap,
    L.config.stress.fixed_point_tol, L.config.stress.max_iter);
  const en = Cascade.eisenbergNoe(net, shock, pass);
  const dr = Cascade.debtRank(net, shock);

  document.getElementById("stressTiles").innerHTML = [
    { k: "Backlog at risk", v: pct(res.ecosystem_at_risk_share),
      n: usd(res.ecosystem_at_risk_usd) },
    { k: "Fixed point", v: res.iterations + " iters",
      n: res.converged ? "converged, residual < 1e-9" : "did not converge" },
    { k: "Eisenberg-Noe", v: pct(en.ecosystem_at_risk_share),
      n: "minus its no-shock baseline " + pct(S.stress.baseline_no_shock.eisenberg_noe) },
    { k: "DebtRank", v: pct(dr.ecosystem_at_risk_share), n: dr.rounds + " propagation rounds" },
  ].map(t => `<div class="tile"><p class="k">${esc(t.k)}</p><div class="v">${esc(t.v)}</div>
    <div class="n">${esc(t.n)}</div></div>`).join("");

  const rows = net.suppliers.map(s => ({
    supplier: s,
    cascade: res.backlog_at_risk_share[s] || 0,
    en: en.backlog_at_risk_share[s] || 0,
    dr: dr.backlog_at_risk_share[s] || 0,
    usd: res.backlog_at_risk_usd[s] || 0,
  })).sort((a, b) => b.cascade - a.cascade);
  groupedBars("#stressChart", rows);
  document.getElementById("stressLegend").innerHTML =
    [["--series-1", "Cascade"], ["--series-2", "Eisenberg-Noe"], ["--series-3", "DebtRank"]]
      .map(([v, l]) => `<span class="item"><span class="swatch" style="background:${css(v)};height:9px;width:9px;border-radius:2px"></span>${esc(l)}</span>`).join("");
  document.getElementById("stressShockNote").textContent =
    "Shock applied to: " + (Object.entries(shock).filter(([, v]) => v > 0)
      .map(([k, v]) => `${k} ${(100 * v).toFixed(0)}%`).join(", ") || "nothing");
  document.getElementById("parityNote").innerHTML =
    "This panel recomputes in your browser using a port of the Python model. " +
    "<code>tests/test_js_parity.py</code> runs both on every scenario preset and " +
    "on all three attribution bounds and fails on any difference above 1e-9.";
}

function groupedBars(sel, rows) {
  if (!rows.length) { d3.select(sel).html('<p class="note">No suppliers with a backlog denominator.</p>'); return; }
  const m = { top: 8, right: 56, bottom: 26, left: 92 };
  const groupH = 34, h = m.top + m.bottom + rows.length * groupH;
  const { svg, w } = svgRoot(sel, h);
  const maxX = Math.max(0.02, d3.max(rows, d => Math.max(d.cascade, d.en, d.dr)) * 1.14);
  const x = d3.scaleLinear([0, maxX], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => (100 * v).toFixed(0) + "%");
  const series = [["cascade", "--series-1"], ["en", "--series-2"], ["dr", "--series-3"]];
  const barH = 7, gap = 2;
  const g = svg.selectAll("g.grp").data(rows).join("g").attr("class", "grp")
    .attr("transform", (d, i) => `translate(0,${m.top + i * groupH})`);
  g.append("text").attr("x", m.left - 8).attr("y", groupH / 2 + 4)
    .attr("text-anchor", "end").text(d => d.supplier);
  series.forEach(([key, varName], si) => {
    const b = g.append("rect")
      .attr("x", x(0)).attr("y", 5 + si * (barH + gap))
      .attr("width", d => Math.max(1, x(d[key]) - x(0)))
      .attr("height", barH).attr("rx", 3).attr("fill", css(varName))
      .attr("tabindex", 0);
    hoverable(b, d => `<strong>${esc(d.supplier)}</strong><br>
      cascade ${pct(d.cascade)} (${usd(d.usd)})<br>
      Eisenberg-Noe ${pct(d.en)}<br>DebtRank ${pct(d.dr)}`);
  });
  /* The direct label belongs on the cascade bar, not past the longest bar in the
     group. Nebius is the case that makes this matter: its Eisenberg-Noe bar runs
     most of the width while its cascade value is zero, and a "0.0%" parked at the
     far right reads as a label for the long orange bar. */
  g.append("text").attr("class", "vallabel")
    .attr("x", d => x(d.cascade) + 7).attr("y", 5 + barH)
    .text(d => pct(d.cascade));
}

function renderMonteCarlo() {
  const mc = S.stress.monte_carlo;
  const rows = Object.entries(mc.suppliers).map(([k, v]) => ({ k, ...v }))
    .sort((a, b) => b.median - a.median);
  rows.unshift({ k: "ECOSYSTEM", ...mc.ecosystem });
  const m = { top: 8, right: 60, bottom: 26, left: 96 };
  const rowH = 26, h = m.top + m.bottom + rows.length * rowH;
  const { svg, w } = svgRoot("#mcChart", h);
  const x = d3.scaleLinear([0, Math.max(0.02, d3.max(rows, d => d.p90) * 1.15)], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => (100 * v).toFixed(0) + "%");
  const g = svg.selectAll("g").data(rows).join("g")
    .attr("transform", (d, i) => `translate(0,${m.top + i * rowH})`).attr("tabindex", 0);
  g.append("text").attr("x", m.left - 8).attr("y", rowH / 2 + 4).attr("text-anchor", "end")
    .text(d => d.k).style("font-weight", d => d.k === "ECOSYSTEM" ? 700 : 400);
  g.append("rect").attr("x", d => x(d.p10)).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(2, x(d.p90) - x(d.p10))).attr("height", 10)
    .attr("rx", 4).attr("fill", css("--band-strong"));
  g.append("circle").attr("cx", d => x(d.median)).attr("cy", rowH / 2).attr("r", 5)
    .attr("fill", css("--series-1")).attr("stroke", css("--surface-1")).attr("stroke-width", 2);
  g.append("text").attr("class", "vallabel").attr("x", d => x(d.p90) + 7)
    .attr("y", rowH / 2 + 4).text(d => pct(d.median));
  hoverable(g, d => `<strong>${esc(d.k)}</strong><br>median ${pct(d.median)}<br>
    p10 ${pct(d.p10)} &middot; p90 ${pct(d.p90)}<br>min ${pct(d.min)} &middot; max ${pct(d.max)}`);
}

function renderTornado() {
  const t = S.stress.tornado;
  const m = { top: 8, right: 64, bottom: 26, left: 128 };
  const rowH = 26, h = m.top + m.bottom + t.length * rowH;
  const { svg, w } = svgRoot("#tornadoChart", h);
  const x = d3.scaleLinear([0, Math.max(0.01, d3.max(t, d => d.swing) * 1.18)], [m.left, w - m.right]);
  xGrid(svg, x, m, h, v => (100 * v).toFixed(0) + "pp");
  const g = svg.selectAll("g").data(t).join("g")
    .attr("transform", (d, i) => `translate(0,${m.top + i * rowH})`).attr("tabindex", 0);
  g.append("text").attr("x", m.left - 8).attr("y", rowH / 2 + 4).attr("text-anchor", "end")
    .text(d => d.parameter.replace(/_/g, " "));
  g.append("rect").attr("x", x(0)).attr("y", rowH / 2 - 5)
    .attr("width", d => Math.max(1, x(d.swing) - x(0))).attr("height", 10)
    .attr("rx", 4).attr("fill", css("--series-2"));
  g.append("text").attr("class", "vallabel").attr("x", d => x(d.swing) + 7)
    .attr("y", rowH / 2 + 4).text(d => (100 * d.swing).toFixed(1) + "pp");
  hoverable(g, d => `<strong>${esc(d.parameter)}</strong><br>
    at ${esc(d.low_value)}: ${pct(d.low_result)}<br>at ${esc(d.high_value)}: ${pct(d.high_result)}<br>
    base ${pct(d.base_result)} &middot; swing ${(100 * d.swing).toFixed(2)} pp`);
  document.getElementById("tornadoNote").innerHTML = esc(S.stress.assumption_note) +
    ` The widest driver is <strong>${esc(t[0].parameter.replace(/_/g, " "))}</strong>, ` +
    `worth ${(100 * t[0].swing).toFixed(1)} percentage points against a base of ` +
    `${pct(t[0].base_result)}.`;
}

function renderMethodTable() {
  const base = S.stress.baseline_no_shock;
  const rows = Object.entries(S.stress.scenarios).map(([k, v]) => `
    <tr><td><strong>${esc(v.label)}</strong><div class="note">${esc(v.description)}</div></td>
      <td class="num">${pct(v.cascade.ecosystem_at_risk_share)}</td>
      <td class="num">${pct(v.method_disagreement.eisenberg_noe_excess_over_baseline)}</td>
      <td class="num">${pct(v.debt_rank.ecosystem_at_risk_share)}</td>
      <td class="num">${(100 * v.method_disagreement.cascade_vs_eisenberg_noe_excess_over_baseline).toFixed(2)} pp</td>
      <td>${v.cascade.converged ? v.cascade.iterations + " iters" : "no convergence"}</td></tr>`).join("");
  document.getElementById("methodTable").innerHTML =
    `<thead><tr><th>Scenario</th><th class="num">Cascade</th>
      <th class="num">Eisenberg-Noe, net of baseline</th><th class="num">DebtRank</th>
      <th class="num">Cascade minus EN</th><th>Convergence</th></tr></thead>
     <tbody>${rows}
     <tr><td><em>No shock, baseline</em></td><td class="num">${pct(base.cascade)}</td>
       <td class="num">0.0%</td><td class="num">${pct(base.debt_rank)}</td>
       <td class="num">n/a</td><td>n/a</td></tr></tbody>`;
}

/* ================= NEWS ================= */
function renderNews() {
  const n = S.news;
  document.getElementById("newsLede").textContent =
    `${n.counts.total} items held. ${n.counts.flagged} flagged as financing-relevant. ` +
    `Tagger: ${n.tagger_mode}. Only headline, link, date, publisher and a short ` +
    `snippet are stored; full article text is never fetched.`;
  document.getElementById("newsNote").textContent = n.sources_note;

  const q = n.review_queue || [];
  document.getElementById("queueTable").innerHTML =
    `<thead><tr><th>Date</th><th>Proposed edge</th><th>Tier</th><th>Status</th>
      <th>Headline</th><th>Amount hint</th></tr></thead><tbody>` +
    (q.length ? q.map(r => `<tr>
      <td class="mono">${esc(r.date)}</td>
      <td>${esc(r.source_node)} &rarr; ${esc(r.target_node)}</td>
      <td><span class="tier ${esc(r.evidence_tier)}">${esc(r.evidence_tier)}</span></td>
      <td><span class="pill ${r.status === "promoted" ? "def" : "cond"}">${esc(r.status)}</span></td>
      <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || r.publisher)}</a>
        <div class="note">${esc(r.publisher)}${r.tags ? " &middot; " + esc(r.tags) : ""}</div></td>
      <td class="mono">${esc(r.amount_hint) || "none"}</td></tr>`).join("")
      : '<tr><td colspan="6" class="note">Queue is empty.</td></tr>') + "</tbody>";

  const srcs = Array.from(new Set(n.items.map(i => i.source_kind))).sort();
  document.getElementById("newsSource").innerHTML =
    '<option value="">All</option>' + srcs.map(s => `<option>${esc(s)}</option>`).join("");
  const draw = () => {
    const term = document.getElementById("newsSearch").value.toLowerCase();
    const src = document.getElementById("newsSource").value;
    const flaggedOnly = document.getElementById("newsFlagged").checked;
    const rows = n.items.filter(i =>
      (!src || i.source_kind === src) &&
      (!flaggedOnly || String(i.financing_relevant).toLowerCase() === "true") &&
      (!term || (i.title + " " + i.publisher + " " + i.entities).toLowerCase().includes(term))
    ).slice(0, 220);
    document.getElementById("newsTable").innerHTML =
      `<thead><tr><th>Date</th><th>Source</th><th>Headline</th><th>Entities</th>
        <th>Tags</th><th class="num">Score</th></tr></thead><tbody>` +
      rows.map(i => `<tr>
        <td class="mono">${esc(i.date)}</td>
        <td class="note">${esc(i.publisher)}</td>
        <td><a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>
          ${String(i.financing_relevant).toLowerCase() === "true"
            ? ' <span class="pill cond">flagged</span>' : ""}</td>
        <td class="note">${esc(String(i.entities).split(";").filter(Boolean).join(", "))}</td>
        <td class="note">${esc(String(i.tags).split(";").filter(Boolean).join(", "))}</td>
        <td class="num">${i.score ? (+i.score).toFixed(2) : "n/a"}</td></tr>`).join("") +
      "</tbody>";
  };
  document.getElementById("newsSearch").oninput = draw;
  document.getElementById("newsSource").onchange = draw;
  document.getElementById("newsFlagged").onchange = draw;
  draw();
  renderTimeline();
}

function renderTimeline() {
  const edges = S.ledger.edges.filter(e => e.as_of && /^\d{4}-\d{2}/.test(e.as_of));
  if (!edges.length) return;
  const m = { top: 14, right: 20, bottom: 34, left: 54 };
  const h = 260;
  const { svg, w } = svgRoot("#timelineChart", h);
  const xs = edges.map(e => new Date(e.as_of));
  const x = d3.scaleTime(d3.extent(xs), [m.left, w - m.right]).nice();
  const maxY = d3.max(edges, e => e.weighted_central) || 1;
  const y = d3.scaleLinear([0, maxY * 1.1], [h - m.bottom, m.top]);
  y.ticks(4).forEach(t => {
    svg.append("line").attr("class", "gridline").attr("x1", m.left).attr("x2", w - m.right)
      .attr("y1", y(t)).attr("y2", y(t));
    svg.append("text").attr("class", "axislabel").attr("x", m.left - 7).attr("y", y(t) + 3)
      .attr("text-anchor", "end").text(usd(t));
  });
  x.ticks(5).forEach(t => svg.append("text").attr("class", "axislabel")
    .attr("x", x(t)).attr("y", h - m.bottom + 15).attr("text-anchor", "middle")
    .text(d3.timeFormat("%b %Y")(t)));
  svg.append("line").attr("class", "baseline").attr("x1", m.left).attr("x2", w - m.right)
    .attr("y1", y(0)).attr("y2", y(0));
  const bars = svg.selectAll("rect.ev").data(edges).join("rect").attr("class", "ev")
    .attr("x", (d, i) => x(xs[i]) - 3).attr("width", 6)
    .attr("y", d => d.amount_undisclosed ? y(0) - 8 : y(d.weighted_central))
    .attr("height", d => d.amount_undisclosed ? 8 : Math.max(2, y(0) - y(d.weighted_central)))
    .attr("rx", 3).attr("fill", d => css(FAM_VAR[d.family]))
    .attr("opacity", d => d.amount_undisclosed ? 0.45 : 0.9)
    .attr("tabindex", 0).style("cursor", "pointer");
  hoverable(bars, edgeTipHtml);
  bars.on("click", (ev, d) => { show("graph"); selectEdge(d); });
}

/* ================= LEDGER EXPLORER ================= */
function renderLedger() {
  const L = S.ledger;
  const statuses = Array.from(new Set(L.edges.map(e => e.status))).sort();
  document.getElementById("ledStatus").innerHTML =
    '<option value="">All</option>' + statuses.map(s => `<option>${esc(s)}</option>`).join("");
  document.getElementById("ledFamily").innerHTML =
    '<option value="">All</option>' + Object.entries(L.families)
      .map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  let sortKey = "high", sortDir = -1;
  const cols = [
    ["as_of", "As of", false], ["source", "From", false], ["target", "To", false],
    ["edge_type", "Type", false], ["high", "Amount", true], ["basis", "Basis", false],
    ["status", "Status", false], ["tier", "Tier", false], ["quote", "Quote", false],
  ];
  function draw() {
    const term = document.getElementById("ledSearch").value.toLowerCase();
    const tier = document.getElementById("ledTier").value;
    const st = document.getElementById("ledStatus").value;
    const fam = document.getElementById("ledFamily").value;
    let rows = L.edges.filter(e =>
      (!tier || e.tier === tier) && (!st || e.status === st) && (!fam || e.family === fam) &&
      (!term || [e.source, e.target, e.edge_type, e.quote, e.accession, e.notes, e.status]
        .join(" ").toLowerCase().includes(term)));
    rows.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number") return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    document.getElementById("ledCount").textContent =
      `${rows.length} of ${L.edges.length} edges. ` +
      `${L.counts.undisclosed_amount} edges in the ledger have no disclosed amount and ` +
      `contribute nothing to the dollar-weighted bounds.`;
    document.getElementById("ledgerTable").innerHTML =
      `<thead><tr>${cols.map(([k, label, num]) =>
        `<th class="${num ? "num" : ""}" data-k="${k}">${esc(label)}${sortKey === k
          ? (sortDir < 0 ? " ▼" : " ▲") : ""}</th>`).join("")}</tr></thead><tbody>` +
      rows.map(e => `<tr>
        <td class="mono">${esc(e.as_of)}</td><td>${esc(e.source)}</td><td>${esc(e.target)}</td>
        <td class="mono" style="font-size:0.76rem">${esc(e.edge_type)}</td>
        <td class="num">${e.amount_undisclosed ? '<span class="note">none</span>'
          : (e.low === e.high ? usd(e.high) : usd(e.low) + "&ndash;" + usd(e.high))}</td>
        <td class="note">${esc(e.basis)}</td>
        <td><span class="pill ${e.conditional ? "cond" : "def"}">${esc(e.status)}</span></td>
        <td><span class="tier ${e.tier}">${e.tier}</span></td>
        <td style="max-width:360px"><span style="font-style:italic">&ldquo;${esc(e.quote)}&rdquo;</span>
          <div class="note"><a href="${esc(e.url)}" target="_blank" rel="noopener">source</a>
          ${e.accession ? " &middot; " + esc(e.accession) : ""}
          ${e.conditions ? "<br>conditions: " + esc(e.conditions) : ""}
          ${e.notes ? "<br>" + esc(e.notes) : ""}</div></td></tr>`).join("") + "</tbody>";
    document.querySelectorAll("#ledgerTable th").forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = k === "high" ? -1 : 1; }
      draw();
    });
  }
  ["ledSearch", "ledTier", "ledStatus", "ledFamily"].forEach(id => {
    const el = document.getElementById(id);
    el.oninput = draw; el.onchange = draw;
  });
  draw();

  document.getElementById("backlogTable").innerHTML =
    `<thead><tr><th>Node</th><th>Metric</th><th>As of</th><th class="num">Amount</th>
      <th>Tier</th><th>Quote</th></tr></thead><tbody>` +
    L.backlog_rows.map(b => `<tr>
      <td>${esc(b.node)}</td><td class="mono">${esc(b.metric)}</td>
      <td class="mono">${esc(b.as_of_date)}</td>
      <td class="num">${b.amount_usd_low === b.amount_usd_high ? usd(b.amount_usd_high)
        : usd(b.amount_usd_low) + "&ndash;" + usd(b.amount_usd_high)}</td>
      <td><span class="tier ${esc(b.evidence_tier)}">${esc(b.evidence_tier)}</span></td>
      <td style="max-width:420px"><span style="font-style:italic">&ldquo;${esc(b.quote_snippet)}&rdquo;</span>
        <div class="note">${b.source_url ? `<a href="${esc(b.source_url)}" target="_blank" rel="noopener">source</a>` : ""}
        ${b.accession_no ? " &middot; " + esc(b.accession_no) : ""}
        ${b.notes ? "<br>" + esc(b.notes) : ""}</div></td></tr>`).join("") + "</tbody>";

  const v = L.validation || [];
  document.getElementById("validation").innerHTML = v.length
    ? `<p class="warn">${v.length} validation problems:</p><ul class="tight">${
        v.map(p => `<li class="mono">${esc(p)}</li>`).join("")}</ul>`
    : `<p><span class="tier T1">PASS</span> Every edge has a source URL and a quote
       under 25 words, every T1 edge has an accession number, no T4 rows exist, no
       self-edges, no duplicate ids, and no row has low above high.</p>`;
}

/* ================= METHOD ================= */
function renderMethod() {
  const w = S.metrics.warnings || [];
  const conv = S.metrics.convergence.central || {};
  document.getElementById("limitations").innerHTML = `<ul class="tight">
    <li><strong>The denominator is mostly blind.</strong>
      ${pct(S.metrics.coverage.unattributable_weighted)} of the disclosed backlog here
      names no customer. Oracle alone is ${usd(664e9)} of it.</li>
    <li><strong>Private labs file nothing.</strong> Their documented funding is a
      subset of their real funding, which pushes every CENTRAL provenance share up.
      The LOWER bound is the honest floor.</li>
    <li><strong>Several real instruments carry no dollar figure.</strong>
      ${S.ledger.counts.undisclosed_amount} ledger edges are recorded at zero
      dollars because no party disclosed an amount, including AMD's warrants and
      the Broadcom gigawatt agreements.</li>
    <li><strong>Multi-hop provenance is damped.</strong> alpha =
      ${esc(S.ledger.config.multihop.alpha)}, truncated at
      ${esc(S.ledger.config.multihop.max_hops)} hops, truncation residual
      ${(conv.truncation_residual_l1 || 0).toExponential(1)}. Funding traced through
      several intermediaries is discounted by assumption, not by evidence.</li>
    <li><strong>The stress result is assumption-dominated.</strong>
      ${esc(S.stress.assumption_note)}</li>
    ${w.length ? `<li><strong>Data-quality warnings in force.</strong><ul class="tight">${
      w.map(x => `<li>${esc(x)}</li>`).join("")}</ul></li>` : ""}
  </ul>`;
  document.getElementById("changeMyMind").innerHTML = `<ul class="tight">
    <li><strong>Oracle or Broadcom naming a customer and a dollar split.</strong>
      Together they hold ${usd(843.2e9)} of unattributed backlog. A single
      concentration disclosure would move the headline more than any parameter here.</li>
    <li><strong>An OpenAI or Anthropic S-1.</strong> A real funding table would
      replace the documented-subset denominator and could move CENTRAL in either
      direction. If their non-supplier funding is larger than what is documented
      here, CENTRAL falls.</li>
    <li><strong>The Nvidia and OpenAI letter of intent converting to a signed,
      sized investment.</strong> It is the largest single row in the ledger and it
      is non-binding. At definitive weight it dominates OpenAI's funding provenance.</li>
    <li><strong>A conditional tranche visibly failing.</strong> Most of the
      conditional dollars here are gated on compute delivery or a liquidity event.
      One public failure would give the conditional weight an empirical anchor
      instead of a configured guess.</li>
    <li><strong>Suppliers beginning to disclose backlog.</strong> If Nvidia or AMD
      published a product backlog figure, the two companies most associated with
      vendor financing would become measurable for the first time.</li>
  </ul>`;
  const p = S.ledger.config;
  const rows = [];
  Object.entries(S.ledger.status_weights).forEach(([k, v]) =>
    rows.push([`status weight, ${k}`, `low ${v.low}, central ${v.central}, high ${v.high}`]));
  rows.push(["multi-hop alpha", p.multihop.alpha]);
  rows.push(["multi-hop max hops", p.multihop.max_hops]);
  rows.push(["assumed term, years", p.amounts.assumed_term_years]);
  rows.push(["headline tier gate", p.tiers.headline_allowed.join(" and ")]);
  rows.push(["sensitivity tier gate", p.tiers.sensitivity_allowed.join(", ")]);
  rows.push(["never counted", p.tiers.never.join(", ")]);
  Object.entries(p.stress).forEach(([k, v]) =>
    rows.push([`stress, ${k.replace(/_/g, " ")}`, Array.isArray(v) ? v.join(" to ") : v]));
  document.getElementById("paramTable").innerHTML =
    "<thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>" +
    rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`).join("") +
    "</tbody>";
}

/* ================= TABS AND THEME ================= */
const PANELS = ["headline", "graph", "suppliers", "cycles", "stress", "news", "ledger", "method"];
const RENDERED = new Set();
function show(name) {
  PANELS.forEach(p => {
    document.getElementById("panel-" + p).classList.toggle("active", p === name);
    document.getElementById("tab-" + p).setAttribute("aria-selected", String(p === name));
  });
  if (!RENDERED.has(name)) {
    RENDERED.add(name);
    try {
      if (name === "graph") { renderGraphControls(); drawGraph(); }
      if (name === "suppliers") renderSuppliers();
      if (name === "cycles") renderCycles();
      if (name === "stress") renderStress();
      if (name === "news") renderNews();
      if (name === "ledger") renderLedger();
      if (name === "method") renderMethod();
    } catch (err) { console.error("panel " + name + " failed", err); }
  }
  if (location.hash.slice(1) !== name) history.replaceState(null, "", "#" + name);
}
PANELS.forEach(p => { document.getElementById("tab-" + p).onclick = () => show(p); });

(function theme() {
  const key = "rt-theme";
  const saved = (() => { try { return localStorage.getItem(key); } catch (e) { return null; } })();
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  document.getElementById("themebtn").onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : (cur === "light" ? "dark"
      : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark"));
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(key, next); } catch (e) { /* private mode */ }
    RENDERED.clear();
    const active = PANELS.find(p => document.getElementById("panel-" + p).classList.contains("active"));
    RENDERED.add("headline");
    renderHeadline();
    show(active || "headline");
  };
})();

let resizeTimer;
addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const active = PANELS.find(p => document.getElementById("panel-" + p).classList.contains("active"));
    RENDERED.delete(active);
    renderHeadline();
    show(active || "headline");
  }, 220);
});

/* ================= BOOT ================= */
Promise.all([
  fetch("data/ledger.json").then(r => r.json()),
  fetch("data/metrics.json").then(r => r.json()),
  fetch("data/stress.json").then(r => r.json()),
  fetch("data/news.json").then(r => r.json()).catch(() => ({ counts: {}, items: [], review_queue: [] })),
  fetch("data/history.json").then(r => r.json()).catch(() => ({ vintages: [] })),
]).then(([ledger, metrics, stress, news, history]) => {
  S.ledger = ledger; S.metrics = metrics; S.stress = stress; S.news = news; S.history = history;
  document.getElementById("subline").innerHTML =
    `${ledger.counts.edges} verified edges from SEC filings and company releases &middot; ` +
    `as of ${esc(metrics.as_of)} &middot; analysis, not investment advice`;
  document.getElementById("footNote").innerHTML =
    `Built from SEC EDGAR, company investor relations releases and GDELT. No paid ` +
    `data. Optional local model extraction is human-reviewed. Every figure resolves to ledger rows with a ` +
    `source link, a verbatim quote and an as-of date. Generated ${esc(metrics.generated)}. ` +
    `This is analysis, not investment advice.`;
  RENDERED.add("headline");
  renderHeadline();
  const hash = location.hash.slice(1);
  show(PANELS.includes(hash) ? hash : "headline");
}).catch(err => {
  document.getElementById("subline").textContent =
    "Could not load data. Run `make refresh` first, then `make serve`.";
  console.error(err);
});
})();
