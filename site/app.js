"use strict";
/* ---------- state ---------- */
let D = null, MODEL = {}, NOTES = {}, META = {}, TAX = {};
const REG = [["asia","Asia ex-Japan"],["japan","Japan"],["europe","Europe"],["americas","Americas"],["me","Middle East & other"]];
const REG_KEYS = REG.map(r => r[0]);
const MEASURES = [["group","Group growth","group growth"],["asia","Asia ex-Japan growth","Asia ex-Japan growth"],["japan","Japan growth","Japan growth"],["europe","Europe growth","Europe growth"],["americas","Americas growth","Americas growth"],["me","Middle East & other growth","Middle East & other growth"],["stack","Two-year growth","two-year growth"]];
const AGAINST = [["prev","Prior quarter"],["yoy","Same quarter last year"],["median","Median of the others"],["company","One company"],["none","Nothing"]];
const TITLES = {overview:"Overview", compare:"Compare", categories:"Categories", company:"Company", data:"Data and sources", method:"Method"};
const WORDS = ["zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve"];
const state = { view:"overview", group:"", quarter:"", company:"", sel:new Set(), measure:"group", against:"prev", againstCo:"", open:new Set(), dataCo:"all", dataType:"all", dataText:"" };
let redraws = [];

/* ---------- helpers ---------- */
const $ = (s, r) => (r || document).querySelector(s);
function el(tag, attrs, ...kids){
  const n = document.createElement(tag);
  if (attrs) for (const k in attrs){
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "style") n.style.cssText = v;   /* set through the style object, so the page needs no inline styles */
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids){ if (kid == null || kid === false) continue; n.append(kid.nodeType ? kid : document.createTextNode(String(kid))); }
  return n;
}
function sv(tag, attrs){ const n = document.createElementNS("http://www.w3.org/2000/svg", tag); if (attrs) for (const k in attrs){ if (k === "style") n.style.cssText = attrs[k]; else n.setAttribute(k, attrs[k]); } return n; }
const isNum = v => typeof v === "number" && isFinite(v);
function trim1(v){ const r = Math.round(v * 10) / 10; return Number.isInteger(r) ? String(r) : r.toFixed(1); }
function fmtPct(v){ if (!isNum(v)) return "n/d"; const r = Math.round(v * 10) / 10; if (r === 0) return "0%"; return (r > 0 ? "+" : "−") + trim1(Math.abs(r)) + "%"; }
function fmtPts(d){ if (!isNum(d)) return "n/d"; const r = Math.round(d * 10) / 10; if (r === 0) return "0 pts"; const a = trim1(Math.abs(r)); return (r > 0 ? "+" : "−") + a + (a === "1" ? " pt" : " pts"); }
function fmtRev(v, cur){ if (!isNum(v)) return ""; const pre = !cur || cur === "EUR" ? "€" : cur + " "; return pre + (v >= 1000 ? Math.round(v).toLocaleString("en-US") : trim1(v)) + "m"; }
function qLabel(q){ return "Q" + q.slice(5) + " " + q.slice(0, 4); }
function shiftQ(q, n){ const i = (+q.slice(0, 4)) * 4 + (+q.slice(5) - 1) + n; return Math.floor(i / 4) + "Q" + (i % 4 + 1); }
const prevQ = q => shiftQ(q, -1);
function median(a){ const v = a.filter(isNum).sort((x, y) => x - y); if (!v.length) return null; const m = v.length >> 1; return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2; }
const cos = () => D.companies;
const byId = id => cos().find(c => c.id === id) || cos()[0];
/* Peer groups come from config/categories.json. Every median and rank is taken inside one industry. */
const industries = () => TAX.industries && TAX.industries.length ? TAX.industries : [{id:"goods", label:"Peers"}];
const firstIndustry = () => industries()[0].id;
function industryOf(c){ return ((TAX.companies || {})[c.id] || {}).industry || firstIndustry(); }
function focusOf(c){ return ((TAX.companies || {})[c.id] || {}).focus || null; }
function groupLabel(id){ const g = industries().concat(TAX.focus || []).find(x => x.id === id); return g ? g.label : id; }
const grp = () => cos().filter(c => industryOf(c) === state.group);
const sameIndustry = c => cos().filter(o => industryOf(o) === industryOf(c));
const minGroup = () => TAX.min_group || 3;
/* Colour follows the company and never its rank: eight checked hues in fixed order inside each industry, then ink, then grey.
   A company outside the first industry is also drawn dashed, so a mixed selection never relies on colour alone. */
function colorOf(c){ const i = sameIndustry(c).indexOf(c); return i >= 0 && i < 9 ? "var(--c" + (i + 1) + ")" : "var(--c-more)"; }
const dashed = c => industryOf(c) !== firstIndustry();
function swatch(color, dash){ return dash ? "background:repeating-linear-gradient(90deg," + color + " 0 5px,transparent 5px 8px)" : "background:" + color; }
function gv(c, q){ const s = c.series && c.series[q]; return s && isNum(s.g) ? s.g : null; }
function rcell(c, q, k){ const r = c.regions && c.regions[q]; return r && r[k] && isNum(r[k].v) ? r[k] : null; }
function rv(c, q, k){ const x = rcell(c, q, k); return x ? x.v : null; }
function mm(c, q){ return ((MODEL[q] || {}).companies || {})[c.id] || null; }
function allQuarters(){ const s = new Set(); cos().forEach(c => Object.keys(c.series || {}).forEach(q => s.add(q))); return [...s].sort(); }
function srcOf(c, i){ return c.sources && isNum(i) && c.sources[i] ? c.sources[i] : null; }
function periodLabel(c, q){ const s = c.series && c.series[q]; return s && s.label ? s.label + " (" + qLabel(q) + ")" : qLabel(q); }
function basisWords(b){ return ({"Organic":"organic","Constant FX":"at constant exchange rates","Comparable":"comparable","Reported":"as reported"})[b] || String(b || "").toLowerCase(); }
function count(n, of){ return (n === of ? (n === 2 ? "Both" : "All " + (WORDS[n] || n)) : (n < WORDS.length ? WORDS[n][0].toUpperCase() + WORDS[n].slice(1) : n) + " of " + (WORDS[of] || of)); }
function niceDomain(vals){
  const v = vals.filter(isNum); let lo = Math.min(0, ...v), hi = Math.max(0, ...v);
  const span = hi - lo, step = span > 60 ? 20 : span > 28 ? 10 : 5;
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step; if (hi === lo) hi = lo + step;
  const ticks = []; for (let t = lo; t <= hi + 1e-9; t += step) ticks.push(t);
  return {lo, hi, step, ticks};
}
function val(c, q, m){ if (m === "group") return gv(c, q); if (m === "stack"){ const x = mm(c, q); return x && isNum(x.two_year_stack) ? x.two_year_stack : null; } return rv(c, q, m); }
function againstVal(c, q, m){
  const a = state.against;
  if (a === "prev") return val(c, prevQ(q), m);
  if (a === "yoy") return val(c, shiftQ(q, -4), m);
  if (a === "median") return median(sameIndustry(c).filter(o => o.id !== c.id).map(o => val(o, q, m)));
  if (a === "company"){ const x = byId(state.againstCo); return x.id === c.id ? null : val(x, q, m); }
  return null;
}
function againstLabel(q){ const a = state.against; return a === "prev" ? qLabel(prevQ(q)) : a === "yoy" ? qLabel(shiftQ(q, -4)) : a === "median" ? "the median of the others in the industry" : a === "company" ? byId(state.againstCo).name : ""; }
const measureLabel = () => MEASURES.find(m => m[0] === state.measure)[1];
function go(hash){ location.hash = hash; }

/* ---------- tooltip ---------- */
const tip = $("#tip");
function tipShow(x, y, build){
  tip.replaceChildren(); build(tip); tip.style.display = "block";
  const w = tip.offsetWidth, h = tip.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
  let left = x + 14, top = y + 14;
  if (left + w > vw - 8) left = Math.max(8, x - w - 14);
  if (top + h > vh - 8) top = Math.max(8, y - h - 14);
  tip.style.left = left + "px"; tip.style.top = top + "px";
}
function tipHide(){ tip.style.display = "none"; }
function tipRow(v, lab, color){ return el("div", {class:"tr"}, color ? el("span", {class:"k", style:"background:" + color}) : null, el("span", {class:"val", text: v}), el("span", {class:"lab", text: lab})); }
function bindTip(node, build){
  node.addEventListener("pointermove", e => tipShow(e.clientX, e.clientY, build));
  node.addEventListener("pointerleave", tipHide);
  node.addEventListener("focus", () => { const r = node.getBoundingClientRect(); tipShow(r.left + Math.min(r.width, 240) / 2, r.bottom - 6, build); });
  node.addEventListener("blur", tipHide);
}

