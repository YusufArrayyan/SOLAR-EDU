import { api } from "../api.js";
import * as f from "../fmt.js";
import { bar, busy, html, render, toast } from "../ui.js";

export default async function belajar({ main, isCurrent }) {
  const d = await api("/api/belajar");
  if (!isCurrent()) return;
  const aktif = d.model.find((m) => m.aktif);
  render(main, html`
    <div class="page-head">
      <div><h1>Pusat belajar</h1><p>Dataset agregat, modul praktikum, dan topik tugas akhir. Tidak ada data identitas penghuni gedung.</p></div>
    </div>

    <section class="panel panel-pad" aria-labelledby="h-data">
      <div class="section-head">
        <div><h2 id="h-data">Dataset per jam</h2><p>Gedung percontohan, agregat seluruh panel. Kolom sama dengan fitur model.</p></div>
        <div class="row">
          <label class="sr" for="hari">Rentang dataset</label>
          <select class="input input-auto" id="hari" name="hari" autocomplete="off">
            <option value="30">30 hari</option><option value="90" selected>90 hari</option><option value="365">Semua (maks. 365 hari)</option>
          </select>
          <button class="btn" type="button" id="salin">Salin CSV</button>
          <button class="btn btn-primary" type="button" id="unduh">Unduh CSV</button>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <caption class="sr">Contoh 12 baris terbaru dataset per jam</caption>
          <thead><tr><th scope="col">Waktu (WIB)</th><th scope="col" class="n">Beban kW</th><th scope="col" class="n">PV kW</th><th scope="col" class="n">Suhu °C</th><th scope="col" class="n">Radiasi W/m²</th><th scope="col" class="n">Ruang</th><th scope="col" class="n">Lengkap</th><th scope="col">Anomali</th></tr></thead>
          <tbody>${d.contoh.map((r) => html`<tr>
            <td class="mono">${f.tgl(r.waktu)} ${f.jam(r.waktu)}</td><td class="n">${f.fix(r.beban_kw, 2)}</td><td class="n">${f.fix(r.produksi_pv_kw, 2)}</td>
            <td class="n">${f.fix(r.suhu, 1)}</td><td class="n">${f.int(r.radiasi)}</td><td class="n">${r.ruang_terjadwal}</td><td class="n">${f.pct(r.kelengkapan * 100)}</td>
            <td>${r.anomali ? html`<span class="chip chip-crit">Anomali</span>` : ""}</td></tr>`)}</tbody>
        </table>
      </div>
      <details class="acc-plain section-sm">
        <summary>Kamus data</summary>
        <dl class="kv section-sm">${d.kamus.map((k) => html`<dt class="mono">${k.kolom}</dt><dd>${k.arti}</dd>`)}</dl>
      </details>
    </section>

    <section class="section" aria-labelledby="h-modul">
      <div class="section-head"><h2 id="h-modul">Modul praktikum</h2><p>Dipakai lintas program studi; tiap modul memakai data dari halaman ini.</p></div>
      <div class="panel">${d.modul.map((m) => html`<details class="acc">
        <summary><span class="code">${m.kode}</span><span><b>${m.judul}</b><span class="sub muted">${m.prodi} · ${m.durasi}</span></span></summary>
        <div class="acc-body"><p>${m.tujuan}</p><ol>${m.langkah.map((l) => html`<li>${l}</li>`)}</ol></div>
      </details>`)}</div>
    </section>

    <div class="grid-2 section">
      <section class="panel panel-pad" aria-labelledby="h-topik">
        <h2 id="h-topik">Topik tugas akhir</h2>
        <ul class="list section-sm">${d.topik.map((t) => html`<li class="list-pad"><b>${t.judul}</b><span class="sub muted">${t.prodi}</span></li>`)}</ul>
      </section>
      <section class="panel panel-pad" aria-labelledby="h-model">
        <h2 id="h-model">Model aktif</h2>
        ${aktif ? html`<p class="muted">Random Forest, 300 pohon, minimal 3 sampel per daun · dilatih ${f.tglTahun(aktif.tanggal_latih)}</p>
          <dl class="kv section-sm"><dt>MAPE</dt><dd>${f.pct(aktif.mape, 1)} pada ${f.int(aktif.jam_uji)} jam uji</dd><dt>MAE</dt><dd>${f.fix(aktif.mae, 2)} kW</dd><dt>Data latih</dt><dd>${f.int(aktif.jam_latih)} jam bersih</dd></dl>
          <h3 class="section-sm">Kepentingan fitur</h3>
          <ul class="explain section-sm">${aktif.fitur.map((x) => html`<li><span>${x.label} <span class="muted num">${f.pct(x.bobot * 100, 1)}</span></span>${bar(x.bobot, aktif.fitur[0].bobot, "pred")}</li>`)}</ul>` : html`<p class="body">Belum ada model aktif.</p>`}
      </section>
    </div>

    <section class="section" aria-labelledby="h-versi">
      <div class="section-head"><h2 id="h-versi">Riwayat versi model</h2><p>Latih ulang tiap Minggu 02.00 WIB. Model baru dipakai bila MAPE tidak lebih buruk dari 110 % model lama.</p></div>
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Tanggal latih</th><th scope="col" class="n">MAPE</th><th scope="col" class="n">MAE</th><th scope="col" class="n">Jam latih</th><th scope="col">Catatan</th></tr></thead>
        <tbody>${d.model.map((m) => html`<tr><td>${f.waktu(m.tanggal_latih)} ${m.aktif ? html`<span class="chip chip-good">Aktif</span>` : ""}</td>
          <td class="n">${f.pct(m.mape, 1)}</td><td class="n">${f.fix(m.mae, 2)} kW</td><td class="n">${f.int(m.jam_latih)}</td><td class="body">${m.catatan}</td></tr>`)}</tbody>
      </table></div>
    </section>`);

  const hari = main.querySelector("#hari");
  main.querySelector("#unduh").addEventListener("click", () => { window.location.href = `/api/dataset.csv?hari=${hari.value}`; });
  main.querySelector("#salin").addEventListener("click", async (e) => {
    try {
      await busy(e.currentTarget, "Menyalin…", async () => {
        const res = await fetch(`/api/dataset.csv?hari=${hari.value}`, { credentials: "same-origin" });
        if (!res.ok) throw new Error("Dataset gagal diambil. Coba lagi.");
        await navigator.clipboard.writeText(await res.text());
      });
      toast(`Dataset ${hari.selectedOptions[0].textContent} disalin ke papan klip.`);
    } catch (ex) { toast(ex.message || "Peramban menolak akses papan klip. Gunakan Unduh CSV.", "err"); }
  });
}
