// Utilitas antarmuka: escape HTML, toast, tombol sibuk, galat formulir, batang kecil SVG.
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Tagged template yang meng-escape semua nilai kecuali yang dibungkus raw().
const RAW = Symbol("raw");
export const raw = (s) => ({ [RAW]: true, s: String(s) });
export function html(strings, ...vals) {
  let out = "";
  strings.forEach((str, i) => {
    out += str;
    if (i < vals.length) {
      const v = vals[i];
      if (Array.isArray(v)) out += v.map((x) => (x && x[RAW] ? x.s : esc(x))).join("");
      else if (v && v[RAW]) out += v.s;
      else if (v !== false && v !== null && v !== undefined) out += esc(v);
    }
  });
  return raw(out);
}
export const render = (el, tpl) => { el.innerHTML = tpl && tpl[RAW] ? tpl.s : String(tpl); };

export function toast(pesan, jenis = "ok") {
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast${jenis === "err" ? " t-err" : ""}`;
  el.textContent = pesan;
  box.append(el);
  setTimeout(() => el.remove(), jenis === "err" ? 7000 : 4500);
}

export async function busy(btn, label, fn) {
  const asli = btn.textContent;
  btn.setAttribute("aria-busy", "true");
  btn.disabled = true;
  btn.textContent = label;
  try { return await fn(); } finally {
    btn.removeAttribute("aria-busy");
    btn.disabled = false;
    btn.textContent = asli;
  }
}

// Tampilkan galat per kolom di samping isian; fokus ke isian pertama yang salah.
export function fieldErrors(form, kolom = {}) {
  form.querySelectorAll(".err[data-for]").forEach((e) => { e.textContent = ""; e.hidden = true; });
  form.querySelectorAll("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
  let first = null;
  for (const [name, msg] of Object.entries(kolom)) {
    const input = form.elements[name];
    const slot = form.querySelector(`.err[data-for="${CSS.escape(name)}"]`);
    if (input) { input.setAttribute("aria-invalid", "true"); first ||= input; }
    if (slot) { slot.textContent = msg; slot.hidden = false; }
  }
  first?.focus();
}

export function bar(nilai, maks = 100, cls = "") {
  const w = Math.max(0, Math.min(100, (nilai / (maks || 1)) * 100));
  return raw(`<svg class="mbar ${cls}" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true" width="100%" height="6"><rect class="mbar-bg" width="100" height="6" rx="3"/><rect class="mbar-fg" width="${w.toFixed(2)}" height="6" rx="3"/></svg>`);
}

export const skeleton = () => raw(`<div class="stack" aria-busy="true"><span class="sr">Memuat…</span><div class="skel skel-line"></div><div class="skel skel-block"></div><div class="skel skel-block"></div></div>`);

export function emptyState(judul, isi, aksi = "") {
  return html`<div class="empty"><h2>${judul}</h2><p>${isi}</p>${aksi ? raw(aksi) : ""}</div>`;
}

let dirty = false;
export const setDirty = (v) => { dirty = v; };
export const isDirty = () => dirty;
window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