/* ---------- exhibit frame ---------- */
let exNo = 0;
/* The default source line under an exhibit. It names the companies with press-sourced figures, so no exhibit overstates its sources. */
function sourceLine(){
  const press = cos().filter(c => Object.values(c.regions || {}).some(r => Object.values(r).some(x => (srcOf(c, x.s) || {}).kind === "press")) || Object.values(c.series || {}).some(x => (srcOf(c, x.s) || {}).kind === "press")).map(c => c.name);
  return "Source: company releases" + (press.length ? "; some figures for " + (press.length > 1 ? press.slice(0, -1).join(", ") + " and " : "") + press[press.length - 1] + " come from press reports" : "") + ". Linked figure by figure on the Data screen.";
}
function exhibit(title, body, opts){
  opts = opts || {}; exNo += 1;
  return el("figure", {class:"ex", style:"margin:0"}, el("div", {class:"mono", text:"Exhibit " + exNo}), el("h3", {text: title}),
    opts.sub ? el("p", {class:"sub", text: opts.sub}) : null, el("div", {class:"body"}, body),
    el("div", {class:"src", text: opts.src || sourceLine()}));
}

/* ---------- charts ---------- */
function rowsChart(rows, dom, draw, padr){
  const host = el("div", {class:"plot", style: padr ? "--padr:" + padr + "px" : null});
  if (!rows.length){ host.append(el("p", {class:"note", text:"No figures for this selection."})); return host; }
  const pos = v => (v - dom.lo) / (dom.hi - dom.lo) * 100;
  const grid = el("div", {class:"gridlines"});
  dom.ticks.forEach(t => grid.append(el("i", {class: t === 0 ? "zero" : "", style:"left:" + pos(t) + "%"})));
  host.append(grid);
  rows.forEach(r => {
    const track = el("div", {class:"track"}); draw(track, r, pos);
    const b = el("button", {class:"rowc", type:"button", "aria-label": r.aria, onclick: () => go("#company/" + r.c.id)}, el("span", {class:"nm", text: r.c.name}), track);
    bindTip(b, r.tip); host.append(b);
  });
  const ax = el("div", {class:"axisrow"}), thin = window.innerWidth < 520 && dom.ticks.length > 4;
  dom.ticks.forEach(t => { if (thin && t !== 0 && Math.round(t / dom.step) % 2) return; ax.append(el("span", {class:"num", style:"left:" + pos(t) + "%", text: (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t) + "%"})); });
  host.append(ax);
  return host;
}
function barsChart(list, q, m, opts){
  opts = opts || {};
  const rows = list.filter(c => val(c, q, m) != null).sort((a, b) => val(b, q, m) - val(a, q, m)).map(c => {
    const g = val(c, q, m), ref = opts.ref ? againstVal(c, q, m) : null, s = m === "group" ? srcOf(c, c.series[q].s) : null;
    return { c, g, ref, aria: c.name + " " + fmtPct(g) + " in " + qLabel(q),
      tip: t => { t.append(el("div", {class:"tt", text: c.name}), tipRow(fmtPct(g), qLabel(q) + (m === "group" ? ", " + basisWords(c.basis) : ""), opts.color ? colorOf(c) : null));
        if (isNum(ref)) t.append(tipRow(fmtPct(ref), againstLabel(q)), el("div", {class:"src", text:"Difference " + fmtPts(g - ref)}));
        if (s) t.append(el("div", {class:"src", text:"Source: " + s.pub + ", " + s.date})); } };
  });
  const dom = niceDomain(rows.flatMap(r => [r.g, r.ref]));
  return rowsChart(rows, dom, (track, r, pos) => {
    const z = pos(0), x = pos(r.g);
    if (r.g !== 0) track.append(el("div", {class:"bar " + (r.g > 0 ? "pos" : "neg"), style:"left:" + Math.min(z, x) + "%;width:" + Math.abs(x - z) + "%" + (opts.color ? ";background:" + colorOf(r.c) : "")}));
    if (isNum(r.ref)) track.append(el("span", {class:"tickm", style:"left:" + pos(r.ref) + "%"}));
    if (opts.ref) track.append(el("span", {class:"gap num", text: isNum(r.ref) ? fmtPts(r.g - r.ref) : fmtPct(r.g)}));
    else track.append(el("span", {class:"tipv num", style:"left:calc(" + Math.max(z, x) + "% + 6px)", text: fmtPct(r.g)}));
  }, opts.ref ? 84 : 56);
}
function dumbChart(list, q){
  const rows = list.filter(c => gv(c, q) != null).sort((a, b) => gv(b, q) - gv(a, q)).map(c => {
    const g = gv(c, q), cell = rcell(c, q, "asia"), a = cell ? cell.v : null;
    return { c, g, a, aria: c.name + ": group " + fmtPct(g) + ", Asia ex-Japan " + fmtPct(a),
      tip: t => { t.append(el("div", {class:"tt", text: c.name + ", " + qLabel(q)}), tipRow(fmtPct(g), "Group", "var(--d-blue)"));
        if (a != null) t.append(tipRow(fmtPct(a), cell.label || "Asia ex-Japan", "var(--d-orange)"), el("div", {class:"src", text:"Gap " + fmtPts(a - g) + (cell.note ? ". " + cell.note : "")}));
        else t.append(el("div", {class:"src", text:"Asia ex-Japan not disclosed"})); } };
  });
  const dom = niceDomain(rows.flatMap(r => [r.g, r.a]));
  return rowsChart(rows, dom, (track, r, pos) => {
    if (r.a != null){ const x1 = pos(r.g), x2 = pos(r.a);
      track.append(el("div", {class:"conn", style:"left:" + Math.min(x1, x2) + "%;width:" + Math.abs(x1 - x2) + "%"}), el("span", {class:"dot a", style:"left:" + x2 + "%"})); }
    track.append(el("span", {class:"dot g", style:"left:" + pos(r.g) + "%"}), el("span", {class:"gap num", text: r.a != null ? fmtPts(r.a - r.g) : "n/d"}));
  }, 84);
}
/* lines: [{name, color, vals:[...], ref:boolean}] aligned with qs */
function trendChart(lines, qs, endLabels){
  const host = el("div", {class:"trend"});
  const draw = () => {
    host.replaceChildren();
    if (qs.length < 2 || !lines.length){ host.append(el("p", {class:"note", text:"Not enough data to draw a trend for this selection."})); return; }
    const W = Math.max(300, host.clientWidth || 700), narrow = W < 560, H = narrow ? 240 : 300;
    const m = {l: 44, r: endLabels && !narrow ? 150 : 52, t: 14, b: 30};
    const dom = niceDomain(lines.flatMap(l => l.vals));
    const x = i => m.l + i * (W - m.l - m.r) / (qs.length - 1), y = v => m.t + (dom.hi - v) / (dom.hi - dom.lo) * (H - m.t - m.b);
    const svg = sv("svg", {viewBox:"0 0 " + W + " " + H, role:"img", "aria-label":"Line chart by quarter. The table below it holds the numbers."});
    dom.ticks.forEach(t => { svg.append(sv("line", {class: t === 0 ? "zl" : "gl", x1: m.l, x2: W - m.r, y1: y(t), y2: y(t)}));
      const tx = sv("text", {class:"tk", x: m.l - 8, y: y(t) + 4, "text-anchor":"end"}); tx.textContent = (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t) + "%"; svg.append(tx); });
    /* Each label needs about 52px. When there is less, label every second quarter, always including the latest. */
    const step = (W - m.l - m.r) / Math.max(1, qs.length - 1) < 52 ? 2 : 1;
    qs.forEach((q, i) => { if ((qs.length - 1 - i) % step) return; const tx = sv("text", {class:"tk", x: x(i), y: H - 8, "text-anchor":"middle"}); tx.textContent = narrow ? "Q" + q.slice(5) + " ’" + q.slice(2, 4) : qLabel(q); svg.append(tx); });
    lines.forEach(l => {
      let d = "", pen = false, n = 0, last = null;
      l.vals.forEach((v, i) => { if (!isNum(v)){ pen = false; return; } d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1); pen = true; n++; last = {i, v}; });
      if (n >= 2) svg.append(sv("path", {class: l.ref ? "ref" : "ln", d, style: l.ref ? "" : "stroke:" + l.color + (l.dash ? ";stroke-dasharray:6 4" : "")}));
      /* A dot marks the latest point, and any point with no neighbour, which the line alone would not show. */
      if (!l.ref) l.vals.forEach((v, i) => { if (isNum(v) && (i === last.i || (!isNum(l.vals[i - 1]) && !isNum(l.vals[i + 1])))) svg.append(sv("circle", {class:"pt", cx: x(i), cy: y(v), r: 4.5, style:"fill:" + l.color})); });
      if (last && endLabels && !l.ref){ const tx = sv("text", {class:"endl", x: x(last.i) + 10, y: y(last.v) + 4}); tx.textContent = (narrow ? "" : l.name + " ") + fmtPct(last.v); svg.append(tx); }
    });
    const xh = sv("line", {class:"xh", y1: m.t, y2: H - m.b, x1: 0, x2: 0, visibility:"hidden"}); svg.append(xh);
    const hit = sv("rect", {x: m.l - 10, y: m.t, width: W - m.l - m.r + 20, height: H - m.t - m.b, fill:"transparent"});
    const move = e => {
      const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (W / r.width);
      let i = Math.round((px - m.l) / ((W - m.l - m.r) / (qs.length - 1))); i = Math.max(0, Math.min(qs.length - 1, i));
      xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("visibility", "visible");
      tipShow(e.clientX, e.clientY, t => { t.append(el("div", {class:"tt", text: qLabel(qs[i])}));
        lines.filter(l => isNum(l.vals[i])).sort((a, b) => b.vals[i] - a.vals[i]).forEach(l => t.append(tipRow(fmtPct(l.vals[i]), l.name, l.ref ? "var(--ink-2)" : l.color))); });
    };
    hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); tipHide(); });
    svg.append(hit); host.append(svg);
  };
  redraws.push(draw); requestAnimationFrame(draw);
  return host;
}
function heatTable(list, q){
  const tb = el("table", {class:"heat num"}), notes = [];
  const mark = txt => { let i = notes.indexOf(txt); if (i < 0){ notes.push(txt); i = notes.length - 1; } return String.fromCharCode(97 + (i % 26)); };
  const cellNode = (v, note, build) => {
    if (!isNum(v)) return el("span", {class:"cell nd", text:"n/d"});
    const t = Math.min(1, Math.abs(v) / 20), p = v === 0 ? 0 : Math.round(12 + t * 88);
    const n = el("span", {class:"cell " + (v >= 0 ? "pos" : "neg") + (p >= 75 ? " hi" : ""), style:"--p:" + p + "%", tabindex:"0"}, fmtPct(v));
    if (note) n.append(el("sup", {text: mark(note)}));
    if (build) bindTip(n, build);
    return n;
  };
  tb.append(el("thead", null, el("tr", null, el("th", {scope:"col", text:"Company"}), el("th", {scope:"col", text:"Group"}), ...REG.map(r => el("th", {scope:"col", text: r[1]})))));
  const body = el("tbody"), rows = list.filter(c => gv(c, q) != null).sort((a, b) => gv(b, q) - gv(a, q));
  rows.forEach(c => {
    const first = el("td", null, el("span", {class:"cdot", style:"background:" + colorOf(c)}), c.name, el("span", {class:"tag", text: c.basis}));
    if (c.scope) first.append(el("sup", {text: " " + mark(c.name + ": " + c.scope)}));
    const tr = el("tr", {class:"click", onclick: () => go("#company/" + c.id)}, first, el("td", null, cellNode(gv(c, q), null, t => t.append(el("div", {class:"tt", text: c.name + ", group"}), tipRow(fmtPct(gv(c, q)), periodLabel(c, q))))));
    REG_KEYS.forEach(k => { const x = rcell(c, q, k);
      tr.append(el("td", null, x ? cellNode(x.v, x.note ? c.name + ": " + x.note : null, t => { const s = srcOf(c, x.s);
        t.append(el("div", {class:"tt", text: c.name}), tipRow(fmtPct(x.v), x.label || k)); if (x.note) t.append(el("div", {class:"src", text: x.note}));
        if (s) t.append(el("div", {class:"src", text:"Source: " + s.pub + ", " + s.date})); }) : cellNode(null))); });
    body.append(tr);
  });
  if (rows.length > 1){
    const plain = v => el("span", {class:"cell nd", style:"color:var(--ink);font-weight:500", text: fmtPct(v)});
    const tr = el("tr", {class:"med"}, el("td", {text:"Median of these"}), el("td", null, plain(median(rows.map(c => gv(c, q))))));
    REG_KEYS.forEach(k => tr.append(el("td", null, plain(median(rows.map(c => rv(c, q, k))))))); body.append(tr);
  }
  tb.append(body);
  const foot = el("ul", {class:"foot"});
  notes.forEach((n, i) => foot.append(el("li", null, el("sup", {text: String.fromCharCode(97 + (i % 26)) + " "}), n)));
  foot.append(el("li", {text:"n/d: not disclosed for the quarter."}));
  return el("div", null, el("div", {class:"tscroll"}, tb), foot);
}
function signalChips(m){ const f = document.createDocumentFragment(); if (!m) return f; f.append(el("span", {class:"st test", text: m.signal.label})); m.signal.flags.forEach(x => f.append(el("span", {class:"st", text: x}))); return f; }

