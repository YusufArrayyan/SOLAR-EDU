import { api } from "../api.js";
import { timeChart } from "../chart.js";
import * as f from "../fmt.js";
import { fieldErrors, html, render } from "../ui.js";

export default async function dampak({ main, isCurrent }) {
  const d = await api("/api/dampak");
  if (!isCurrent()) return;
  const hariIni = new Date();
  const iso = (x) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(x);
  const awalSemester = new Date(hariIni.getTime() - 120 * 86400000);

  render(main, html`
    <div class="page-head">
      <div><h1>Dampak</h1><p>Hasil terukur dari tindakan yang sudah dievaluasi. Target persentase penghematan baru ditetapkan setelah baseline Fase 1.</p></div>
    </div>

    <section class="panel figs" aria-label="Angka dampak">
      <div class="fig"><div class="fig-label">Hemat terukur</div><div class="fig-val">${f.num(d.hemat_terukur_kwh, 0)}<small>kWh</small></div><div class="fig-sub">dari ${d.jumlah_evaluasi} tindakan yang dievaluasi</div></div>
      <div class="fig"><div class="fig-label">Biaya terhindarkan</div><div class="fig-val">${f.rupiah(d.hemat_rp)}</div><div class="fig-sub">tarif ${f.rupiah(d.tarif)}/kWh</div></div>
      <div class="fig"><div class="fig-label">Emisi terhindarkan</div><div class="fig-val">${f.num(d.emisi_terhindar_kg, 0)}<small>kg CO₂e</small></div><div class="fig-sub">faktor ${f.fix(d.faktor_emisi, 2)} kg/kWh</div></div>
      <div class="fig"><div class="fig-label"><i class="key key-pv" aria-hidden="true"></i>Listrik surya terpakai</div><div class="fig-val">${f.num(d.pv_swakonsumsi_kwh, 0)}<small>kWh</small></div><div class="fig-sub">${f.num(d.pv_emisi_terhindar_kg / 1000, 1)} t CO₂e · sejak ${f.tglTahun(d.baseline.mulai)}</div></div>
    </section>

    <section class="panel panel-pad section" aria-labelledby="h-harian">
      <div class="section-head">
        <div><h2 id="h-harian">Konsumsi harian dan baseline</h2><p>60 hari terakhir. Baseline = rerata hari yang sama selama Fase 1 (${f.tglTahun(d.baseline.mulai)}–${f.tglTahun(d.baseline.selesai)}).</p></div>
        <div class="legend" aria-hidden="true"><span><i class="key key-bar"></i>Konsumsi</span><span><i class="key key-base"></i>Baseline</span><span><i class="key key-pv"></i>Produksi surya</span></div>
      </div>
      <div id="grafik-harian"></div>
      <dl class="kv section-sm">
        <dt>Rerata baseline</dt><dd>${f.num(d.baseline.rerata_harian_kwh, 0)} kWh/hari</dd>
        <dt>Rerata masa pilot</dt><dd>${f.num(d.pilot.rerata_harian_kwh, 0)} kWh/hari selama ${d.pilot.hari} hari</dd>
      </dl>
      <p class="muted section-sm">Selisih rerata belum dikoreksi cuaca dan jadwal, jadi bukan klaim penghematan. Angka hemat terukur memakai selisih-dalam-selisih terhadap gedung pembanding per tindakan.</p>
    </section>

    <section class="section" aria-labelledby="h-eval">
      <div class="section-head"><h2 id="h-eval">Evaluasi per tindakan</h2><p>Jendela 14 hari sebelum dan sesudah tindakan</p></div>
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Rekomendasi</th><th scope="col" class="n">Sebelum</th><th scope="col" class="n">Sesudah</th><th scope="col" class="n">Pembanding</th><th scope="col" class="n">Hemat</th></tr></thead>
        <tbody>${d.evaluasi.length ? d.evaluasi.map((e) => html`<tr>
          <th scope="row"><a href="#/rekomendasi/${e.rekomendasi_id}">R-${String(e.nomor).padStart(3, "0")} ${e.judul}</a><span class="sub">dicatat ${f.tglTahun(e.waktu)}</span></th>
          <td class="n">${f.num(e.sebelum, 0)} kWh</td><td class="n">${f.num(e.sesudah, 0)} kWh</td>
          <td class="n">${f.num(e.pembanding_sebelum, 0)} → ${f.num(e.pembanding_sesudah, 0)}</td>
          <td class="n"><b>${f.fix(e.hemat, 1)} kWh</b></td></tr>`)
          : html`<tr><td colspan="5" class="muted">Belum ada tindakan yang dievaluasi. Evaluasi dicatat setelah pemantauan 14 hari selesai.</td></tr>`}</tbody>
      </table></div>
    </section>

    <section class="section" aria-labelledby="h-ind">
      <div class="section-head"><h2 id="h-ind">Indikator keberhasilan</h2><p>Target awal, dikaji ulang setelah tiga bulan data pertama</p></div>
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Indikator</th><th scope="col" class="n">Nilai</th><th scope="col">Target</th><th scope="col">Status</th></tr></thead>
        <tbody>${d.indikator.map((i) => html`<tr>
          <th scope="row">${i.nama}<span class="sub">${i.cara}</span></th>
          <td class="n">${i.nilai === null ? "–" : `${f.num(i.nilai, 1)} ${i.satuan}`}</td>
          <td>${i.target}</td>
          <td>${i.status === null ? html`<span class="chip chip-plain">Belum ada data</span>` : i.status === "tercapai" ? html`<span class="chip chip-good">Tercapai</span>` : html`<span class="chip chip-warn">Belum tercapai</span>`}</td>
        </tr>`)}</tbody>
      </table></div>
    </section>

    <section class="panel panel-pad section" aria-labelledby="h-lap">
      <h2 id="h-lap">Laporan CSV</h2>
      <p class="muted">Konsumsi, produksi surya, anomali, dan hasil evaluasi per hari. Pemisah titik koma, bisa dibuka di spreadsheet.</p>
      <form id="f-lap" class="row section-sm" novalidate>
        <div class="field"><label for="lap-mulai">Dari</label><input class="input" type="date" id="lap-mulai" name="mulai" value="${iso(awalSemester)}" autocomplete="off" required></div>
        <div class="field"><label for="lap-selesai">Sampai</label><input class="input" type="date" id="lap-selesai" name="selesai" value="${iso(hariIni)}" autocomplete="off" required></div>
        <button class="btn btn-primary align-end" type="submit">Unduh laporan</button>
        <span class="err" data-for="selesai" hidden></span>
      </form>
    </section>`);

  const seri = d.seri;
  const chart = timeChart(main.querySelector("#grafik-harian"), {
    data: seri.map((r) => ({ ...r, t: r.tanggal })), unit: "kWh", height: 260, bars: true,
    label: `Konsumsi harian 60 hari terakhir dibanding baseline. Rerata baseline ${f.num(d.baseline.rerata_harian_kwh, 0)} kWh per hari.`,
    xRead: (t) => `${f.hari(t)}, ${f.tglTahun(t)}`,
    xTick: (t, i, step) => (i % Math.max(step, 7) === 0 ? f.tgl(t) : null),
    series: [
      { key: "kwh", type: "bar", label: "Konsumsi", keyCls: "key-bar", unit: "kWh" },
      { key: "pv", type: "line", cls: "a-pvpred", label: "Produksi surya", keyCls: "key-pv", unit: "kWh" },
      { key: "baseline", type: "line", cls: "l-base", label: "Baseline", keyCls: "key-base", unit: "kWh", dot: "dot-base" },
    ],
  });

  const form = main.querySelector("#f-lap");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const a = form.elements.mulai.value, b = form.elements.selesai.value;
    if (!a || !b) return fieldErrors(form, { selesai: "Isi kedua tanggal." });
    if (b < a) return fieldErrors(form, { selesai: "Tanggal akhir harus sama atau setelah tanggal awal." });
    fieldErrors(form, {});
    window.location.href = `/api/laporan.csv?mulai=${a}&selesai=${b}`;
  });
  return () => chart.destroy();
}
