/* Client-side port of src/stress.py::cascade, build_network and the two
 * cross-check methods. The graph is tiny, so the stress lab recomputes in the
 * browser instead of shipping a precomputed grid.
 *
 * This file is a PORT, not a reimplementation: tests/test_js_parity.py runs it
 * under node against the Python results for every scenario preset and fails on
 * any difference above 1e-9. If you change the Python model, change this and
 * re-run the parity test.
 */
(function (root) {
  "use strict";

  const FUNDING = new Set(["equity_investment", "convertible_or_debt",
    "loan_or_guarantee", "warrants", "vendor_financing"]);
  const DEMAND = new Set(["purchase_commitment", "cloud_capacity_contract",
    "lease", "offtake_or_rpo"]);
  const PREF = ["rpo", "contracted_backlog", "revenue_ttm"];

  function termYears(start, end, dflt) {
    if (start && end) {
      const a = Date.parse(start), b = Date.parse(end);
      if (!isNaN(a) && !isNaN(b)) {
        const y = (b - a) / (365.25 * 86400000);
        if (y > 0) return Math.max(1, y);
      }
    }
    return dflt;
  }

  /* Status-weighted total contract value, matching ledger.tcv + weighted_amount. */
  function weightedAmount(edge, bound, weights, assumedTerm) {
    const w = (weights[edge.status] || {})[bound];
    if (w === undefined) return 0;
    let mult = 1;
    if (edge.basis === "per-year") {
      mult = termYears(edge.term_start, edge.term_end, assumedTerm);
    }
    const lo = edge.low * mult, hi = edge.high * mult;
    const base = bound === "central" ? (lo + hi) / 2 : (bound === "high" ? hi : lo);
    return base * w;
  }

  /* Port of metrics.backlog_table restricted to what the cascade needs. */
  function backlogFor(node, backlogRows, bound) {
    const rows = backlogRows.filter(r => r.node === node && PREF.includes(r.metric));
    for (const metric of PREF) {
      const m = rows.filter(r => r.metric === metric)
        .sort((a, b) => String(a.as_of_date).localeCompare(String(b.as_of_date)));
      if (m.length) {
        const r = m[m.length - 1];
        const lo = +r.amount_usd_low, hi = +r.amount_usd_high;
        if (bound === "central") return (lo + hi) / 2;
        return bound === "low" ? hi : lo;   // bound-correct denominators
      }
    }
    return 0;
  }

  function buildNetwork(edges, backlogRows, opts) {
    const o = opts || {};
    const bound = o.bound || "central";
    const tiers = new Set(o.tiers || ["T1", "T2"]);
    const weights = JSON.parse(JSON.stringify(o.weights));
    if (o.loiWeight !== undefined && o.loiWeight !== null) {
      weights.LOI_nonbinding[bound] = o.loiWeight;
    }
    if (o.conditionalWeight !== undefined && o.conditionalWeight !== null) {
      weights.conditional[bound] = o.conditionalWeight;
    }
    const assumedTerm = o.assumedTerm === undefined ? 5 : o.assumedTerm;
    const e = edges.filter(x => tiers.has(x.tier) && x.tier !== "T4");

    const nodeSet = new Set();
    e.forEach(x => { nodeSet.add(x.source); nodeSet.add(x.target); });
    backlogRows.forEach(r => { if (PREF.includes(r.metric)) nodeSet.add(r.node); });
    const nodes = Array.from(nodeSet).sort();
    const ix = new Map(nodes.map((n, i) => [n, i]));
    const n = nodes.length;
    const zeros = () => Array.from({ length: n }, () => new Float64Array(n));
    const C = zeros();   // C[buyer][seller]
    const F = zeros();   // F[funder][recipient]
    const links = zeros();

    e.forEach(x => {
      const amt = weightedAmount(x, bound, weights, assumedTerm);
      const i = ix.get(x.source), j = ix.get(x.target);
      if (i === undefined || j === undefined) return;
      if (FUNDING.has(x.edge_type)) { F[i][j] += amt; links[i][j] = 1; }
      else if (DEMAND.has(x.edge_type)) { C[i][j] += amt; }
    });

    const backlog = new Float64Array(n);
    nodes.forEach((nd, i) => { backlog[i] = backlogFor(nd, backlogRows, bound); });
    const external = new Float64Array(n);
    for (let j = 0; j < n; j++) { let s = 0; for (let i = 0; i < n; i++) s += F[i][j]; external[j] = s; }

    const suppliers = nodes.filter((nd, i) => backlog[i] > 0);
    const buyers = nodes.filter((nd, i) => {
      let s = 0; for (let j = 0; j < n; j++) s += C[i][j]; return s > 0;
    });
    return { nodes, ix, C, F, links, backlog, external, suppliers, buyers, n };
  }

  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

  function cascade(net, shock, passthrough, capacityToInvest, tol, maxIter) {
    tol = tol === undefined ? 1e-9 : tol;
    maxIter = maxIter === undefined ? 200 : maxIter;
    const { nodes, ix, C, F, backlog, external, n } = net;

    const exo = new Float64Array(n);
    Object.keys(shock || {}).forEach(k => {
      if (ix.has(k)) exo[ix.get(k)] = clamp01(+shock[k]);
    });
    let fundingLoss = Float64Array.from(exo);
    let honour = new Float64Array(n).fill(1);
    let residual = Infinity, iterations = 0;

    for (iterations = 1; iterations <= maxIter; iterations++) {
      for (let j = 0; j < n; j++) honour[j] = clamp01(1 - passthrough * fundingLoss[j]);

      const lost = new Float64Array(n);
      for (let b = 0; b < n; b++) {
        const f = 1 - honour[b];
        if (f === 0) continue;
        for (let s = 0; s < n; s++) lost[s] += C[b][s] * f;
      }
      const lossRate = new Float64Array(n);
      for (let s = 0; s < n; s++) lossRate[s] = backlog[s] > 0 ? clamp01(lost[s] / backlog[s]) : 0;

      const cut = new Float64Array(n);
      for (let s = 0; s < n; s++) cut[s] = clamp01(capacityToInvest * lossRate[s]);

      const withdrawn = new Float64Array(n);
      for (let f = 0; f < n; f++) {
        if (cut[f] === 0) continue;
        for (let r = 0; r < n; r++) withdrawn[r] += F[f][r] * cut[f];
      }
      const induced = new Float64Array(n);
      for (let r = 0; r < n; r++) induced[r] = external[r] > 0 ? clamp01(withdrawn[r] / external[r]) : 0;

      const next = new Float64Array(n);
      let res = 0;
      for (let k = 0; k < n; k++) {
        next[k] = clamp01(exo[k] + induced[k]);
        res = Math.max(res, Math.abs(next[k] - fundingLoss[k]));
      }
      residual = res;
      fundingLoss = next;
      if (residual < tol) break;
    }

    for (let j = 0; j < n; j++) honour[j] = clamp01(1 - passthrough * fundingLoss[j]);
    const lost = new Float64Array(n);
    for (let b = 0; b < n; b++) {
      const f = 1 - honour[b];
      if (f === 0) continue;
      for (let s = 0; s < n; s++) lost[s] += C[b][s] * f;
    }
    const atRisk = {}, atRiskUsd = {}, lossMap = {}, honourMap = {};
    let totLost = 0, totBl = 0;
    nodes.forEach((nd, i) => {
      lossMap[nd] = fundingLoss[i];
      honourMap[nd] = honour[i];
      totBl += backlog[i];
      totLost += lost[i];
      if (backlog[i] > 0) {
        atRisk[nd] = clamp01(lost[i] / backlog[i]);
        atRiskUsd[nd] = lost[i];
      }
    });
    return {
      converged: residual < tol, iterations, residual,
      funding_loss: lossMap, honour: honourMap,
      backlog_at_risk_share: atRisk, backlog_at_risk_usd: atRiskUsd,
      ecosystem_at_risk_share: totBl > 0 ? totLost / totBl : 0,
      ecosystem_at_risk_usd: totLost,
    };
  }

  function eisenbergNoe(net, shock, passthrough, tol, maxIter) {
    tol = tol === undefined ? 1e-10 : tol;
    maxIter = maxIter === undefined ? 500 : maxIter;
    const { nodes, ix, C, backlog, external, n } = net;
    const oblig = new Float64Array(n);
    for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < n; j++) s += C[i][j]; oblig[i] = s; }
    const loss = new Float64Array(n);
    Object.keys(shock || {}).forEach(k => { if (ix.has(k)) loss[ix.get(k)] = clamp01(+shock[k]); });
    const resources = new Float64Array(n);
    for (let i = 0; i < n; i++) resources[i] = external[i] * (1 - passthrough * loss[i]);

    const Pi = Array.from({ length: n }, (_, i) => {
      const row = new Float64Array(n);
      if (oblig[i] > 0) for (let j = 0; j < n; j++) row[j] = C[i][j] / oblig[i];
      return row;
    });
    let p = Float64Array.from(oblig), delta = Infinity, it = 0;
    for (it = 1; it <= maxIter; it++) {
      const inflow = new Float64Array(n);
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) inflow[j] += Pi[i][j] * p[i];
      const next = new Float64Array(n);
      delta = 0;
      for (let i = 0; i < n; i++) {
        next[i] = Math.max(0, Math.min(oblig[i], resources[i] + inflow[i]));
        delta = Math.max(delta, Math.abs(next[i] - p[i]));
      }
      p = next;
      if (delta < tol) break;
    }
    const received = new Float64Array(n), promised = new Float64Array(n);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      received[j] += Pi[i][j] * p[i]; promised[j] += C[i][j];
    }
    const share = {}; let tot = 0, risk = 0;
    nodes.forEach((nd, i) => {
      tot += backlog[i];
      const cs = promised[i] > 0 ? 1 - received[i] / promised[i] : 0;
      const usd = cs * Math.min(promised[i], backlog[i]);
      risk += usd;
      if (backlog[i] > 0) share[nd] = clamp01(usd / backlog[i]);
    });
    return { iterations: it, residual: delta, converged: delta < tol,
      backlog_at_risk_share: share,
      ecosystem_at_risk_share: tot > 0 ? risk / tot : 0 };
  }

  function debtRank(net, shock) {
    const { nodes, ix, C, backlog, n } = net;
    const W = Array.from({ length: n }, (_, i) => {
      const row = new Float64Array(n);
      for (let j = 0; j < n; j++) row[j] = backlog[j] > 0 ? clamp01(C[i][j] / backlog[j]) : 0;
      return row;
    });
    let h = new Float64Array(n);
    Object.keys(shock || {}).forEach(k => { if (ix.has(k)) h[ix.get(k)] = clamp01(+shock[k]); });
    const state = new Int8Array(n);
    for (let i = 0; i < n; i++) state[i] = h[i] > 0 ? 1 : 0;
    let rounds = 0;
    while (state.some(s => s === 1) && rounds < 50) {
      rounds++;
      const active = [];
      for (let i = 0; i < n; i++) if (state[i] === 1) active.push(i);
      const next = Float64Array.from(h);
      active.forEach(i => {
        for (let j = 0; j < n; j++) next[j] = Math.min(1, next[j] + W[i][j] * h[i]);
      });
      const newly = [];
      for (let j = 0; j < n; j++) if (next[j] > h[j] + 1e-15 && state[j] === 0) newly.push(j);
      active.forEach(i => { state[i] = 2; });
      newly.forEach(j => { state[j] = 1; });
      h = next;
    }
    const share = {}; let tot = 0, risk = 0;
    nodes.forEach((nd, i) => {
      tot += backlog[i]; risk += h[i] * backlog[i];
      if (backlog[i] > 0) share[nd] = h[i];
    });
    return { rounds, backlog_at_risk_share: share,
      ecosystem_at_risk_share: tot > 0 ? risk / tot : 0 };
  }

  const api = { FUNDING, DEMAND, buildNetwork, cascade, eisenbergNoe, debtRank,
                weightedAmount, termYears };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Cascade = api;
})(typeof window !== "undefined" ? window : globalThis);
