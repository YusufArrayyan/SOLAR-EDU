// Kerangka aplikasi: sesi, navigasi berbasis peran, router hash, notifikasi.
import { api, setUnauthorizedHandler } from "./api.js";
import * as f from "./fmt.js";
import { esc, html, isDirty, render, setDirty, skeleton, toast } from "./ui.js";

const ICON = {
  ringkasan: '<path d="M3 13h4l3-8 4 14 3-6h4"/>',
  rekomendasi: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>',
  peringkat: '<path d="M8 21V11M16 21V7M12 21V3M4 21h16"/>',
  dampak: '<path d="M12 3v18M17 7.5c0-1.9-2.2-3.5-5-3.5s-5 1.6-5 3.5S9.2 11 12 11.5s5 1.9 5 4-2.2 3.5-5 3.5-5-1.6-5-3.5"/>',
  belajar: '<path d="M2 7l10-4 10 4-10 4z"/><path d="M6 9v5c0 1.7 2.7 3 6 3s6-1.3 6-3V9"/>',
  pengaturan: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};

const ROUTES = [
  { path: "ringkasan", label: "Ringkasan", izin: "ringkasan.lihat", load: () => import("./views/ringkasan.js") },
  { path: "rekomendasi", label: "Rekomendasi", izin: "rekomendasi.lihat", load: () => import("./views/rekomendasi.js"), badge: "rek" },
  { path: "peringkat", label: "Papan peringkat", izin: "dampak.lihat", load: () => import("./views/peringkat.js") },
  { path: "dampak", label: "Dampak", izin: "dampak.lihat", load: () => import("./views/dampak.js") },
  { path: "belajar", label: "Pusat belajar", izin: "belajar.lihat", load: () => import("./views/belajar.js") },
  { path: "pengaturan", label: "Pengaturan", izin: "pengaturan.ubah", load: () => import("./views/pengaturan.js") },
];
const AKUN = { path: "akun", label: "Akun", izin: null, load: () => import("./views/akun.js") };
const BERANDA = { pengelola: "ringkasan", piket: "rekomendasi", tim: "ringkasan", pimpinan: "dampak", akademik: "belajar" };

const state = { user: null, cleanup: null, token: 0, pollTimer: null, lastHash: location.hash };
const $ = (id) => document.getElementById(id);

export function can(izin) { return !izin || state.user?.izin.includes(izin); }
export const user = () => state.user;

export function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [p, q = ""] = h.split("?");
  const parts = p.split("/").filter(Boolean);
  return { parts, query: new URLSearchParams(q) };
}
export function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

/* ---------- tema */
function applyTheme(t) {
  const dark = t === "dark" || (t !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", dark ? "#0a0a0a" : "#fafafa"));
  document.getElementById("tema")?.setAttribute("aria-pressed", String(dark));
}
applyTheme(localStorage.getItem("tema"));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(localStorage.getItem("tema")));

/* ---------- masuk */
async function showLogin(pesan) {
  stopPolling();
  state.user = null;
  $("shell").hidden = true;
  const box = $("masuk");
  box.hidden = false;
  const { renderLogin } = await import("./views/masuk.js");
  renderLogin(box, pesan, async (u) => { state.user = u; await boot(); });
}

setUnauthorizedHandler((detail) => {
  if (state.user) showLogin(typeof detail === "string" ? detail : "Sesi berakhir. Silakan masuk lagi.");
});

async function boot() {
  $("masuk").hidden = true;
  $("masuk").innerHTML = "";
  $("shell").hidden = false;
  const u = state.user;
  $("user-nama").textContent = u.nama;
  $("user-peran").textContent = u.demo ? `${u.peran_label} · akun demo` : u.peran_label;
  $("user-avatar").textContent = f.inisial(u.nama);
  buildNav();
  startPolling();
  if (!location.hash || location.hash === "#/" || location.hash === "#") location.hash = `#/${BERANDA[u.peran]}`;
  else route();
}