/* ---------- overview ---------- */
function viewOverview(v){
  const q = state.quarter, list = grp(), blk = MODEL[q] || {}, peer = (blk.groups || {})[state.group] || blk.peer || {}, p = prevQ(q), main = state.group === firstIndustry();
  const ranked = list.filter(c => gv(c, q) != null).sort((a, b) => gv(b, q) - gv(a, q));
  let head = groupLabel(state.group) + " in " + qLabel(q) + ".";
  if (peer.compared >= 2) head = peer.slowed * 2 >= peer.compared ? count(peer.slowed, peer.compared) + " companies slowed in " + qLabel(q) + "." : count(peer.compared - peer.slowed, peer.compared) + " companies sped up in " + qLabel(q) + ".";
  /* The sentence on how the median moved is written once, by the pipeline. */
  const few = ranked.length < minGroup() ? "With " + (WORDS[ranked.length] || ranked.length) + " companies in this group there is no median: each company is shown on its own." : null;
  const bits = [main ? ((NOTES[q] || {}).peer || {}).lede : null, few, "Every figure links to its source."].filter(Boolean);
  v.append(el("div", {class:"hero"}, el("div", {class:"mono", text: qLabel(q) + " · " + groupLabel(state.group) + " · " + ranked.length + " companies · data as of " + D.asOf}), el("h2", {class:"headline", text: head}), el("p", {class:"lede", text: bits.join(" ")})));

  const delta = (a, b) => { if (!isNum(a) || !isNum(b)) return null; const d = a - b; return el("span", {class:"delta " + (d < 0 ? "down" : d > 0 ? "up" : "")}, (d < 0 ? "▼ " : d > 0 ? "▲ " : "") + fmtPts(d)); };
  const tile = (label, value, ...rest) => el("div", {class:"kpi"}, el("div", {class:"mono", text: label}), el("div", {class:"v num", text: value}), el("div", {class:"d"}, ...rest));
  const medianTile = (label, all, like, prev, both, n) => isNum(prev) && isNum(like)
    ? tile(label, fmtPct(like), delta(like, prev), " against " + qLabel(p) + (both < n ? ", " + both + " of " + n + " companies" : ""))
    : tile(label, fmtPct(all), "");
  const top = ranked[0], low = ranked[ranked.length - 1];
  v.append(el("div", {class:"kpis"},
    /* A tile that shows a change shows the level for the same companies, and says so when that is not all of them. */
    /* A group too small for a median shows its size and the spread between its companies instead. */
    isNum(peer.median) ? medianTile("Median growth", peer.median, peer.median_like, peer.median_prev, peer.compared, peer.n) : tile("Companies", String(ranked.length), "Too few for a median"),
    isNum(peer.median) ? medianTile("Median, Asia ex-Japan", peer.asia_median, peer.asia_median_like, peer.asia_median_prev, peer.asia_both, peer.asia_compared) : tile("Spread", isNum(peer.spread) ? fmtPts(peer.spread).replace(/^\+/, "") : "n/d", "Fastest less slowest"),
    tile("Fastest", top ? fmtPct(gv(top, q)) : "n/d", top ? top.name : ""),
    tile("Slowest", low ? fmtPct(gv(low, q)) : "n/d", low ? low.name : "")));

  const flat = ranked.filter(c => gv(c, q) <= 0).length;
  const t1 = top ? top.name + " grew fastest at " + fmtPct(gv(top, q)) + ". " + (flat === 0 ? "Every company grew." : flat === 1 ? "One company was at or below zero." : count(flat, ranked.length) + " companies were at or below zero.") : "Growth by company";
  const t2 = peer.asia_compared ? "Asia ex-Japan grew more slowly than the group at " + peer.asia_lagging + " of " + peer.asia_compared + " companies." : "Group growth against Asia ex-Japan";
  const dumb = el("div", null, el("div", {class:"legend"}, el("span", null, el("i", {style:"background:var(--d-blue)"}), "Group"), el("span", null, el("i", {style:"background:var(--d-orange)"}), "Asia ex-Japan"), el("span", null, "Right column: the gap in points")), dumbChart(list, q));
  const bars = exhibit(t1, barsChart(list, q, "group"), {sub:"Sales growth against the same quarter a year earlier, on each company's underlying basis."});
  /* The carmakers report units by region, not revenue, so a group with no Asia figure gets its trend instead. */
  const qs8 = allQuarters().slice(-8), trendLines = list.map(c => ({name: c.name, color: colorOf(c), dash: dashed(c), vals: qs8.map(x => gv(c, x))}));
  v.append(el("div", {class:"g2"}, bars, peer.asia_compared
    ? exhibit(t2, dumb, {sub:"Where the orange dot sits left of the blue one, the region is holding the company back."})
    : exhibit("Growth by quarter, " + qLabel(qs8[0]) + " to " + qLabel(qs8[qs8.length - 1]) + ".", el("div", null, el("div", {class:"legend"}, ...trendLines.map(l => el("span", null, el("i", {class:"ln", style: swatch(l.color, l.dash)}), l.name))), trendChart(trendLines, qs8, true)), {sub:"These companies report no revenue by region."})));

  const ms = ranked.map(c => mm(c, q)).filter(Boolean);
  const nSlow = ms.filter(m => m.signal.momentum === "Slowing").length, nDrag = ms.filter(m => m.signal.flags.includes("Asia drag")).length, nTough = ms.filter(m => m.signal.flags.includes("Tougher base next quarter")).length;
  const tb = el("table", {class:"num"}, el("thead", null, el("tr", null, el("th", {text:"Company"}), el("th", {text:"Growth"}), el("th", {text:"Change"}), el("th", {class:"l", text:"What the model flags"}))));
  const body = el("tbody");
  ranked.forEach(c => { const m = mm(c, q); body.append(el("tr", {class:"click", onclick: () => go("#company/" + c.id)}, el("td", null, c.name), el("td", {text: fmtPct(gv(c, q))}), el("td", {text: m ? fmtPts(m.delta) : "n/d"}), el("td", {class:"l"}, signalChips(m)))); });
  tb.append(body);
  const faces = n => n === 1 ? " faces" : " face";
  v.append(exhibit(nSlow + " of " + ms.length + " companies are slowing. " + (peer.asia_compared ? nDrag + (nDrag === 1 ? " shows" : " show") + " an Asia drag and " + nTough + faces(nTough) : nTough + faces(nTough)) + " a tougher base next quarter.", el("div", {class:"tscroll"}, tb),
    {sub:"Labels come from fixed rules applied to the figures. Select a company for its file.", src:"Source: model step of the pipeline. Rules and thresholds are on the Method screen."}));

  v.append(el("div", null, el("div", {class:"mono", style:"margin-bottom:8px", text:"How the data gets here"}), el("div", {class:"steps"},
    ...[["1 · LLM with web search","Research","Finds each company's newest release."],["2 · LLM","Extract","Returns each figure with the sentence that states it."],["3 · Rules","Verify","Checks every quote and number against the release."],["4 · Arithmetic","Model","Computes changes, medians, base effects and signals."],["5 · LLM","Interpret","Writes the note. Numbers not in the data are rejected."]]
      .map(s => el("div", null, el("span", {class:"mono", text: s[0]}), el("b", {text: s[1]}), el("span", {text: s[2]})))),
    el("p", {class:"note", style:"margin-top:8px"}, el("a", {href:"#compare", text:"Compare companies"}), " · ", el("a", {href:"#data", text:"See every figure and its source"}), " · ", el("a", {href:"#method", text:"Read the method"}))));
}

