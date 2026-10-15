// Grafik deret waktu SVG ringan. Fokus pada grafik lalu tekan panah kiri/kanan untuk membaca nilai per titik.
import { esc } from "./ui.js";
import * as f from "./fmt.js";

const NS = "http://www.w3.org/2000/svg";

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  const step = [1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10].find((s) => n <= s);
  return step * p;
}

/**
 * opts: {
 *   data: [{t, ...}], series: [{key, type: line|band|area|bar|base, cls, label, lo, hi, unit}],
 *   height, label (alt text), xTick: fn(t,i) -> string|null, xRead: fn(t) -> string,
 *   now: iso, markKey: key boolean untuk anomali, unit
 * }
 */
export function timeChart(host, opts) {
  host.classList.add("chart");
  host.tabIndex = 0;
  host.setAttribute("role", "group");
  host.setAttribute("aria-roledescription", "grafik");
  host.setAttribute("aria-label", `${opts.label}. Tekan panah kiri atau kanan untuk membaca nilai per titik.`);
  const readout = document.createElement("div");
  readout.className = "chart-readout";
  readout.setAttribute("aria-hidden", "true");
  const live = document.createElement("div");
  live.className = "sr";
  live.setAttribute("aria-live", "polite");
  let idx = -1;
  let geo = null;
  const data = opts.data;
  const H = opts.height || 260;
  const pad = { t: 22, r: 12, b: 26, l: 44 };

  function draw(width) {
    if (!data.length) {
      host.innerHTML = '<p class="empty">Belum ada data untuk digambar. Grafik muncul setelah data meter masuk.</p>';
      return;
    }
    const W = Math.max(280, Math.round(width));
    const n = data.length;
    const vals = [];
    for (const s of opts.series) for (const r of data) {
      for (const k of [s.key, s.hi]) if (k && r[k] !== null && r[k] !== undefined) vals.push(r[k]);
    }
    const ymax = niceMax(Math.max(1, ...vals) * 1.05);
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const bw = iw / n;
    const x = (i) => pad.l + (opts.bars ? bw * i + bw / 2 : (n === 1 ? iw / 2 : (iw * i) / (n - 1)));
    const y = (v) => pad.t + ih - (v / ymax) * ih;
    geo = { x, y, W, n, iw, pad, bw };

    const path = (key) => {
      let dd = "", on = false;
      data.forEach((r, i) => {
        const v = r[key];
        if (v === null || v === undefined) { on = false; return; }
        dd += `${on ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        on = true;
      });
      return dd;
    };
    const area = (lo, hi) => {
      // potong menjadi segmen kontinu
      const segs = []; let cur = [];
      data.forEach((r, i) => {
        const a = lo ? r[lo] : 0, b = r[hi];
        if (b === null || b === undefined || (lo && (a === null || a === undefined))) { if (cur.length) segs.push(cur); cur = []; return; }
        cur.push([i, a, b]);
      });
      if (cur.length) segs.push(cur);
      return segs.map((s) => {
        const top = s.map(([i, , b], j) => `${j ? "L" : "M"}${x(i).toFixed(1)},${y(b).toFixed(1)}`).join("");
        const bot = s.slice().reverse().map(([i, a]) => `L${x(i).toFixed(1)},${y(a).toFixed(1)}`).join("");
        return top + bot + "Z";
      }).join("");
    };

    let g = `<g class="grid">`;
    const ticks = 4;
    for (let k = 0; k <= ticks; k++) {
      const v = (ymax / ticks) * k;
      g += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/>`;
    }
    g += `</g><g class="axis">`;
    for (let k = 0; k <= ticks; k++) {
      const v = (ymax / ticks) * k;
      g += `<text x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${esc(f.num(v, ymax < 10 ? 1 : 0))}</text>`;
    }
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 64))));
    data.forEach((r, i) => {
      const lbl = opts.xTick ? opts.xTick(r.t, i, step) : (i % step === 0 ? f.jam(r.t) : null);
      if (lbl) g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(lbl)}</text>`;
    });
    g += `<text x="${pad.l - 8}" y="${pad.t - 12}" text-anchor="end">${esc(opts.unit || "")}</text></g>`;

    // anomali: latar merah tipis + penanda bawah
    if (opts.markKey) {
      data.forEach((r, i) => {
        if (!r[opts.markKey]) return;
        const x0 = opts.bars ? x(i) - bw / 2 : x(i) - iw / (n - 1) / 2;
        const w = opts.bars ? bw : iw / (n - 1);
        g += `<rect class="r-anom" x="${x0}" y="${pad.t}" width="${w}" height="${ih}"/>`;
        g += `<rect class="m-anom" x="${x0}" y="${pad.t + ih + 1}" width="${w}" height="3"/>`;
      });
    }
    for (const s of opts.series) {
      if (s.type === "band") g += `<path class="${s.cls || "a-band"}" d="${area(s.lo, s.hi)}"/>`;
      else if (s.type === "area") g += `<path class="${s.cls}" d="${area(null, s.key)}"/>`;
      else if (s.type === "bar") {
        data.forEach((r, i) => {
          const v = r[s.key];
          if (v === null || v === undefined) return;
          const cls = s.hiKey && r[s.hiKey] ? "bar bar-hi" : "bar";
          g += `<rect class="${cls}" x="${(x(i) - bw * 0.36).toFixed(1)}" y="${y(v).toFixed(1)}" width="${(bw * 0.72).toFixed(1)}" height="${(y(0) - y(v)).toFixed(1)}" rx="1.5"/>`;
        });
      } else g += `<path class="${s.cls}" d="${path(s.key)}"/>`;
    }
    if (opts.now) {
      const tn = f.d(opts.now).getTime();
      let ni = data.findIndex((r) => f.d(r.t).getTime() > tn) - 1;
      if (ni >= 0) {
        const xn = x(ni) + (x(ni + 1) - x(ni)) * ((tn - f.d(data[ni].t).getTime()) / 3600000);
        g += `<g class="now"><line x1="${xn}" x2="${xn}" y1="${pad.t}" y2="${pad.t + ih}"/><text x="${xn + 4}" y="${pad.t + 10}">sekarang</text></g>`;
      }
    }
    g += `<g class="cursor" visibility="hidden"><line y1="${pad.t}" y2="${pad.t + ih}"/></g>`;
    host.innerHTML = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(opts.label)}"><title>${esc(opts.label)}</title>${g}</svg>`;
    host.append(readout, live);
    if (idx >= 0) show(idx, false);
  }

  function show(i, announce = true) {
    if (!geo || i < 0 || i >= data.length) return;
    idx = i;
    const r = data[i];
    const cur = host.querySelector(".cursor");
    const cx = geo.x(i);
    cur.setAttribute("visibility", "visible");
    const ln = cur.querySelector("line");
    ln.setAttribute("x1", cx); ln.setAttribute("x2", cx);
    cur.querySelectorAll("circle").forEach((c) => c.remove());
    const rows = [];
    for (const s of opts.series) {
      if (!s.label) continue;
      const v = r[s.key];
      let txt = v === null || v === undefined ? "–" : `${f.fix(v, 1)} ${s.unit || opts.unit || ""}`;
      if (s.type === "band") txt = r[s.lo] === null || r[s.lo] === undefined ? "–" : `${f.fix(r[s.lo], 1)}–${f.fix(r[s.hi], 1)}`;
      rows.push([s, txt]);
      if (v !== null && v !== undefined && s.type !== "band" && s.type !== "bar") {
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", geo.y(v)); c.setAttribute("r", 3.5);
        c.setAttribute("class", s.dot || "");
        cur.append(c);
      }
    }
    const judul = opts.xRead ? opts.xRead(r.t) : `${f.hari(r.t)} ${f.jam(r.t)}`;
    const anom = opts.markKey && r[opts.markKey] ? `<div><span><i class="key key-crit"></i>Anomali</span><span>ya</span></div>` : "";
    readout.innerHTML = `<b>${esc(judul)}</b>${rows.map(([s, t]) => `<div><span><i class="key ${s.keyCls || ""}"></i>${esc(s.label)}</span><span>${esc(t)}</span></div>`).join("")}${anom}`;
    const leftPct = (cx / geo.W) * 100;
    readout.style.left = `clamp(90px, ${leftPct}%, calc(100% - 90px))`;
    readout.classList.add("on");
    if (announce) live.textContent = `${judul}. ${rows.map(([s, t]) => `${s.label} ${t}`).join(", ")}${anom ? ", anomali" : ""}.`;
  }
  function hide() {
    readout.classList.remove("on");
    host.querySelector(".cursor")?.setAttribute("visibility", "hidden");
    idx = -1;
  }

  host.addEventListener("keydown", (e) => {
    const map = { ArrowRight: 1, ArrowLeft: -1, End: Infinity, Home: -Infinity };
    if (!(e.key in map) && e.key !== "Escape") return;
    e.preventDefault();
    if (e.key === "Escape") return hide();
    let start = idx;
    if (start < 0) start = opts.startIndex ?? data.length - 1;
    const step = map[e.key];
    const next = step === Infinity ? data.length - 1 : step === -Infinity ? 0 : Math.max(0, Math.min(data.length - 1, start + (idx < 0 ? 0 : step)));
    show(next);
  });
  host.addEventListener("blur", hide);
  host.addEventListener("pointermove", (e) => {
    if (!geo) return;
    const box = host.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * geo.W;
    let best = 0, bd = Infinity;
    for (let i = 0; i < data.length; i++) { const dd = Math.abs(geo.x(i) - px); if (dd < bd) { bd = dd; best = i; } }
    show(best, false);
  });
  host.addEventListener("pointerleave", () => { if (document.activeElement !== host) hide(); });

  let lebar = 0;
  const gambar = (w) => { if (w > 0 && Math.abs(w - lebar) >= 1) { lebar = w; draw(w); } };
  gambar(host.clientWidth || 720);
  const ro = new ResizeObserver((entries) => gambar(entries[0].contentRect.width));
  ro.observe(host);
  return { destroy: () => ro.disconnect() };
}