function buildNav() {
  const items = ROUTES.filter((r) => can(r.izin));
  render($("nav-list"), html`${items.map((r) => html`<li><a href="#/${r.path}" data-path="${r.path}"><svg viewBox="0 0 24 24" aria-hidden="true"></svg><span>${r.label}</span>${r.badge ? html`<span class="count" data-badge="${r.badge}" hidden></span>` : ""}</a></li>`)}`);
  // ikon disisipkan terpisah karena berupa markup statis tepercaya
  $("nav-list").querySelectorAll("a").forEach((a) => { a.querySelector("svg").innerHTML = ICON[a.dataset.path] || ""; });
}

function markNav(path) {
  $("nav-list").querySelectorAll("a").forEach((a) => {
    if (a.dataset.path === path) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

/* ---------- router */
async function route() {
  if (!state.user) return;
  const { parts, query } = parseHash();
  const path = parts[0] || BERANDA[state.user.peran];
  const r = ROUTES.find((x) => x.path === path) || (path === AKUN.path ? AKUN : null);
  const main = $("konten");
  closeNav();
  if (state.cleanup) { try { state.cleanup(); } catch { /* abaikan */ } state.cleanup = null; }
  setDirty(false);
  markNav(r?.path);
  const token = ++state.token;
  if (!r) {
    document.title = "Halaman tidak ditemukan · SOLAR-EDU AI";
    render(main, html`<div class="empty"><h1>Halaman tidak ditemukan</h1><p>Alamat ini tidak ada. Gunakan menu untuk membuka halaman lain.</p><a class="btn" href="#/${BERANDA[state.user.peran]}">Kembali ke beranda</a></div>`);
    return;
  }
  if (!can(r.izin)) {
    document.title = "Akses dibatasi · SOLAR-EDU AI";
    render(main, html`<div class="empty"><h1>Akses dibatasi</h1><p>Peran ${state.user.peran_label} tidak memiliki akses ke ${r.label}. Hubungi tim pengelola bila perlu akses.</p><a class="btn" href="#/${BERANDA[state.user.peran]}">Kembali ke beranda</a></div>`);
    return;
  }
  document.title = `${r.label} · SOLAR-EDU AI`;
  render(main, skeleton());
  try {
    const mod = await r.load();
    if (token !== state.token) return;
    const cleanup = await mod.default({ main, params: parts.slice(1), query, user: state.user, isCurrent: () => token === state.token });
    if (token !== state.token) { if (typeof cleanup === "function") cleanup(); return; }
    state.cleanup = typeof cleanup === "function" ? cleanup : null;
  } catch (e) {
    if (token !== state.token || e.status === 401) return;
    console.error(e);
    render(main, html`<div class="empty"><h1>Halaman gagal dimuat</h1><p>${e.message || "Terjadi kesalahan."}</p><button class="btn" type="button" data-ulang>Muat ulang</button></div>`);
    main.querySelector("[data-ulang]").addEventListener("click", route);
  }
  if (state.focusMain) main.focus({ preventScroll: true });
  state.focusMain = true;
  window.scrollTo({ top: 0 });
}

window.addEventListener("hashchange", (e) => {
  if (isDirty() && !confirm("Perubahan belum disimpan. Tinggalkan halaman ini?")) {
    history.replaceState(null, "", new URL(e.oldURL).hash);
    return;
  }
  state.lastHash = location.hash;
  route();
});

/* ---------- menu ponsel */
function openNav() {
  $("nav").classList.add("open"); $("scrim").hidden = false; $("nav-buka").setAttribute("aria-expanded", "true");
  $("nav").querySelector("a")?.focus();
}
function closeNav() {
  if (!$("nav").classList.contains("open")) return;
  $("nav").classList.remove("open"); $("scrim").hidden = true; $("nav-buka").setAttribute("aria-expanded", "false");
}
$("nav-buka").addEventListener("click", openNav);
$("nav-tutup").addEventListener("click", () => { closeNav(); $("nav-buka").focus(); });
$("scrim").addEventListener("click", closeNav);

$("tema").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("tema", next);
  applyTheme(next);
  window.dispatchEvent(new Event("solar:tema"));
});

$("keluar").addEventListener("click", async () => {
  if (isDirty() && !confirm("Perubahan belum disimpan. Tetap keluar?")) return;
  try { await api("/api/auth/keluar", { method: "POST" }); } catch { /* sesi mungkin sudah habis */ }
  location.hash = "";
  showLogin("Berhasil keluar.");
});

/* ---------- notifikasi (polling 60 detik; peristiwa tampil kurang dari 5 menit) */
const panel = $("notif-panel");
const btn = $("notif-btn");
function setPanel(open) {
  panel.hidden = !open;
  btn.setAttribute("aria-expanded", String(open));
  if (open) loadNotif();
}
btn.addEventListener("click", (e) => { e.stopPropagation(); setPanel(panel.hidden); });
document.addEventListener("click", (e) => { if (!panel.hidden && !panel.contains(e.target)) setPanel(false); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!panel.hidden) { setPanel(false); btn.focus(); }
    else if ($("nav").classList.contains("open")) { closeNav(); $("nav-buka").focus(); }
  }
});
panel.addEventListener("click", async (e) => {
  const a = e.target.closest("a[data-id]");
  if (a) { setPanel(false); api("/api/notifikasi/baca", { method: "POST", body: { ids: [a.dataset.id] } }).then(poll).catch(() => {}); }
});
$("notif-baca").addEventListener("click", async () => {
  await api("/api/notifikasi/baca", { method: "POST", body: {} });
  loadNotif(); poll();
});