/* ---------- compare ---------- */
function viewCompare(v){
  const q = state.quarter, list = cos().filter(c => state.sel.has(c.id)), m = state.measure, ml = measureLabel(), hasRef = state.against !== "none";
  const chips = el("div", {class:"chips"});
  cos().forEach(c => chips.append(el("button", {class:"chip", type:"button", "aria-pressed": String(state.sel.has(c.id)), onclick: () => { state.sel.has(c.id) ? state.sel.delete(c.id) : state.sel.add(c.id); render(); }}, el("i", {style:"background:" + colorOf(c)}), c.name)));
  /* Quick picks: a whole industry, or one focus inside it. */
  const pick = (label, ids) => el("button", {class:"linkbtn", type:"button", onclick: () => { state.sel = new Set(ids); render(); }}, label);
  const picks = [...industries().map(i => pick(i.label, cos().filter(c => industryOf(c) === i.id).map(c => c.id))),
    ...(TAX.focus || []).filter(f => cos().filter(c => focusOf(c) === f.id).length > 1 && cos().filter(c => focusOf(c) === f.id).length < cos().filter(c => industryOf(c) === f.industry).length)
      .map(f => pick(f.label, cos().filter(c => focusOf(c) === f.id).map(c => c.id)))];
  const mSel = el("select", {id:"c-measure", onchange: e => { state.measure = e.target.value; render(); }}, ...MEASURES.map(x => el("option", {value: x[0], text: x[1]}))); mSel.value = m;
  const aSel = el("select", {id:"c-against", onchange: e => { state.against = e.target.value; render(); }}, ...AGAINST.map(x => el("option", {value: x[0], text: x[1]}))); aSel.value = state.against;
  const coSel = el("select", {id:"c-against-co", "aria-label":"Company to compare against", onchange: e => { state.againstCo = e.target.value; render(); }}, ...cos().map(c => el("option", {value: c.id, text: c.name}))); coSel.value = state.againstCo;
  v.append(el("div", {class:"controls"},
    el("div", {class:"ctl"}, el("div", {class:"mono"}, "Companies", el("button", {class:"linkbtn", type:"button", onclick: () => { state.sel = new Set(cos().map(c => c.id)); render(); }}, "All"), ...picks, el("button", {class:"linkbtn", type:"button", onclick: () => { state.sel = new Set(); render(); }}, "Clear")), chips),
    el("div", {class:"ctl"}, el("label", {class:"mono", for:"c-measure", text:"Measure"}), mSel),
    el("div", {class:"ctl"}, el("label", {class:"mono", for:"c-against", text:"Compare against"}), el("div", {class:"row"}, aSel, state.against === "company" ? coSel : null))));
  if (!list.length){ v.append(el("p", {class:"note", text:"Select at least one company."})); return; }

  const rows = list.map(c => ({c, g: val(c, q, m), ref: hasRef ? againstVal(c, q, m) : null})).filter(r => r.g != null);
  const cmp = rows.filter(r => isNum(r.ref)), below = cmp.filter(r => r.g < r.ref).length;
  const t1 = hasRef && cmp.length ? below + " of " + cmp.length + " selected " + (cmp.length === 1 ? "company is" : "companies are") + " below " + againstLabel(q) + " on " + MEASURES.find(x => x[0] === m)[2] + "." : ml + " in " + qLabel(q) + ".";
  const leg = el("div", {class:"legend"}, el("span", null, "Bar: " + qLabel(q)), hasRef ? el("span", null, el("i", {class:"tick"}), againstLabel(q)[0].toUpperCase() + againstLabel(q).slice(1)) : null, hasRef ? el("span", null, "Right column: the difference in points") : null);
  const qs = allQuarters().slice(-8);
  const lines = list.map(c => ({name: c.name, color: colorOf(c), dash: dashed(c), vals: qs.map(x => val(c, x, m))})).filter(l => l.vals.some(isNum));
  /* One median line per industry in the selection, and only for an industry with enough companies. */
  if (state.against === "median") industries().filter(i => list.some(c => industryOf(c) === i.id)).forEach(i => { const mem = cos().filter(c => industryOf(c) === i.id);
    if (mem.length >= minGroup()) lines.push({name:"Median, " + i.label.toLowerCase(), ref: true, vals: qs.map(x => median(mem.map(c => val(c, x, m))))}); });
  if (state.against === "company" && !state.sel.has(state.againstCo)) lines.push({name: byId(state.againstCo).name, ref: true, vals: qs.map(x => val(byId(state.againstCo), x, m))});
  const tleg = el("div", {class:"legend"}, ...lines.map(l => el("span", null, el("i", {class:"ln", style: l.ref ? "background:var(--ink-2)" : swatch(l.color, l.dash)}), l.name)));
  const span = lines.length ? qs.filter((x, i) => lines.some(l => isNum(l.vals[i]))) : [];
  v.append(el("div", {class:"g2"},
    exhibit(t1, el("div", null, leg, barsChart(list, q, m, {ref: hasRef, color: true})), {sub: m === "group" ? "Each company on its own underlying basis." : m === "stack" ? "This quarter's growth compounded with the same quarter a year earlier." : "Regions as mapped into the five buckets. See the notes under Exhibit 4."}),
    exhibit(ml + (span.length > 1 ? ", " + qLabel(span[0]) + " to " + qLabel(span[span.length - 1]) + "." : " by quarter."), el("div", null, tleg, trendChart(lines, qs, lines.filter(l => !l.ref).length <= 4)), {sub: REG_KEYS.includes(m) ? "Regional figures are held for the two latest quarters." : "Move across the chart to read every line at a quarter."})));

  const tb = el("table", {class:"num"}, el("thead", null, el("tr", null, el("th", {text:"Company"}), el("th", {text: ml + ", " + qLabel(q)}), hasRef ? el("th", {text: againstLabel(q)[0].toUpperCase() + againstLabel(q).slice(1)}) : null, hasRef ? el("th", {text:"Difference"}) : null, el("th", {class:"l", text:"Signal"}), el("th", {class:"l", text:""}))));
  const body = el("tbody"), mixed = new Set(list.map(industryOf)).size > 1;   /* the industry tag only when the selection spans two */
  rows.sort((a, b) => b.g - a.g).forEach(r => {
    const c = r.c, x = mm(c, q), open = state.open.has(c.id);
    body.append(el("tr", {class:"click" + (open ? " open" : ""), onclick: () => { open ? state.open.delete(c.id) : state.open.add(c.id); render(); }},
      el("td", null, el("span", {class:"cdot", style:"background:" + colorOf(c)}), c.name, mixed ? el("span", {class:"tag", text: groupLabel(industryOf(c))}) : null), el("td", {text: fmtPct(r.g)}), hasRef ? el("td", {text: fmtPct(r.ref)}) : null, hasRef ? el("td", {text: isNum(r.ref) ? fmtPts(r.g - r.ref) : "n/d"}) : null,
      el("td", {class:"l"}, x ? el("span", {class:"st test", text: x.signal.label}) : "n/d"), el("td", {class:"l note", text: open ? "Hide" : "Details"})));
    if (open && x){
      const item = (k, t) => el("div", null, el("dt", {text: k}), el("dd", {text: t}));
      body.append(el("tr", {class:"detail"}, el("td", {colspan: hasRef ? "6" : "4"}, el("dl", {class:"dl"},
        item("Change against " + qLabel(prevQ(q)), fmtPts(x.delta)), item("Against the median of the others in the industry", fmtPts(x.vs_median)), item("Two-year growth", fmtPct(x.two_year_stack)),
        item("Base this quarter, next quarter", isNum(x.base) ? fmtPct(x.base) + ", " + fmtPct(x.next_base) : "n/d"), item("Asia gap to group", fmtPts(x.asia_gap)), item("Regions growing", x.breadth.reported ? x.breadth.growing + " of " + x.breadth.reported : "n/d"),
        item("Largest regional move", x.driver ? x.driver.name + " " + fmtPts(x.driver.change) : "n/d"), item("Flags", x.signal.flags.join(", ") || "None")),
        el("p", {class:"note", style:"margin-top:10px"}, el("a", {href:"#company/" + c.id, text:"Open the " + c.name + " file"})))));
    }
  });
  tb.append(body);
  v.append(exhibit("The numbers behind the charts, with the model's read of each company.", el("div", {class:"tscroll"}, tb), {sub:"Select a row for the full set of measures.", src:"Source: company releases and the model step of the pipeline."}));

  const meds = REG.map(r => [r[1], median(list.map(c => rv(c, q, r[0])))]).filter(x => isNum(x[1])).sort((a, b) => a[1] - b[1]);
  v.append(exhibit(meds.length ? meds[0][0] + " was the weakest region for this selection, with a median of " + fmtPct(meds[0][1]) + "." : "Growth by region", heatTable(list, q), {sub:"Blue is growth, red is decline. Hover a cell for the company's own label and the source."}));
}

