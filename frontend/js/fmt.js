// Format angka dan waktu lewat Intl, locale id-ID, zona WIB.
const TZ = "Asia/Jakarta";
const L = "id-ID";
const cache = new Map();
function nf(min, max) {
  const k = `${min}-${max}`;
  if (!cache.has(k)) cache.set(k, new Intl.NumberFormat(L, { minimumFractionDigits: min, maximumFractionDigits: max }));
  return cache.get(k);
}
export const num = (x, d = 1, min = 0) => (x === null || x === undefined || Number.isNaN(x) ? "–" : nf(Math.min(min, d), d).format(x));
export const fix = (x, d = 1) => num(x, d, d);
export const int = (x) => num(x, 0);
export const pct = (x, d = 0) => (x === null || x === undefined ? "–" : `${num(x, d)}\u00a0%`);
const rp = new Intl.NumberFormat(L, { style: "currency", currency: "IDR", maximumFractionDigits: 0 });
export const rupiah = (x) => (x === null || x === undefined ? "–" : rp.format(x));

// Server mengirim waktu naif dalam WIB; tambahkan offset agar benar di zona mana pun.
export function d(iso) {
  if (!iso) return null;
  if (iso instanceof Date) return iso;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso.length === 10 ? iso + "T00:00:00" : iso}+07:00`);
}
const df = (o) => new Intl.DateTimeFormat(L, { timeZone: TZ, ...o });
const F = {
  jam: df({ hour: "2-digit", minute: "2-digit" }),
  tgl: df({ day: "numeric", month: "short" }),
  tglPanjang: df({ weekday: "long", day: "numeric", month: "long", year: "numeric" }),
  tglTahun: df({ day: "numeric", month: "short", year: "numeric" }),
  hari: df({ weekday: "short" }),
  hariPanjang: df({ weekday: "long" }),
  bulan: df({ month: "long", year: "numeric" }),
  waktu: df({ day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }),
};
export const jam = (x) => F.jam.format(d(x)).replace(":", ".");
export const tgl = (x) => F.tgl.format(d(x));
export const tglTahun = (x) => F.tglTahun.format(d(x));
export const tglPanjang = (x) => F.tglPanjang.format(d(x));
export const hari = (x) => F.hari.format(d(x));
export const hariPanjang = (x) => F.hariPanjang.format(d(x));
export const bulan = (x) => F.bulan.format(d(x));
export const waktu = (x) => F.waktu.format(d(x)).replace(":", ".");
export const rentangJam = (a, b) => `${jam(a)}–${jam(b)}`;

const rtf = new Intl.RelativeTimeFormat(L, { numeric: "auto" });
export function relatif(x) {
  const s = (d(x) - Date.now()) / 1000;
  const a = Math.abs(s);
  if (a < 60) return "baru saja";
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}
export function inisial(nama = "") {
  return nama.replace(/^(Dr\.|Prof\.)\s*/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}