const CRIT = new Set(["eskalasi", "galat_data", "kambuh"]);
async function loadNotif() {
  const list = $("notif-list");
  try {
    const d = await api("/api/notifikasi");
    if (!d.baris.length) { list.innerHTML = '<li class="notif-empty">Belum ada notifikasi. Rekomendasi baru, tugas, dan batas waktu akan muncul di sini.</li>'; return; }
    render(list, html`${d.baris.map((n) => html`<li><a href="${n.tautan || "#/"}" data-id="${n.id}" class="${n.dibaca ? "" : "unread"} ${CRIT.has(n.jenis) ? "n-crit" : ""}"><span><b>${n.judul}</b>${n.isi ? html`<span class="isi">${n.isi}</span>` : ""}<small>${f.relatif(n.waktu)}</small></span></a></li>`)}`);
  } catch (e) { list.innerHTML = `<li class="notif-empty">${esc(e.message)}</li>`; }
}

let lastUnread = null;
async function poll() {
  if (!state.user) return;
  try {
    const d = await api("/api/notifikasi");
    const c = $("notif-count");
    c.hidden = d.belum_dibaca === 0;
    c.textContent = d.belum_dibaca > 9 ? "9+" : String(d.belum_dibaca);
    btn.setAttribute("aria-label", d.belum_dibaca ? `Notifikasi, ${d.belum_dibaca} belum dibaca` : "Notifikasi");
    if (lastUnread !== null && d.belum_dibaca > lastUnread) {
      const baru = d.baris.find((n) => !n.dibaca);
      if (baru) toast(baru.judul);
    }
    lastUnread = d.belum_dibaca;
    if (can("rekomendasi.verifikasi")) {
      const r = await api("/api/rekomendasi?status=Diusulkan");
      const b = document.querySelector('[data-badge="rek"]');
      if (b) { b.hidden = !r.hitung.Diusulkan; b.textContent = r.hitung.Diusulkan; b.setAttribute("aria-label", `${r.hitung.Diusulkan} menunggu verifikasi`); }
    }
  } catch { /* ditangani handler 401 */ }
}
function startPolling() { stopPolling(); poll(); state.pollTimer = setInterval(poll, 60000); }
function stopPolling() { clearInterval(state.pollTimer); }
export const refreshBadges = poll;
export function reload() { state.focusMain = false; route(); }

/* ---------- mulai */
(async () => {
  try {
    const [u, sehat] = await Promise.all([api("/api/auth/saya"), fetch("/api/sehat").then((r) => r.json()).catch(() => ({}))]);
    $("badge-sim").hidden = sehat.simulasi === false;
    if (sehat.gedung) $("gedung-nama").textContent = sehat.gedung;
    state.user = u;
    await boot();
  } catch {
    showLogin();
  }
})();
