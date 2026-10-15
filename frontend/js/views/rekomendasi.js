import { api } from "../api.js";
import { can, refreshBadges, reload } from "../app.js";
import { timeChart } from "../chart.js";
import * as f from "../fmt.js";
import { bar, busy, emptyState, fieldErrors, html, raw, render, setDirty, toast } from "../ui.js";
import { bindTugas, tugasList } from "./tugas.js";

const STATUS = ["Diusulkan", "Diverifikasi", "Dilaksanakan", "Dievaluasi", "Ditolak", "Kedaluwarsa"];
const kode = (n) => `R-${String(n).padStart(3, "0")}`;
const chip = (s) => html`<span class="chip" data-s="${s}">${s}</span>`;

export default async function rekomendasi(ctx) {
  if (ctx.params[0]) return detail(ctx, ctx.params[0]);
  return daftar(ctx);
}

/* ------------------------------------------------------------------ daftar */
async function daftar({ main, query, user, isCurrent }) {
  const status = STATUS.includes(query.get("status")) ? query.get("status") : null;
  const d = await api(`/api/rekomendasi${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  if (!isCurrent()) return;
  const piket = user.peran === "piket";
  const total = Object.values(d.hitung).reduce((a, b) => a + b, 0);

  let tugasAktif = [];
  if (piket) {
    tugasAktif = d.baris.flatMap((r) => r.tugas.filter((t) => t.pelaksana.id === user.id && !t.selesai_pada && r.status === "Diverifikasi"));
  }

  const rows = d.baris.map((r) => html`<li><a class="rec-row" href="#/rekomendasi/${r.id}">
    <div>
      <span class="code">${kode(r.nomor)}</span>
      <h3>${r.judul}</h3>
      <div class="rec-meta">
        ${chip(r.status)}
        <span>${r.lokasi.split(" (")[0]}</span>
        <span>Anomali ${f.hari(r.anomali.mulai)} ${f.tgl(r.anomali.mulai)}, ${f.rentangJam(r.anomali.mulai, r.anomali.selesai)}</span>
        ${r.kejadian_berulang ? html`<span>Berulang ${r.kejadian_berulang}×</span>` : ""}
      </div>
    </div>
    <div class="rec-side">
      ${r.evaluasi
        ? html`<span class="num">${f.fix(r.evaluasi.hemat, 1)} kWh</span><span class="muted">hemat terukur</span>`
        : html`<span class="num">${f.fix(r.estimasi_hemat_kwh, 1)} kWh</span><span class="muted">estimasi hemat</span>`}
    </div>
  </a></li>`);

  const tabs = html`<nav class="tabs" aria-label="Filter status">
    <a href="#/rekomendasi" ${raw(!status ? 'aria-current="page"' : "")}>Semua <span class="n">${total}</span></a>
    ${STATUS.map((s) => html`<a href="#/rekomendasi?status=${encodeURIComponent(s)}" ${raw(status === s ? 'aria-current="page"' : "")}>${s} <span class="n">${d.hitung[s]}</span></a>`)}
  </nav>`;

  render(main, html`
    <div class="page-head">
      <div>
        <h1>${piket ? "Tugas dan rekomendasi" : "Rekomendasi"}</h1>
        <p>${piket ? "Tugas yang diberikan pengelola gedung kepadamu." : "Sistem mengusulkan, pengelola gedung memverifikasi. Status tidak bisa melompat."}</p>
      </div>
    </div>
    ${piket ? html`<section class="panel" aria-labelledby="h-aktif">
      <div class="panel-pad section-head flush"><h2 id="h-aktif">Tugas aktif</h2></div>
      ${tugasAktif.length ? tugasList(tugasAktif.map((t) => ({ ...t })), true)
        : emptyState("Tidak ada tugas aktif", "Tugas muncul setelah pengelola gedung memverifikasi rekomendasi dan menunjukmu sebagai pelaksana.")}
    </section>
    <div class="section"><h2>Riwayat tugas</h2></div>` : ""}
    ${!piket ? tabs : ""}
    <section class="panel ${piket ? "section-sm" : ""}" aria-label="Daftar rekomendasi">
      ${d.baris.length ? html`<ul class="list">${rows}</ul>` : status
        ? emptyState(`Tidak ada rekomendasi berstatus ${status}`, "Pilih status lain di atas untuk melihat rekomendasi lainnya.", '<a class="btn" href="#/rekomendasi">Tampilkan semua</a>')
        : emptyState("Belum ada rekomendasi", "Rekomendasi muncul setelah sistem menemukan pola tidak wajar, yaitu beban di atas prediksi selama 2 jam atau lebih.")}
    </section>`);
  if (piket) bindTugas(main, reload);
}

/* ------------------------------------------------------------------ detail */
async function detail({ main, user, isCurrent }, id) {
  const r = await api(`/api/rekomendasi/${encodeURIComponent(id)}`);
  if (!isCurrent()) return;
  document.title = `${kode(r.nomor)} ${r.judul} · SOLAR-EDU AI`;
  const urut = ["Diusulkan", "Diverifikasi", "Dilaksanakan", "Dievaluasi"];
  const pos = urut.indexOf(r.status);
  const berhenti = pos < 0;
  const steps = urut.map((s, i) => {
    let cls = "";
    if (!berhenti && i < pos) cls = "done";
    if (!berhenti && i === pos) cls = "now";
    if (berhenti) cls = i === 0 ? "done" : "off";
    return html`<li class="${cls}" ${raw(i === pos ? 'aria-current="step"' : "")}>${s}</li>`;
  });

  const an = r.anomali;
  const fitur = r.fitur_penting || [];
  const maxF = Math.max(...fitur.map((x) => x.bobot), 0.01);

  render(main, html`
    <p><a class="btn btn-ghost btn-sm" href="#/rekomendasi">← Semua rekomendasi</a></p>
    <div class="page-head">
      <div>
        <div class="row"><span class="code">${kode(r.nomor)}</span>${chip(r.status)}${r.kejadian_berulang ? html`<span class="chip chip-warn">Berulang ${r.kejadian_berulang}×</span>` : ""}</div>
        <h1 class="section-sm">${r.judul}</h1>
        <p>${r.lokasi}</p>
      </div>
    </div>
    <section class="panel panel-pad" aria-label="Tahap rekomendasi">
      <ol class="steps">${steps}</ol>
      ${berhenti ? html`<p class="body section-sm">${r.status === "Ditolak" ? `Ditolak: ${r.alasan_tolak}` : "Kedaluwarsa karena tidak direspons atau tidak dilaksanakan tepat waktu."}</p>` : ""}
    </section>

    <div class="split section">
      <div class="stack">
        <section class="panel panel-pad" aria-labelledby="h-alasan">
          <h2 id="h-alasan">Alasan</h2>
          <p class="section-sm">${r.alasan}</p>
          <div class="section">
            <div class="section-head"><h3>Aktual dan prediksi di sekitar anomali</h3>
              <div class="legend" aria-hidden="true"><span><i class="key key-act"></i>Aktual</span><span><i class="key key-pred"></i>Prediksi</span><span><i class="key key-crit"></i>Jam anomali</span></div></div>
            <div id="grafik-anom"></div>
          </div>
        </section>
        <section class="panel panel-pad" aria-labelledby="h-fitur">
          <h2 id="h-fitur">Fitur yang paling berpengaruh</h2>
          <p class="muted">Bobot kepentingan pada model aktif, beserta nilainya saat anomali dimulai.</p>
          <ul class="explain section-sm">${fitur.map((x) => html`<li><span>${x.label}${x.nilai ? html` <span class="muted">· ${x.nilai}</span>` : ""}</span>${bar(x.bobot, maxF, "pred")}</li>`)}</ul>
          <hr class="divider">
          <dl class="kv">
            <dt>Kelebihan energi</dt><dd>${f.fix(r.kelebihan_kwh, 1)} kWh (${an.aturan === "jadwal" ? "aturan jadwal" : "residu prediksi"})</dd>
            <dt>Peluang berulang</dt><dd>${f.pct(r.peluang_berulang * 100)}</dd>
            <dt>Estimasi hemat</dt><dd><b>${f.fix(r.estimasi_hemat_kwh, 1)} kWh</b></dd>
          </dl>
          <p class="formula section-sm">estimasi = ${f.fix(r.kelebihan_kwh, 1)} kWh × ${f.fix(r.peluang_berulang, 2)}</p>
        </section>
        <section class="panel panel-pad" aria-labelledby="h-riwayat">
          <h2 id="h-riwayat">Riwayat</h2>
          <ol class="timeline section-sm">${r.riwayat.map((h) => html`<li><div><b>${judulRiwayat(h)}</b>${catatanRiwayat(h) ? html`<p class="body">${catatanRiwayat(h)}</p>` : ""}<div class="when">${f.waktu(h.waktu)} WIB · ${h.oleh}</div></div></li>`)}</ol>
        </section>
      </div>
      <div class="stack" id="aksi"></div>
    </div>`);

  timeChart(main.querySelector("#grafik-anom"), {
    data: r.seri, unit: "kW", height: 200, markKey: "anomali",
    label: `Beban aktual dan prediksi ${f.tgl(an.mulai)}, anomali ${f.rentangJam(an.mulai, an.selesai)}, puncak ${f.fix(an.puncak_kw, 1)} kW di atas prediksi.`,
    xTick: (t, i, step) => (i % Math.max(step, 3) === 0 ? f.jam(t) : null),
    series: [
      { key: "prediksi", type: "line", cls: "l-pred", label: "Prediksi", keyCls: "key-pred", dot: "dot-pred" },
      { key: "aktual", type: "line", cls: "l-act", label: "Aktual", keyCls: "key-act", dot: "dot-act" },
    ],
  });
  await renderAksi(main.querySelector("#aksi"), r, user);
}

function judulRiwayat(h) {
  if (h.catatan === "pemantauan_selesai") return "Pemantauan 14 hari selesai";
  if (h.catatan.startsWith("kejadian_berulang")) return "Pola serupa terdeteksi lagi";
  if (!h.dari) return "Diusulkan oleh sistem";
  return `${h.dari} → ${h.ke}`;
}
function catatanRiwayat(h) {
  if (h.catatan === "pemantauan_selesai") return "";
  if (h.catatan.startsWith("kejadian_berulang:")) return `Anomali ${f.waktu(h.catatan.split(":").slice(1).join(":"))} WIB dicatat pada rekomendasi ini.`;
  return h.catatan === "Dibuat otomatis dari anomali." ? "" : h.catatan;
}

async function renderAksi(box, r, user) {
  const parts = [];
  const bisaVerif = can("rekomendasi.verifikasi");

  if (r.status === "Diusulkan" && bisaVerif) {
    const pelaksana = await api("/api/pelaksana");
    parts.push(html`<section class="panel panel-pad" aria-labelledby="h-putus">
      <h2 id="h-putus">Keputusan pengelola</h2>
      <p class="muted">Batas respons ${f.waktu(r.batas_respons)} WIB. Tanpa respons, rekomendasi menjadi Kedaluwarsa.</p>
      <form id="f-verif" class="stack section-sm" novalidate>
        <div class="field">
          <label for="pelaksana">Pelaksana</label>
          <select class="input" id="pelaksana" name="pelaksana_id" autocomplete="off">
            ${pelaksana.map((p) => html`<option value="${p.id}" ${raw(r.pelaksana_disarankan?.id === p.id ? "selected" : "")}>${p.nama} · ${p.tugas_aktif} tugas aktif${r.pelaksana_disarankan?.id === p.id ? " · disarankan" : ""}</option>`)}
          </select>
          <span class="err" data-for="pelaksana_id" hidden></span>
        </div>
        <div class="field">
          <label for="batas">Batas waktu pelaksanaan</label>
          <select class="input" id="batas" name="batas_jam" autocomplete="off">
            <option value="24">24 jam</option><option value="48" selected>48 jam</option><option value="72">3 hari</option><option value="168">7 hari</option>
          </select>
        </div>
        <div class="field">
          <label for="cat-verif">Catatan untuk pelaksana <span class="muted">(opsional)</span></label>
          <textarea class="input" id="cat-verif" name="catatan" autocomplete="off" placeholder="Contoh: cek juga lampu koridor lantai 2…"></textarea>
        </div>
        <button class="btn btn-primary" type="submit">Verifikasi rekomendasi</button>
      </form>
      <hr class="divider">
      <button class="btn btn-danger btn-block" type="button" id="buka-tolak" aria-expanded="false" aria-controls="f-tolak">Tolak rekomendasi…</button>
      <form id="f-tolak" class="stack section-sm" hidden novalidate>
        <fieldset class="field" aria-describedby="tolak-hint">
          <legend class="label">Alasan penolakan</legend>
          <p class="hint" id="tolak-hint">Alasan wajib diisi, dicatat di log audit, dan dipakai untuk mengkalibrasi ambang.</p>
          <div class="radio-list">
            ${["Ada kegiatan sah di luar jadwal kuliah", "Sudah dicek, tidak ada peralatan menyala", "Data meter tidak wajar atau rusak", "Lainnya"].map((a, i) => html`<label class="check"><input type="radio" name="pilihan" value="${a}" ${raw(i === 0 ? "checked" : "")}><span>${a}</span></label>`)}
          </div>
        </fieldset>
        <div class="field">
          <label for="alasan">Keterangan</label>
          <textarea class="input" id="alasan" name="alasan" autocomplete="off" placeholder="Contoh: seminar fakultas di aula pukul 08.00–16.00…"></textarea>
          <span class="err" data-for="alasan" hidden></span>
        </div>
        <div class="row row-end">
          <button class="btn" type="button" id="batal-tolak">Batal</button>
          <button class="btn btn-danger-solid" type="submit">Tolak dengan alasan ini</button>
        </div>
      </form>
    </section>`);
  }

  if (r.status === "Diverifikasi") {
    const milikku = r.tugas.filter((t) => !t.selesai_pada && (t.pelaksana.id === user.id || can("rekomendasi.verifikasi")));
    parts.push(html`<section class="panel" aria-labelledby="h-tugas">
      <div class="panel-pad section-head flush"><div><h2 id="h-tugas">Tugas pelaksanaan</h2><p>Diverifikasi ${r.diverifikasi_oleh} · ${f.waktu(r.diverifikasi_pada)} WIB</p></div></div>
      ${milikku.length && can("tugas.tandai") ? tugasList(milikku, user.peran === "piket") : html`<div class="panel-pad"><dl class="kv">${r.tugas.map((t) => html`<dt>${t.pelaksana.nama}</dt><dd>batas ${f.waktu(t.batas_waktu)} WIB${t.terlambat ? " · terlambat" : ""}</dd>`)}</dl></div>`}
    </section>`);
  }

  if (r.status === "Dilaksanakan") {
    const mulai = f.d(r.dilaksanakan_pada), akhir = f.d(r.pemantauan_selesai);
    const hari = Math.min(14, Math.max(0, Math.floor((Date.now() - mulai) / 86400000)));
    const ev = r.evaluasi_pratinjau;
    parts.push(html`<section class="panel panel-pad" aria-labelledby="h-pantau">
      <h2 id="h-pantau">Pemantauan 14 hari</h2>
      <p class="muted">Dilaksanakan ${f.waktu(r.dilaksanakan_pada)} WIB · selesai ${f.waktu(r.pemantauan_selesai)} WIB</p>
      <div class="section-sm">${bar(hari, 14, "pv")}</div>
      <p class="body section-sm">${r.siap_evaluasi ? "Pemantauan selesai. Konsumsi sebelum dan sesudah sudah terisi otomatis." : `Hari ke-${hari} dari 14. Evaluasi bisa dicatat setelah ${f.tgl(akhir)}.`}</p>
      ${r.tugas.map((t) => t.catatan_bukti ? html`<p class="muted section-sm">Bukti dari ${t.pelaksana.nama}: “${t.catatan_bukti}”</p>` : "")}
      ${ev ? evalTable(ev, !r.siap_evaluasi) : ""}
      ${r.siap_evaluasi && can("evaluasi.catat") ? html`<form id="f-eval" class="stack section" novalidate>
        <div class="field"><label for="cat-eval">Catatan evaluasi <span class="muted">(opsional)</span></label>
          <textarea class="input" id="cat-eval" name="catatan" autocomplete="off" placeholder="Contoh: AC lantai 2 sudah rutin dimatikan setelah kelas terakhir…"></textarea></div>
        <button class="btn btn-primary" type="submit">Catat hasil</button>
      </form>` : ""}
    </section>`);
  }

  if (r.evaluasi) {
    parts.push(html`<section class="panel panel-pad" aria-labelledby="h-hasil">
      <h2 id="h-hasil">Hasil evaluasi</h2>
      <p class="muted">Dicatat ${f.waktu(r.evaluasi.waktu)} WIB</p>
      ${evalTable({ konsumsi_sebelum_kwh: r.evaluasi.sebelum, konsumsi_sesudah_kwh: r.evaluasi.sesudah, pembanding_sebelum_kwh: r.evaluasi.pembanding_sebelum, pembanding_sesudah_kwh: r.evaluasi.pembanding_sesudah, hemat_kwh: r.evaluasi.hemat }, false)}
      ${r.evaluasi.catatan ? html`<p class="body section-sm">${r.evaluasi.catatan}</p>` : ""}
    </section>`);
  }

  if (!parts.length) {
    parts.push(html`<section class="panel panel-pad"><h2>Status</h2><p class="body section-sm">${
      r.status === "Diusulkan" ? "Menunggu verifikasi pengelola gedung." :
      r.status === "Ditolak" ? "Rekomendasi ini ditolak. Alasannya dipakai untuk mengkalibrasi ambang deteksi." :
      r.status === "Kedaluwarsa" ? "Rekomendasi ini kedaluwarsa. Bila pola muncul lagi, sistem membuat rekomendasi baru." :
      "Tidak ada aksi untuk peran ini."}</p></section>`);
  }
  render(box, html`${parts}`);
  bindAksi(box, r);
}

function evalTable(ev, sementara) {
  const pct = ev.konsumsi_sebelum_kwh ? (ev.hemat_kwh / ev.konsumsi_sebelum_kwh) * 100 : null;
  return html`<div class="table-wrap section-sm"><table>
    <caption class="sr">Perbandingan konsumsi 14 hari sebelum dan sesudah tindakan</caption>
    <thead><tr><th scope="col">14 hari</th><th scope="col" class="n">Sebelum</th><th scope="col" class="n">Sesudah</th></tr></thead>
    <tbody>
      <tr><th scope="row">Panel percontohan</th><td class="n">${f.num(ev.konsumsi_sebelum_kwh, 0)} kWh</td><td class="n">${f.num(ev.konsumsi_sesudah_kwh, 0)} kWh</td></tr>
      <tr><th scope="row">Gedung pembanding</th><td class="n">${f.num(ev.pembanding_sebelum_kwh, 0)} kWh</td><td class="n">${f.num(ev.pembanding_sesudah_kwh, 0)} kWh</td></tr>
    </tbody></table></div>
    <p class="section-sm"><b class="num">${f.fix(ev.hemat_kwh, 1)} kWh</b> ${sementara ? "perkiraan sementara" : "hemat terukur"}${pct !== null ? ` (${f.pct(pct, 1)})` : ""}, selisih-dalam-selisih terhadap gedung pembanding.</p>`;
}

function bindAksi(box, r) {
  const fv = box.querySelector("#f-verif");
  if (fv) {
    fv.addEventListener("input", () => setDirty(true));
    fv.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { pelaksana_id: fv.elements.pelaksana_id.value, batas_jam: Number(fv.elements.batas_jam.value), catatan: fv.elements.catatan.value.trim() };
      try {
        await busy(fv.querySelector('[type="submit"]'), "Memverifikasi…", () => api(`/api/rekomendasi/${r.id}/verifikasi`, { method: "POST", body }));
        setDirty(false);
        toast("Rekomendasi diverifikasi. Tugas dikirim ke pelaksana.");
        refreshBadges(); reload();
      } catch (ex) { fieldErrors(fv, ex.kolom && Object.keys(ex.kolom).length ? ex.kolom : { pelaksana_id: ex.message }); }
    });
    const ft = box.querySelector("#f-tolak");
    const buka = box.querySelector("#buka-tolak");
    buka.addEventListener("click", () => { ft.hidden = false; buka.hidden = true; buka.setAttribute("aria-expanded", "true"); ft.querySelector("input[type=radio]").focus(); });
    box.querySelector("#batal-tolak").addEventListener("click", () => { ft.hidden = true; buka.hidden = false; buka.setAttribute("aria-expanded", "false"); buka.focus(); });
    ft.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pilihan = ft.elements.pilihan.value;
      const ket = ft.elements.alasan.value.trim();
      if (pilihan === "Lainnya" && ket.length < 5) return fieldErrors(ft, { alasan: "Tulis alasan penolakan, minimal 5 karakter." });
      const alasan = pilihan === "Lainnya" ? ket : ket ? `${pilihan}. ${ket}` : pilihan;
      try {
        await busy(ft.querySelector('[type="submit"]'), "Menolak…", () => api(`/api/rekomendasi/${r.id}/tolak`, { method: "POST", body: { alasan } }));
        setDirty(false);
        toast("Rekomendasi ditolak. Alasan tercatat di log audit.");
        refreshBadges(); reload();
      } catch (ex) { fieldErrors(ft, { alasan: ex.message }); }
    });
  }
  bindTugas(box, reload);
  const fe = box.querySelector("#f-eval");
  if (fe) fe.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await busy(fe.querySelector('[type="submit"]'), "Menyimpan…", () => api(`/api/rekomendasi/${r.id}/evaluasi`, { method: "POST", body: { catatan: fe.elements.catatan.value.trim() } }));
      toast("Hasil evaluasi dicatat dan masuk laporan semester.");
      reload();
    } catch (ex) { toast(ex.message, "err"); }
  });
}