/* ---------- categories ---------- */
function viewCategories(v){
  const q = state.quarter, p = prevQ(q), blk = MODEL[q] || {}, groups = blk.groups || {}, cats = blk.categories || {};
  const order = industries().flatMap(i => [i.id, ...(TAX.focus || []).filter(f => f.industry === i.id).map(f => f.id)]).filter(id => groups[id] && groups[id].n);
  const tb = el("table", {class:"num"}, el("thead", null, el("tr", null, el("th", {class:"l", text:"Group"}), el("th", {class:"l", text:"Companies"}), el("th", {text:"Median, " + qLabel(q)}), el("th", {text:"Median, " + qLabel(p)}), el("th", {text:"Change"}))));
  const body = el("tbody");
  order.forEach(id => { const g = groups[id], ind = g.kind === "industry";
    const who = g.members.map(cid => byId(cid)).sort((a, b) => gv(b, q) - gv(a, q)).map(c => c.name + " " + fmtPct(gv(c, q))).join(", ");
    const hasMed = isNum(g.median), like = isNum(g.median_like) && isNum(g.median_prev);
    body.append(el("tr", null, el("td", {class:"l", style: ind ? "font-weight:600" : "padding-left:22px"}, g.label, el("span", {class:"tag", text: ind ? "Industry" : "Focus"})),
      el("td", {class:"l", style:"color:var(--ink-2);font-size:13px", text: g.members.length < minGroup() ? who : g.n + " companies"}),
      el("td", {text: hasMed ? fmtPct(like ? g.median_like : g.median) : "n/d"}), el("td", {text: like ? fmtPct(g.median_prev) : "n/d"}), el("td", {text: like ? fmtPts(g.median_like - g.median_prev) : "n/d"}))); });
  tb.append(body);
  const withMed = order.map(id => groups[id]).filter(g => isNum(g.median_like) && isNum(g.median_prev)).sort((a, b) => (b.median_like - b.median_prev) - (a.median_like - a.median_prev));
  v.append(exhibit(withMed.length ? withMed.map(g => g.label + " moved " + fmtPts(g.median_like - g.median_prev)).join(". ") + "." : "Peer groups in " + qLabel(q) + ".", el("div", {class:"tscroll"}, tb),
    {sub:"Medians use the companies that report both quarters. A group of fewer than " + (WORDS[minGroup()] || minGroup()) + " lists its members instead of a median.", src:"Source: company releases and the model step of the pipeline."}));

  const ids = (TAX.categories || []).map(c => c.id).filter(id => cats[id]);
  if (!ids.length){ v.append(exhibit("Product categories", el("p", {class:"note", text:"No segment figures for this quarter."}))); return; }
  const all = ids.flatMap(id => cats[id].rows.map(r => r.g)), dom = niceDomain(all), pos = t => (t - dom.lo) / (dom.hi - dom.lo) * 100;
  const wrap = el("div", {class:"cat"});
  ids.forEach(id => { const k = cats[id], ml = el("div", {class:"mlist"});
    wrap.append(el("h4", null, k.label, el("span", {class:"note", text: k.n + (k.n === 1 ? " line" : " lines") + " from " + k.companies + (k.companies === 1 ? " company" : " companies") + (isNum(k.median) ? ", median " + fmtPct(k.median) : "")})));
    k.rows.forEach(r => { const c = byId(r.company), mt = el("div", {class:"mt"}, el("i", {style:"left:" + pos(0) + "%"}));
      if (r.g !== 0) mt.append(el("b", {class: r.g > 0 ? "pos" : "neg", style:"left:" + Math.min(pos(0), pos(r.g)) + "%;width:" + Math.abs(pos(r.g) - pos(0)) + "%"}));
      if (isNum(k.median)) mt.append(el("span", {class:"medm", style:"left:" + pos(k.median) + "%"}));
      const row = el("div", {class:"mrow", tabindex:"0"}, el("span", null, c.name + " · " + r.segment), mt, el("span", {class:"g num", text: fmtPct(r.g)}), el("span", {class:"r", text: c.basis}));
      bindTip(row, t => { t.append(el("div", {class:"tt", text: c.name + ", " + r.segment}), tipRow(fmtPct(r.g), qLabel(q) + ", " + basisWords(c.basis))); if (isNum(k.median)) t.append(el("div", {class:"src", text:"Category median " + fmtPct(k.median) + ", gap " + fmtPts(r.g - k.median)})); });
      ml.append(row); });
    wrap.append(ml); });
  const ranked = ids.filter(id => isNum(cats[id].median)).sort((a, b) => cats[b].median - cats[a].median);
  v.append(exhibit(ranked.length >= 2 ? cats[ranked[0]].label + " led the categories with a median of " + fmtPct(cats[ranked[0]].median) + ". " + cats[ranked[ranked.length - 1]].label + " trailed at " + fmtPct(cats[ranked[ranked.length - 1]].median) + "." : "Growth by product category, " + qLabel(q) + ".", wrap,
    {sub:"Each line on its company's own basis. The black mark is the category median, shown when " + (WORDS[minGroup()] || minGroup()) + " or more lines stand behind it. A line inside another line, such as Gucci inside Kering's fashion line, is left out."}));
}

