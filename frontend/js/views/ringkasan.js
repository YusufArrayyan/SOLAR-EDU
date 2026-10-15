import { api } from "../api.js";
import { timeChart } from "../chart.js";
import * as f from "../fmt.js";
import { html, render } from "../ui.js";
import { reload } from "../app.js";
import { tugasList, bindTugas } from "./tugas.js";

export default async function ringkasan({ main, user, isCurrent }) {
  const d = await api("/api/ringkasan");
  if (!isCurrent()) return;
  document.getElementById("gedung-nama").textContent = d.gedung.nama;
  const a = d.angka;
  const piket = user.peran === "piket";

  const selisih = (akt, pred) => {
    if (akt === null || pred === null || !pred) return "";
    const p = ((akt - pred) / pred) * 100;
    if (Math.abs(p) < 3) return "sesuai prediksi";
    return `${p > 0 ? "+" : "−"}${f.num(Math.abs(p), 0)} % dari prediksi ${f.fix(pred, 1)}`;
  };

  const peringatan = d.peringatan.map((p) => html`
    <div class="alert">
      <span class="alert-tag ${p.berlangsung ? "live" : ""}">${p.berlangsung ? "Anomali berlangsung" : "Anomali"}</span>
      <div class="alert-text">
        <b>Beban ${f.fix(p.puncak_kw, 1)} kW di atas prediksi · ${p.lokasi}</b>
        <p>${f.hari(p.mulai)} ${f.rentangJam(p.mulai, p.selesai)} WIB · kelebihan ${f.fix(p.kelebihan_kwh, 1)} kWh · ${p.ruang_terjadwal ? `${p.ruang_terjadwal} ruang terjadwal` : "tidak ada kelas terjadwal"}</p>
      </div>
      ${p.rekomendasi && !piket ? html`<a class="btn btn-sm" href="#/rekomendasi/${p.rekomendasi.id}">${p.rekomendasi.status === "Diusulkan" ? "Tinjau rekomendasi" : `Lihat R-${String(p.rekomendasi.nomor).padStart(3, "0")}`}</a>` : ""}
    </div>`);
  const diam = d.data_diam.map((p) => html`
    <div class="alert alert-info">
      <span class="alert-tag">Data terputus</span>
      <div class="alert-text"><b>Data ${p.nama} belum masuk${p.terakhir ? ` sejak ${f.jam(p.terakhir)}` : ""}</b><p>Cek koneksi gateway, lalu muat ulang halaman ini.</p></div>
    </div>`);

  const fig4 = piket
    ? html`<div class="fig"><a href="#/rekomendasi"><div class="fig-label">Tugas aktif kamu</div><div class="fig-val">${a.tugas_aktif}</div><div class="fig-sub">${a.tugas_aktif ? "Lihat daftar tugas" : "Tidak ada tugas saat ini"}</div></a></div>`
    : html`<div class="fig"><a href="#/rekomendasi?status=Diusulkan"><div class="fig-label">Menunggu verifikasi</div><div class="fig-val">${a.rekomendasi_menunggu}<small>rekomendasi</small></div><div class="fig-sub">${a.rekomendasi_menunggu ? "Kedaluwarsa bila 7 hari tanpa respons" : "Tidak ada yang menunggu"}</div></a></div>`;

  const pb = d.prediksi_besok;
  render(main, html`
    <div class="page-head">
      <div>
        <h1>Ringkasan</h1>
        <p>${f.tglPanjang(d.waktu)} · ${a.beban_kini_jam ? `data terakhir ${f.jam(a.beban_kini_jam)} WIB` : "belum ada data hari ini"}</p>
      </div>
    </div>

    ${d.peringatan.length || d.data_diam.length
      ? html`<section class="alerts" aria-label="Peringatan">${peringatan}${diam}</section>`
      : html`<section class="alerts" aria-label="Peringatan"><div class="alert alert-calm"><span class="alert-tag">Normal</span><div class="alert-text"><b>Tidak ada anomali dalam 48 jam terakhir.</b><p>Beban gedung masih dalam rentang prediksi.</p></div></div></section>`}

    ${d.tugas_saya.length ? html`<section class="panel" aria-labelledby="h-tugas">
      <div class="panel-pad section-head flush"><h2 id="h-tugas">${piket ? "Tugas kamu hari ini" : "Tugas saya"}</h2></div>
      ${tugasList(d.tugas_saya, piket)}
    </section>` : ""}

    <section class="panel figs ${d.tugas_saya.length ? "section-gap" : ""}" aria-label="Angka utama">
      <div class="fig">
        <div class="fig-label">Beban sekarang</div>
        <div class="fig-val">${f.fix(a.beban_kini_kw, 1)}<small>kW</small></div>
        <div class="fig-sub">${selisih(a.beban_kini_kw, a.beban_kini_prediksi) || "–"}</div>
      </div>
      <div class="fig">
        <div class="fig-label">Konsumsi hari ini</div>
        <div class="fig-val">${f.num(a.kwh_hari_ini, 0)}<small>kWh</small></div>
        <div class="fig-sub">${selisih(a.kwh_hari_ini, a.kwh_prediksi_hari_ini) || "–"}</div>
      </div>
      <div class="fig">
        <div class="fig-label"><i class="key key-pv" aria-hidden="true"></i>Produksi surya hari ini</div>
        <div class="fig-val">${f.num(a.pv_kwh_hari_ini, 0)}<small>kWh</small></div>
        <div class="fig-sub">${a.pv_porsi !== null ? `${f.pct(a.pv_porsi)} dari konsumsi` : "–"}</div>
      </div>
      ${fig4}
    </section>

    <section class="panel panel-pad section" aria-labelledby="h-grafik">
      <div class="section-head">
        <div><h2 id="h-grafik">Beban dan produksi surya</h2><p>48 jam terakhir dan prediksi 24 jam ke depan</p></div>
        <div class="legend" aria-hidden="true">
          <span><i class="key key-act"></i>Beban aktual</span>
          <span><i class="key key-pred"></i>Prediksi</span>
          <span><i class="key key-band"></i>Rentang 10–90 %</span>
          <span><i class="key key-pv"></i>Produksi surya</span>
          <span><i class="key key-crit"></i>Anomali</span>
        </div>
      </div>
      <div id="grafik"></div>
      <p class="chart-help">Fokus pada grafik lalu tekan panah kiri atau kanan untuk membaca nilai per jam.</p>
    </section>

    <div class="grid-2 section">
      <section class="panel panel-pad" aria-labelledby="h-besok">
        <h2 id="h-besok">Prediksi besok</h2>
        ${pb ? html`
          <p class="muted">${f.hariPanjang(pb.tanggal)}, ${f.tgl(pb.tanggal)}</p>
          <div class="fig-val num">${f.num(pb.kwh, 0)}<small>kWh</small></div>
          <p class="body">Rentang ${f.num(pb.kwh_bawah, 0)}–${f.num(pb.kwh_atas, 0)} kWh. Puncak ${f.fix(pb.puncak_kw, 1)} kW sekitar pukul ${f.jam(pb.puncak_jam)}.</p>
          <hr class="divider">
          <dl class="kv">
            <dt>Produksi surya</dt><dd>${f.num(pb.pv_kwh, 0)} kWh</dd>
            <dt>Jam surya terbaik</dt><dd>${pb.jendela_surya ? `${f.rentangJam(pb.jendela_surya[0], pb.jendela_surya[1])} WIB` : "Produksi rendah"}</dd>
          </dl>
          ${pb.jendela_surya ? html`<p class="body section-sm">Jadwalkan beban fleksibel seperti pompa air, pengisian daya laptop lab, atau pembersihan ruang server pada ${f.rentangJam(pb.jendela_surya[0], pb.jendela_surya[1])} agar memakai listrik surya langsung.</p>` : ""}
        ` : html`<p class="body">Prediksi besok belum tersedia. Prediksi dibuat setiap hari sebelum pukul 03.00 WIB.</p>`}
      </section>
      <section class="panel panel-pad" aria-labelledby="h-data">
        <h2 id="h-data">Kualitas data dan model</h2>
        <dl class="kv section-sm">
          <dt>Kelengkapan hari ini</dt><dd>${d.kelengkapan_hari_ini !== null ? f.pct(d.kelengkapan_hari_ini, 1) : "–"}</dd>
          <dt>Model aktif</dt><dd>${d.model ? `Random Forest, dilatih ${f.tglTahun(d.model.tanggal_latih)}` : "Belum ada model"}</dd>
          <dt>Akurasi (MAPE)</dt><dd>${d.model ? html`${f.pct(d.model.mape, 1)} <span class="muted">target ≤ 15 %</span>` : "–"}</dd>
          <dt>Galat rata-rata</dt><dd>${d.model ? `${f.fix(d.model.mae, 2)} kW` : "–"}</dd>
        </dl>
        <p class="muted section-sm">Rekomendasi adalah hipotesis. Model tidak mengetahui penyebab; pengelola gedung memeriksa sebelum tindakan dijalankan.</p>
      </section>
    </div>`);

  bindTugas(main, reload);

  const seri = d.seri;
  const chart = timeChart(main.querySelector("#grafik"), {
    data: seri,
    label: `Grafik beban gedung dan produksi surya per jam, ${seri.length} jam. ${d.peringatan.length} anomali dalam 48 jam terakhir.`,
    unit: "kW",
    height: 280,
    now: d.waktu,
    markKey: "anomali",
    startIndex: seri.findIndex((r) => f.d(r.t) > f.d(d.waktu)) - 1,
    xTick: (t, i, step) => {
      const h = f.d(t).getUTCHours() + 7;
      const jam = h % 24;
      if (jam === 0) return f.tgl(t);
      return jam % (step > 6 ? 12 : 6) === 0 ? f.jam(t) : null;
    },
    series: [
      { key: "pv", type: "area", cls: "a-pv", label: "Produksi surya", keyCls: "key-pv" },
      { key: "pv_prediksi", type: "line", cls: "a-pvpred", label: "Prediksi surya", keyCls: "key-pv" },
      { key: "atas", lo: "bawah", hi: "atas", type: "band", label: "Rentang 10–90 %", keyCls: "key-band" },
      { key: "prediksi", type: "line", cls: "l-pred", label: "Prediksi beban", keyCls: "key-pred", dot: "dot-pred" },
      { key: "aktual", type: "line", cls: "l-act", label: "Beban aktual", keyCls: "key-act", dot: "dot-act" },
    ],
  });
  // segarkan tiap 5 menit
  const timer = setInterval(() => {
    const ae = document.activeElement;
    if (!isCurrent() || document.hidden || (main.contains(ae) && ae.matches("textarea, input"))) return;
    reload();
  }, 300000);
  return () => { chart.destroy(); clearInterval(timer); };
}