/* ---------- company ---------- */
function viewCompany(v){
  const c = byId(state.company), q = state.quarter, x = mm(c, q), nt = ((NOTES[q] || {}).companies || {})[c.id], s0 = c.series && c.series[q];
  const chips = el("div", {class:"chips"});
  cos().forEach(o => chips.append(el("button", {class:"chip", type:"button", "aria-pressed": String(o.id === c.id), onclick: () => go("#company/" + o.id)}, el("i", {style:"background:" + colorOf(o)}), o.name)));
  v.append(chips);
  const head = el("div", null, el("div", {class:"cohead"}, el("span", {class:"name", text: c.name}), el("span", {class:"mono", text: [c.ticker, c.hq, groupLabel(industryOf(c)), focusOf(c) ? groupLabel(focusOf(c)) : null, c.basis + " growth", periodLabel(c, q)].filter(Boolean).join(" · ")})));
  if (c.fiscal) head.append(el("p", {class:"note", text: c.fiscal}));
  if (c.scope) head.append(el("p", {class:"note", text: c.scope}));
  const mini = (k, t) => el("div", null, el("span", {class:"mono", text: k}), el("b", {class:"num", text: t}));
  head.append(el("div", {class:"mini"}, mini("Growth", fmtPct(gv(c, q))), mini("Change", x ? fmtPts(x.delta) : "n/d"), mini("Against peers", x ? fmtPts(x.vs_median) : "n/d"), mini("Two years", x ? fmtPct(x.two_year_stack) : "n/d")));
  v.append(head);

  const note = el("div", {class:"prose"}, el("p", {text: nt ? nt.note : "No note for this quarter."}));
  if (nt && nt.watch) note.append(el("p", null, el("b", {style:"font-weight:600", text:"To check next: "}), nt.watch));
  note.append(el("div", {style:"margin:8px 0"}, signalChips(x)));
  const qs = allQuarters().slice(-8);
  /* Against the median of its own industry, or against each other member when the industry is too small for a median. */
  const mates = sameIndustry(c), big = mates.length >= minGroup(), indName = groupLabel(industryOf(c)).toLowerCase();
  const lines = [{name: c.name, color: colorOf(c), dash: dashed(c), vals: qs.map(t => gv(c, t))}].concat(big
    ? [{name:"Median, " + indName, ref: true, vals: qs.map(t => median(mates.map(o => gv(o, t))))}]
    : mates.filter(o => o.id !== c.id).map(o => ({name: o.name, ref: true, vals: qs.map(t => gv(o, t))})));
  const left = el("div", {style:"display:grid;gap:24px;align-content:start"},
    exhibit(x ? x.signal.label + "." : "What moved", note, {src: nt ? (nt.by === "rules" ? "Note written by fixed rules from the model output." : "Note written by " + nt.by + " from the model output. Every number in it was checked against the data.") : ""}),
    exhibit(c.name + (big ? " against the median of " + indName + ", by quarter." : " against " + lines.slice(1).map(l => l.name).join(" and ") + ", by quarter."), el("div", null, el("div", {class:"legend"}, ...lines.map(l => el("span", null, el("i", {class:"ln", style: l.ref ? "background:var(--ink-2)" : swatch(l.color, l.dash)}), l.name))), trendChart(lines, qs, true))));
  const segs = (c.segments && c.segments[q]) || [];
  if (segs.length){
    const dom = niceDomain(segs.map(s => s.g)), pos = t => (t - dom.lo) / (dom.hi - dom.lo) * 100, ml = el("div", {class:"mlist"});
    segs.forEach(s => { const mt = el("div", {class:"mt"}, el("i", {style:"left:" + pos(0) + "%"}));
      if (isNum(s.g) && s.g !== 0) mt.append(el("b", {class: s.g > 0 ? "pos" : "neg", style:"left:" + Math.min(pos(0), pos(s.g)) + "%;width:" + Math.abs(pos(s.g) - pos(0)) + "%"}));
      ml.append(el("div", {class:"mrow"}, el("span", {text: s.name}), mt, el("span", {class:"g num", text: fmtPct(s.g)}), el("span", {class:"r num", text: fmtRev(s.rev, c.cur)}))); });
    const catOf = s => { const m = (TAX.segments || {})[c.id] || {}; return s.name in m ? m[s.name] : "other"; };
    const best = segs.filter(s => isNum(s.g) && !/^of which/i.test(s.name) && catOf(s) !== null && catOf(s) !== "other").sort((a, b) => b.g - a.g);
    left.append(exhibit(best.length >= 2 ? best[0].name + " led at " + fmtPct(best[0].g) + ". " + best[best.length - 1].name + " was weakest at " + fmtPct(best[best.length - 1].g) + "." : "Segments", ml, {sub:"Growth and revenue by segment, " + qLabel(q) + "."}));
  }
  const right = el("div", {style:"display:grid;gap:24px;align-content:start"});
  const regs = REG.map(r => ({k: r[0], name: r[1], x: rcell(c, q, r[0])})).filter(r => r.x);
  if (regs.length){
    const tb = el("table", {class:"num"}, el("thead", null, el("tr", null, el("th", {text:"Region as reported"}), el("th", {class:"l", text:"Bucket"}), el("th", {text: qLabel(q)}), el("th", {text: qLabel(prevQ(q))}))));
    const body = el("tbody"); regs.forEach(r => body.append(el("tr", null, el("td", {text: r.x.label || r.name}), el("td", {class:"l", style:"color:var(--ink-2)", text: r.name}), el("td", {text: fmtPct(r.x.v)}), el("td", {text: fmtPct(rv(c, prevQ(q), r.k))}))));
    tb.append(body);
    right.append(exhibit(x && x.driver ? x.driver.name + " moved most against the prior quarter, by " + fmtPts(x.driver.change) + "." : "Growth by region", el("div", {class:"tscroll"}, tb)));
  }
  const item = (k, t) => el("div", null, el("dt", {text: k}), el("dd", {text: t}));
  if (x) right.append(exhibit(x.signal.flags.some(f => /base/.test(f)) ? x.signal.flags.find(f => /base/.test(f)) + "." : "The comparison base is steady into next quarter.", el("dl", {class:"dl"},
    item("Revenue, " + qLabel(q), s0 && isNum(s0.rev) ? fmtRev(s0.rev, c.cur) : "n/d"), item("Growth lapped this quarter", fmtPct(x.base)), item("Growth to lap next quarter", fmtPct(x.next_base)), item("Asia gap to group", fmtPts(x.asia_gap)), item("Regions growing", x.breadth.reported ? x.breadth.growing + " of " + x.breadth.reported : "n/d"), item("Rank on growth in " + indName, x.rank + " of " + (x.rank_of || ((MODEL[q] || {}).peer || {}).n))),
    {src:"Source: model step of the pipeline."}));
  const words = el("div", {class:"prose"});
  if (c.china) words.append(el("p", null, el("b", {style:"font-weight:600", text:"China and Asia. "}), c.china));
  if (c.guidance && c.guidance.text){ const g = c.guidance; words.append(el("p", null, el("b", {style:"font-weight:600", text:"Guidance. "}), g.text + (g.date ? " Stated " + g.date + "." : "")));
    if (g.evidence) words.append(el("p", null, el("b", {style:"font-weight:600", text:"Against the figures. "}), g.evidence.replace("{median}", fmtPct(median(mates.filter(o => o.id !== c.id).map(o => gv(o, D.latest))))) + " " + (g.read || ""))); }
  if (words.children.length) right.append(exhibit("What management said.", words, {src:"Source: company releases listed below."}));
  if (c.sources && c.sources.length){ const ol = el("ol", {class:"srcs"});
    c.sources.forEach(s => ol.append(el("li", null, s.url ? el("a", {href: s.url, target:"_blank", rel:"noopener noreferrer", text: s.t}) : s.t, ". " + [s.pub, s.date].filter(Boolean).join(", ") + ". ", el("span", {class:"st " + (s.kind === "press" ? "part" : "ok"), text: s.kind === "press" ? "Press" : "Company"}))));
    right.append(el("div", {class:"ex"}, el("div", {class:"mono", text:"Sources"}), el("div", {class:"body"}, ol))); }
  v.append(el("div", {class:"g2"}, left, right));
}

/* ---------- data ---------- */
function figures(q){
  const out = [];
  cos().forEach(c => { const s = c.series && c.series[q]; if (!s || !isNum(s.g)) return;
    out.push({c, q, type:"Group", item:"Group", g: s.g, rev: s.rev, src: srcOf(c, s.s), quote: s.q, note: c.scope || ""});
    const r = (c.regions && c.regions[q]) || {};
    REG.forEach(([k, name]) => { if (r[k] && isNum(r[k].v)) out.push({c, q, type:"Region", item: r[k].label || name, bucket: name, g: r[k].v, src: srcOf(c, r[k].s), quote: r[k].q, note: r[k].note || ""}); });
    ((c.segments && c.segments[q]) || []).forEach(x => out.push({c, q, type:"Segment", item: x.name, g: x.g, rev: x.rev, src: srcOf(c, s.s), quote: x.q, note:""})); });
  return out;
}
function csv(){
  const rows = [["company","ticker","calendar_quarter","period_label","type","item","bucket","growth_pct","revenue_m","currency","basis","note","source","source_kind","source_url"]];
  const esc = t => { const s = t == null ? "" : String(t); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  allQuarters().forEach(q => figures(q).forEach(f => { const s = f.src || {};
    rows.push([f.c.name, f.c.ticker, q, (f.c.series[q].label || qLabel(q)), f.type, f.item, f.bucket || "", isNum(f.g) ? f.g : "", isNum(f.rev) ? f.rev : "", isNum(f.rev) ? (f.c.cur || "EUR") : "", f.c.basis, f.note, s.t, s.kind || "", s.url]); }));
  return rows.map(r => r.map(esc).join(",")).join("\n");
}
function openDrawer(f){
  const d = $("#drawer"), s = f.src; d.replaceChildren(); d.hidden = false;
  const item = (k, t) => t ? el("div", null, el("dt", {text: k}), el("dd", {text: t})) : null;
  d.append(el("button", {class:"btn x", type:"button", onclick: closeDrawer}, "Close"), el("div", {class:"mono", text: f.c.name + " · " + f.type}), el("h2", {style:"font-size:1.15rem;font-weight:600;margin-top:4px", text: f.item}),
    el("div", {class:"big num", text: fmtPct(f.g)}),
    el("dl", {class:"dl", style:"grid-template-columns:1fr 1fr"}, item("Period", periodLabel(f.c, f.q)), item("Basis", f.c.basis), item("Bucket", f.bucket), item("Revenue", fmtRev(f.rev, f.c.cur))));
  if (f.note) d.append(el("h3", {text:"Note"}), el("p", {class:"note", text: f.note}));
  d.append(el("h3", {text:"Evidence"}), f.quote ? el("blockquote", {text: f.quote}) : el("p", {class:"note", text:"Entered by hand from the source below and checked against it on " + D.asOf + ". Figures added by the pipeline carry the exact sentence from the release here."}));
  d.append(el("h3", {text:"Source"}));
  if (s) d.append(el("p", null, s.url ? el("a", {href: s.url, target:"_blank", rel:"noopener noreferrer", text: s.t}) : s.t), el("p", {class:"note", style:"margin-top:4px"}, [s.pub, s.date].filter(Boolean).join(", ") + " ", el("span", {class:"st " + (s.kind === "press" ? "part" : "ok"), text: s.kind === "press" ? "Press report" : "Company source"})));
  else d.append(el("p", {class:"note", text:"No source recorded."}));
  if (s && s.kind === "press") d.append(el("p", {class:"note", style:"margin-top:8px", text:"This figure comes from a trade press report of the company's results presentation. It has not been checked against the company's own slides."}));
  $(".x", d).focus();
}
function closeDrawer(){ $("#drawer").hidden = true; }
function viewData(v){
  const q = state.quarter, all = figures(q), text = state.dataText.toLowerCase();
  const rows = all.filter(f => (state.dataCo === "all" || f.c.id === state.dataCo) && (state.dataType === "all" || f.type === state.dataType) && (!text || (f.c.name + " " + f.item + " " + (f.bucket || "")).toLowerCase().includes(text)));
  const press = all.filter(f => f.src && f.src.kind === "press").length;
  const coSel = el("select", {id:"d-co", "aria-label":"Company", onchange: e => { state.dataCo = e.target.value; render(); }}, el("option", {value:"all", text:"All companies"}), ...cos().map(c => el("option", {value: c.id, text: c.name}))); coSel.value = state.dataCo;
  const types = el("div", {class:"chips"}, ...["all","Group","Region","Segment"].map(t => el("button", {class:"chip", type:"button", "aria-pressed": String(state.dataType === t), onclick: () => { state.dataType = t; render(); }}, t === "all" ? "All figures" : t)));
  const search = el("input", {type:"search", id:"d-search", placeholder:"Filter by name", "aria-label":"Filter by name", value: state.dataText});
  search.addEventListener("input", e => { state.dataText = e.target.value; render(); const n = $("#d-search"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); });
  const flash = (b, t) => { const o = b.textContent; b.textContent = t; setTimeout(() => { b.textContent = o; }, 1600); };
  const dl = el("button", {class:"btn", type:"button", onclick: e => { const url = URL.createObjectURL(new Blob([csv()], {type:"text/csv"})), a = el("a", {href: url, download:"luxury-earnings-tracker.csv"}); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); flash(e.currentTarget, "Saved"); }}, "Download CSV, all quarters");
  const tb = el("table", {class:"num"}, el("thead", null, el("tr", null, el("th", {text:"Company"}), el("th", {class:"l", text:"Figure"}), el("th", {class:"l", text:"Type"}), el("th", {text:"Growth"}), el("th", {text:"Revenue"}), el("th", {class:"l", text:"Basis"}), el("th", {class:"l", text:"Source"}))));
  const body = el("tbody");
  rows.forEach(f => body.append(el("tr", {class:"click", tabindex:"0", onclick: () => openDrawer(f), onkeydown: e => { if (e.key === "Enter") openDrawer(f); }},
    el("td", null, el("span", {class:"cdot", style:"background:" + colorOf(f.c)}), f.c.name), el("td", {class:"l", text: f.item + (f.bucket && f.bucket !== f.item ? "  →  " + f.bucket : "")}), el("td", {class:"l", style:"color:var(--ink-2)", text: f.type}),
    el("td", {text: fmtPct(f.g)}), el("td", {text: fmtRev(f.rev, f.c.cur)}), el("td", {class:"l", style:"color:var(--ink-2)", text: f.c.basis}),
    el("td", {class:"l"}, el("span", {class:"st " + (f.src && f.src.kind === "press" ? "part" : "ok"), text: f.src && f.src.kind === "press" ? "Press" : "Company"}), el("span", {class:"note", text: f.src ? f.src.date : ""})))));
  if (!rows.length) body.append(el("tr", null, el("td", {colspan:"7", class:"note", text:"No figures match these filters."})));
  tb.append(body);
  v.append(exhibit(all.length + " figures for " + qLabel(q) + ". " + (all.length - press) + " come from company sources and " + press + " from press reports.",
    el("div", null, el("div", {class:"toolbar"}, coSel, types, search, el("span", {class:"sp"}), dl), el("div", {class:"tscroll"}, tb)),
    {sub:"Select a row to see the evidence and the link for that figure.", src:"Company: a press release, a regulatory filing or the company's own site. Press: a trade press report of the results presentation."}));

  const gt = el("table", null, el("thead", null, el("tr", null, ...["Company","What was said","Stated","Type","Against the figures","Read"].map(h => el("th", {class:"l", scope:"col", text: h})))));
  const gb = el("tbody"), kinds = {testable:["test","Can be tested"], qualitative:["","Qualitative"], none:["","No guidance"]};
  cos().forEach(c => { const g = c.guidance; if (!g || !g.text) return; const k = kinds[g.kind] || kinds.qualitative, med = median(sameIndustry(c).filter(o => o.id !== c.id).map(o => gv(o, D.latest)));
    gb.append(el("tr", null, el("td", {text: c.name}), el("td", {class:"l", text: g.text}), el("td", {class:"l", style:"white-space:nowrap", text: g.date || ""}), el("td", {class:"l"}, el("span", {class:"st " + k[0], text: k[1]})), el("td", {class:"l", text: (g.evidence || "").replace("{median}", fmtPct(med))}), el("td", {class:"l", text: g.read || ""}))); });
  gt.append(gb);
  const testable = cos().filter(c => c.guidance && c.guidance.kind === "testable").length;
  v.append(exhibit(testable + " of " + cos().length + " companies gave guidance that can be tested against results.", el("div", {class:"tscroll"}, gt), {sub:"Luxury groups rarely give numeric guidance. Each statement is logged with its date.", src:"Source: company releases, as of " + qLabel(D.latest) + " reporting."}));
}

/* ---------- method ---------- */
function viewMethod(v){
  const node = $("#tpl-method").content.cloneNode(true), th = META.thresholds || {};
  node.querySelectorAll("[data-t]").forEach(n => { if (isNum(th[n.dataset.t])) n.textContent = trim1(th[n.dataset.t]); });
  v.append(el("div", {class:"ex"}, el("div", {class:"mono", text:"Definitions"}), el("div", {class:"body"}, node)));
  v.append(el("div", null, el("div", {class:"mono", style:"margin-bottom:8px", text:"The pipeline"}), el("div", {class:"steps"},
    ...[["1 · LLM with web search","Research","Finds the newest quarterly release for each company on the watchlist, and only searches once a release is due."],["2 · LLM","Extract","Reads the release and returns each figure with the sentence or table row that states it."],["3 · Rules","Verify","Confirms that every quote and number is in the release. Anything unmatched is held back for review."],["4 · Arithmetic","Model","Computes changes, peer medians, two-year growth, base effects and a rule-based signal."],["5 · LLM","Interpret","Writes the note for each company from the model output. A note with a number that is not in the data is discarded."]]
      .map(s => el("div", null, el("span", {class:"mono", text: s[0]}), el("b", {text: s[1]}), el("span", {text: s[2]}))))));
  const ql = META.quality, ev = META.eval, checks = el("ul", {class:"runs"});
  if (ql) checks.append(el("li", null, el("span", {class:"st " + (ql.errors ? "miss" : "ok"), text: ql.errors ? "Failed" : "Passed"}), el("b", {style:"font-weight:600", text:"Data gate"}),
    el("span", {class:"note", text: ql.figures + " figures checked for a source, a valid quarter and a plausible value. " + (ql.errors ? ql.errors + " errors." : "No errors.")})));
  if (ql) (ql.warnings || []).forEach(w => checks.append(el("li", null, el("span", {class:"st part", text:"Open"}), el("span", {class:"note", text: w}))));
  checks.append(ev && ev.total
    ? el("li", null, el("span", {class:"st " + (ev.hits === ev.total ? "ok" : "part"), text: ev.hits + " of " + ev.total}), el("b", {style:"font-weight:600", text:"Extraction test"}),
        el("span", {class:"note", text:"The LLM re-read " + (isNum(ev.read) ? ev.read + " of " + ev.releases : "the") + " " + qLabel(ev.quarter) + " releases and its figures were compared with the verified dataset."
          + (ev.skipped && ev.skipped.length ? " " + ev.skipped.length + " could not be read: " + ev.skipped.join("; ") + "." : "") + " Run " + (ev.at || "").slice(0, 10) + " on " + ev.model + "."}))
    : el("li", null, el("span", {class:"st", text:"Not run"}), el("b", {style:"font-weight:600", text:"Extraction test"}), el("span", {class:"note", text:"Scores the LLM extraction against the verified dataset. It has not been run yet."})));
  v.append(el("div", {class:"ex"}, el("div", {class:"mono", text:"Quality checks"}), el("div", {class:"body"}, checks)));
  const ul = el("ul", {class:"runs"});
  (META.runs || []).slice().reverse().forEach(r => { const parts = (r.results || []).map(x => [x.company, x.quarter ? qLabel(x.quarter) : "", x.status, x.checks ? x.checks + " figures matched" : "", x.detail || ""].filter(Boolean).join(", "));
    ul.append(el("li", null, el("b", {style:"font-weight:600", text: (r.at || "").slice(0, 10)}), el("span", {class:"tag", style:"margin-left:0", text: r.command || "run"}), el("span", {class:"note", text: parts.join("; ")}), r.usage ? el("span", {class:"note", text:"Estimated API cost $" + r.usage.estimated_usd.toFixed(2)}) : null)); });
  if (!ul.children.length) ul.append(el("li", {class:"note", text:"No runs logged yet."}));
  v.append(el("div", {class:"ex"}, el("div", {class:"mono", text:"Recent runs" + (META.built_at ? " · site data built " + META.built_at.slice(0, 10) : "")}), el("div", {class:"body"}, ul)));
}

/* ---------- shell ---------- */
const VIEWS = {overview: viewOverview, compare: viewCompare, categories: viewCategories, company: viewCompany, data: viewData, method: viewMethod};
function render(){
  if (!D) return;
  redraws = []; exNo = 0; tipHide();
  const v = $("#view"); v.replaceChildren();
  $("#title").textContent = TITLES[state.view];
  $("#q-wrap").style.visibility = state.view === "method" ? "hidden" : "visible";
  $("#g-wrap").style.display = state.view === "overview" || state.view === "compare" ? "" : "none";   /* the other screens show every group */
  document.querySelectorAll("#nav a").forEach(a => { if (a.dataset.v === state.view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  VIEWS[state.view](v);
}
function route(){
  const h = location.hash.replace(/^#/, ""), parts = h.split("/"), name = VIEWS[parts[0]] ? parts[0] : "overview";
  const changed = name !== state.view; state.view = name;
  if (name === "company" && parts[1] && D && cos().some(c => c.id === parts[1])) state.company = parts[1];
  closeDrawer(); render(); if (changed) window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
window.addEventListener("scroll", tipHide, {passive: true});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
$("#f-quarter").addEventListener("change", e => { state.quarter = e.target.value; render(); });
$("#f-group").addEventListener("change", e => { state.group = e.target.value; state.sel = new Set(grp().map(c => c.id)); render(); });
let lastW = 0, rz = 0;
if (window.ResizeObserver) new ResizeObserver(() => { const w = $("#view").clientWidth; if (w === lastW) return; lastW = w; cancelAnimationFrame(rz); rz = requestAnimationFrame(() => redraws.forEach(f => f())); }).observe($("#view"));

fetch("data.json", {cache:"no-store"}).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(d => {
  D = {asOf: d.asOf, latest: d.latest, companies: d.companies}; MODEL = d.model || {}; NOTES = d.notes || {}; META = d.meta || {}; TAX = d.taxonomy || {};
  state.group = firstIndustry(); state.quarter = D.latest; state.company = cos()[0].id; state.againstCo = cos()[0].id; state.sel = new Set(grp().map(c => c.id));
  const gs = $("#f-group"); gs.replaceChildren(...industries().map(i => el("option", {value: i.id, text: i.label}))); gs.value = state.group;
  const sel = $("#f-quarter"); sel.replaceChildren(...allQuarters().reverse().map(q => el("option", {value: q, text: qLabel(q)}))); sel.value = state.quarter;
  $("#side-asof").textContent = "Data as of " + D.asOf;
  route();
}).catch(() => {
  $("#view").replaceChildren(el("p", {class:"note", text:"The data file did not load. Open the site through a web server. From the project folder run: python -m pipeline.run serve"}));
});
