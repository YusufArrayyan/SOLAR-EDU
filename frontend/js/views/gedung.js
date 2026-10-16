// Pengaturan > Gedung: data gedung, perangkat, ruang, gedung lain, dan konsumsi bulanan.
import { api } from "../api.js";
import { go } from "../app.js";
import * as f from "../fmt.js";
import { busy, fieldErrors, html, raw, render, setDirty, toast } from "../ui.js";

const PERAN_GEDUNG = { percontohan: "Gedung percontohan", pembanding: "Gedung pembanding", lain: "Gedung lain (papan peringkat)" };
const muatUlang = () => go("#/pengaturan?tab=gedung");

function statusPerangkat(p) {
  if (!p.terakhir_lapor) return html`<span class="chip chip-plain">Belum lapor</span>`;
  const aktif = Date.now() - f.d(p.terakhir_lapor) <= 2 * 3600e3;
  return html`${aktif ? html`<span class="chip chip-good">Aktif</span>` : html`<span class="chip chip-warn">Diam</span>`}<span class="sub muted">${f.relatif(p.terakhir_lapor)}</span>`;
}

function formGedung(g, fungsi) {
  return html`<form class="grid-form" data-gedung="${g.id}" novalidate>
    <div class="field"><label for="n-${g.id}">Nama</label><input class="input" id="n-${g.id}" name="nama" value="${g.nama}" autocomplete="off"><span class="err" data-for="nama" hidden></span></div>
    <div class="field"><label for="f-${g.id}">Fungsi</label><select class="input" id="f-${g.id}" name="fungsi" autocomplete="off">${fungsi.map((k) => html`<option value="${k}" ${raw(k === g.fungsi ? "selected" : "")}>${f.fungsiGedung(k)}</option>`)}</select><span class="err" data-for="fungsi" hidden></span></div>
    <div class="field"><label for="l-${g.id}">Luas lantai</label><div class="input-unit"><input class="input" id="l-${g.id}" name="luas_m2" type="number" inputmode="decimal" min="50" step="any" value="${g.luas_m2}" autocomplete="off"><span>m²</span></div><span class="err" data-for="luas_m2" hidden></span></div>
    <div class="field"><label for="j-${g.id}">Jam operasional</label><div class="input-unit"><input class="input" id="j-${g.id}" name="jam_operasional_pekan" type="number" inputmode="decimal" min="1" max="168" step="any" value="${g.jam_operasional_pekan}" autocomplete="off"><span>jam/pekan</span></div><span class="err" data-for="jam_operasional_pekan" hidden></span></div>
    ${g.peran === "percontohan" ? html`<div class="field"><label for="p-${g.id}">Kapasitas panel surya</label><div class="input-unit"><input class="input" id="p-${g.id}" name="kapasitas_pv_kwp" type="number" inputmode="decimal" min="0" step="any" value="${g.kapasitas_pv_kwp}" autocomplete="off"><span>kWp</span></div><span class="err" data-for="kapasitas_pv_kwp" hidden></span></div>` : ""}
    <div class="row row-end span-all"><button class="btn btn-primary" type="submit">Simpan data gedung</button></div>
  </form>`;
}

function tabelPerangkat(g, perangkat) {
  const milik = perangkat.filter((p) => p.gedung_id === g.id);
  return html`<div class="section">
    <div class="section-head"><h3>Perangkat</h3><p>Kode harus sama dengan topik MQTT <span class="mono">solar/&lt;kode&gt;</span> atau kolom <span class="mono">perangkat</span> di API.</p></div>
    ${milik.length ? html`<div class="table-wrap"><table>
      <thead><tr><th scope="col">Nama</th><th scope="col">Kode</th><th scope="col">Jenis</th><th scope="col" class="n">Batas fisik</th><th scope="col">Status</th><th scope="col"><span class="sr">Aksi</span></th></tr></thead>
      <tbody>${milik.map((p) => html`<tr data-perangkat="${p.id}">
        <th scope="row">${p.nama}<span class="sub muted">${p.protokol}</span></th>
        <td class="mono">${p.kode}</td><td>${p.jenis === "meter" ? "Meter" : "Inverter"}</td>
        <td class="n">${f.num(p.batas_fisik_kw, 0)} kW</td><td>${statusPerangkat(p)}</td>
        <td class="n"><div class="row row-end nowrap-row"><button class="btn btn-sm" type="button" data-ubah-perangkat>Ubah</button><button class="btn btn-sm btn-danger" type="button" data-hapus-perangkat>Hapus</button></div></td>
      </tr>`)}</tbody></table></div>` : html`<p class="body">Belum ada perangkat. Daftarkan meter per panel dan inverter supaya data bisa diterima.</p>`}
    <form class="grid-form section-sm" data-tambah-perangkat="${g.id}" novalidate>
      <div class="field"><label for="pk-${g.id}">Kode perangkat baru</label><input class="input mono" id="pk-${g.id}" name="kode" spellcheck="false" autocomplete="off" placeholder="fk-a/panel-l4…"><span class="err" data-for="kode" hidden></span></div>
      <div class="field"><label for="pn-${g.id}">Nama</label><input class="input" id="pn-${g.id}" name="nama" autocomplete="off" placeholder="Panel lantai 4…"><span class="err" data-for="nama" hidden></span></div>
      <div class="field"><label for="pj-${g.id}">Jenis</label><select class="input" id="pj-${g.id}" name="jenis" autocomplete="off"><option value="meter">Meter listrik</option>${g.peran === "percontohan" ? html`<option value="inverter">Inverter panel surya</option>` : ""}</select><span class="err" data-for="jenis" hidden></span></div>
      <div class="field"><label for="pb-${g.id}">Batas fisik</label><div class="input-unit"><input class="input" id="pb-${g.id}" name="batas_fisik_kw" type="number" inputmode="decimal" min="1" step="any" value="100" autocomplete="off"><span>kW</span></div><span class="hint">Nilai di atas batas ini dianggap lonjakan sensor.</span><span class="err" data-for="batas_fisik_kw" hidden></span></div>
      <div class="row row-end span-all"><button class="btn" type="submit">Tambah perangkat</button></div>
    </form>
  </div>`;
}

function tabelRuang(g, ruang, perangkat) {
  const meter = perangkat.filter((p) => p.gedung_id === g.id && p.jenis === "meter");
  const pilihan = (sel) => html`<option value="">Belum dipetakan</option>${meter.map((p) => html`<option value="${p.id}" ${raw(p.id === sel ? "selected" : "")}>${p.nama}</option>`)}`;
  return html`<div class="section">
    <div class="section-head"><h3>Ruang</h3><p>Nama ruang harus sama persis dengan kolom <span class="mono">ruang</span> di CSV jadwal. Panel dipakai untuk menunjuk lokasi rekomendasi.</p></div>
    ${ruang.length ? html`<div class="table-wrap"><table>
      <thead><tr><th scope="col">Ruang</th><th scope="col" class="n">Kapasitas</th><th scope="col">Panel pemasok</th><th scope="col" class="n">Sesi jadwal</th><th scope="col"><span class="sr">Aksi</span></th></tr></thead>
      <tbody>${ruang.map((r) => html`<tr data-ruang="${r.id}">
        <th scope="row">${r.nama}</th><td class="n">${r.kapasitas}</td>
        <td><label class="sr" for="rp-${r.id}">Panel pemasok ${r.nama}</label><select class="input input-auto" id="rp-${r.id}" name="perangkat_id" autocomplete="off">${pilihan(r.perangkat_id)}</select></td>
        <td class="n">${r.sesi_jadwal}</td>
        <td class="n"><button class="btn btn-sm btn-danger" type="button" data-hapus-ruang>Hapus</button></td>
      </tr>`)}</tbody></table></div>` : html`<p class="body">Belum ada ruang. Tambahkan ruang sebelum mengimpor jadwal kuliah.</p>`}
    <form class="grid-form section-sm" data-tambah-ruang="${g.id}" novalidate>
      <div class="field"><label for="rn-${g.id}">Nama ruang baru</label><input class="input" id="rn-${g.id}" name="nama" autocomplete="off" placeholder="A4.01…"><span class="err" data-for="nama" hidden></span></div>
      <div class="field"><label for="rk-${g.id}">Kapasitas</label><input class="input" id="rk-${g.id}" name="kapasitas" type="number" inputmode="numeric" min="1" value="40" autocomplete="off"><span class="err" data-for="kapasitas" hidden></span></div>
      <div class="field"><label for="rpn-${g.id}">Panel pemasok</label><select class="input" id="rpn-${g.id}" name="perangkat_id" autocomplete="off">${pilihan("")}</select><span class="err" data-for="perangkat_id" hidden></span></div>
      <div class="row row-end span-all"><button class="btn" type="submit">Tambah ruang</button></div>
    </form>
  </div>`;
}

function konsumsiBulanan(g, rows) {
  const kemarin = new Date(); kemarin.setDate(1); kemarin.setMonth(kemarin.getMonth() - 1);
  const bulanLalu = `${kemarin.getFullYear()}-${String(kemarin.getMonth() + 1).padStart(2, "0")}`;
  return html`<div class="section">
    <div class="section-head"><h3>Konsumsi bulanan</h3><p>Dari tagihan PLN atau meter utama kampus. Dipakai untuk indeks efisiensi di papan peringkat.</p></div>
    <form class="grid-form" data-konsumsi="${g.id}" novalidate>
      <div class="field"><label for="kb-${g.id}">Bulan</label><input class="input" id="kb-${g.id}" name="periode" type="month" value="${bulanLalu}" max="${bulanLalu}" autocomplete="off"><span class="err" data-for="periode" hidden></span></div>
      <div class="field"><label for="kk-${g.id}">Konsumsi</label><div class="input-unit"><input class="input" id="kk-${g.id}" name="kwh" type="number" inputmode="decimal" min="1" step="any" autocomplete="off" placeholder="12500…"><span>kWh</span></div><span class="err" data-for="kwh" hidden></span></div>
      <div class="field"><label for="ks-${g.id}">Sumber</label><input class="input" id="ks-${g.id}" name="sumber" value="tagihan PLN" autocomplete="off"></div>
      <div class="row row-end span-all"><button class="btn" type="submit">Simpan konsumsi</button></div>
    </form>
    ${rows.length ? html`<div class="table-wrap section-sm"><table>
      <thead><tr><th scope="col">Bulan</th><th scope="col" class="n">Konsumsi</th><th scope="col">Sumber</th><th scope="col" class="n">Indeks</th></tr></thead>
      <tbody>${rows.map((k) => html`<tr><td>${f.bulan(k.periode + "-01")}</td><td class="n">${f.num(k.kwh, 0)} kWh</td><td class="body">${k.sumber}</td><td class="n">${k.indeks === null ? "–" : f.fix(k.indeks, 1)}</td></tr>`)}</tbody>
    </table></div>` : html`<p class="muted section-sm">Belum ada data konsumsi.</p>`}
  </div>`;
}

export async function gedung(box, { isCurrent }) {
  const [d, perangkat, ruang] = await Promise.all([api("/api/gedung"), api("/api/perangkat"), api("/api/ruang")]);
  const lain = d.baris.filter((g) => g.peran === "lain");
  const konsumsi = Object.fromEntries(await Promise.all(lain.map(async (g) => [g.id, await api(`/api/gedung/${g.id}/konsumsi`)])));
  if (!isCurrent()) return;
  render(box, html`
    <p class="muted">Luas dan jam operasional dipakai untuk intensitas energi dan indeks efisiensi. Kapasitas panel surya dipakai untuk prediksi produksi.</p>
    <div class="stack section-sm">${d.baris.map((g) => html`<section class="panel panel-pad" aria-labelledby="g-${g.id}">
      <div class="section-head"><h2 id="g-${g.id}">${g.nama}</h2><div class="row"><span class="chip chip-plain">${PERAN_GEDUNG[g.peran] || g.peran}</span>${g.peran === "lain" ? html`<button class="btn btn-sm btn-danger" type="button" data-hapus-gedung="${g.id}">Hapus gedung</button>` : ""}</div></div>
      ${formGedung(g, d.fungsi)}
      ${g.peran !== "lain" ? tabelPerangkat(g, perangkat) : ""}
      ${g.peran === "percontohan" ? tabelRuang(g, ruang.filter((r) => r.gedung_id === g.id), perangkat) : ""}
      ${g.peran === "lain" ? konsumsiBulanan(g, konsumsi[g.id] || []) : ""}
    </section>`)}</div>
    <section class="panel panel-pad section" aria-labelledby="h-gedung-baru">
      <h2 id="h-gedung-baru">Tambah gedung lain</h2>
      <p class="muted">Gedung tanpa meter, untuk papan peringkat antargedung. Konsumsinya diisi per bulan.</p>
      <form class="grid-form section-sm" id="f-gedung-baru" novalidate>
        <div class="field"><label for="gb-nama">Nama gedung</label><input class="input" id="gb-nama" name="nama" autocomplete="off" placeholder="Perpustakaan Pusat…"><span class="err" data-for="nama" hidden></span></div>
        <div class="field"><label for="gb-fungsi">Fungsi</label><select class="input" id="gb-fungsi" name="fungsi" autocomplete="off">${d.fungsi.map((k) => html`<option value="${k}">${f.fungsiGedung(k)}</option>`)}</select><span class="err" data-for="fungsi" hidden></span></div>
        <div class="field"><label for="gb-luas">Luas lantai</label><div class="input-unit"><input class="input" id="gb-luas" name="luas_m2" type="number" inputmode="decimal" min="50" step="any" autocomplete="off" placeholder="3000…"><span>m²</span></div><span class="err" data-for="luas_m2" hidden></span></div>
        <div class="field"><label for="gb-jam">Jam operasional</label><div class="input-unit"><input class="input" id="gb-jam" name="jam_operasional_pekan" type="number" inputmode="decimal" min="1" max="168" step="any" value="60" autocomplete="off"><span>jam/pekan</span></div><span class="err" data-for="jam_operasional_pekan" hidden></span></div>
        <div class="row row-end span-all"><button class="btn btn-primary" type="submit">Tambah gedung</button></div>
      </form>
    </section>`);
  bind(box, perangkat);
}

const angka = (form, nama) => (form.elements[nama] && form.elements[nama].value !== "" ? Number(form.elements[nama].value) : undefined);

function kirim(form, label, fn, sukses) {
  form.addEventListener("input", () => setDirty(true));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await busy(form.querySelector('[type="submit"]'), label, fn);
      fieldErrors(form, {});
      setDirty(false);
      sukses(r);
    } catch (ex) { fieldErrors(form, ex.kolom); if (!Object.keys(ex.kolom || {}).length) toast(ex.message, "err"); }
  });
}

function bind(box, perangkat) {
  const perangkatById = Object.fromEntries(perangkat.map((p) => [p.id, p]));
  box.querySelectorAll("form[data-gedung]").forEach((form) => kirim(form, "Menyimpan…", () => api(`/api/gedung/${form.dataset.gedung}`, {
    method: "PATCH",
    body: { nama: form.elements.nama.value, fungsi: form.elements.fungsi.value, luas_m2: angka(form, "luas_m2"),
      jam_operasional_pekan: angka(form, "jam_operasional_pekan"), kapasitas_pv_kwp: angka(form, "kapasitas_pv_kwp") },
  }), (g) => {
    form.closest("section").querySelector("h2").textContent = g.nama;
    toast(g.berubah ? `${g.nama} disimpan dan dicatat di log audit.` : "Tidak ada perubahan.");
  }));

  box.querySelectorAll("form[data-tambah-perangkat]").forEach((form) => kirim(form, "Menambahkan…", () => api("/api/perangkat", {
    method: "POST",
    body: { gedung_id: form.dataset.tambahPerangkat, kode: form.elements.kode.value.trim(), nama: form.elements.nama.value.trim(),
      jenis: form.elements.jenis.value, batas_fisik_kw: angka(form, "batas_fisik_kw") },
  }), (p) => { toast(`${p.nama} terdaftar. Data dari kode ${p.kode} sekarang diterima.`); muatUlang(); }));

  box.querySelectorAll("tr[data-perangkat]").forEach((tr) => {
    const id = tr.dataset.perangkat;
    tr.querySelector("[data-hapus-perangkat]").addEventListener("click", async (e) => {
      const nama = tr.querySelector("th").firstChild.textContent;
      if (!confirm(`Hapus ${nama}? Perangkat yang sudah punya data tidak bisa dihapus.`)) return;
      try { await busy(e.currentTarget, "Menghapus…", () => api(`/api/perangkat/${id}`, { method: "DELETE" })); toast(`${nama} dihapus.`); muatUlang(); }
      catch (ex) { toast(ex.message, "err"); }
    });
    tr.querySelector("[data-ubah-perangkat]").addEventListener("click", (e) => {
      if (tr.nextElementSibling?.classList.contains("edit-row")) { tr.nextElementSibling.querySelector("input").focus(); return; }
      const tombol = e.currentTarget;
      const { nama, kode, batas_fisik_kw: batas } = perangkatById[id];
      const baris = document.createElement("tr");
      baris.className = "edit-row";
      render(baris, html`<td colspan="6"><form class="grid-form" novalidate>
        <div class="field"><label for="ue-n-${id}">Nama</label><input class="input" id="ue-n-${id}" name="nama" value="${nama}" autocomplete="off"><span class="err" data-for="nama" hidden></span></div>
        <div class="field"><label for="ue-k-${id}">Kode</label><input class="input mono" id="ue-k-${id}" name="kode" value="${kode}" spellcheck="false" autocomplete="off"><span class="hint">Ubah juga konfigurasi gateway bila kode diganti.</span><span class="err" data-for="kode" hidden></span></div>
        <div class="field"><label for="ue-b-${id}">Batas fisik</label><div class="input-unit"><input class="input" id="ue-b-${id}" name="batas_fisik_kw" type="number" inputmode="decimal" min="1" step="any" value="${batas}" autocomplete="off"><span>kW</span></div><span class="err" data-for="batas_fisik_kw" hidden></span></div>
        <div class="row row-end span-all"><button class="btn" type="button" data-batal>Batal</button><button class="btn btn-primary" type="submit">Simpan perangkat</button></div>
      </form></td>`);
      tr.after(baris);
      const form = baris.querySelector("form");
      const tutup = () => { baris.remove(); tombol.focus(); setDirty(false); };
      form.querySelector("[data-batal]").addEventListener("click", tutup);
      form.addEventListener("keydown", (ev) => { if (ev.key === "Escape") tutup(); });
      form.elements.nama.focus();
      kirim(form, "Menyimpan…", () => api(`/api/perangkat/${id}`, {
        method: "PATCH", body: { nama: form.elements.nama.value.trim(), kode: form.elements.kode.value.trim(), batas_fisik_kw: angka(form, "batas_fisik_kw") },
      }), (p) => { toast(p.berubah ? `${p.nama} disimpan.` : "Tidak ada perubahan."); muatUlang(); });
    });
  });

  box.querySelectorAll("form[data-tambah-ruang]").forEach((form) => kirim(form, "Menambahkan…", () => api("/api/ruang", {
    method: "POST",
    body: { gedung_id: form.dataset.tambahRuang, nama: form.elements.nama.value.trim(), kapasitas: angka(form, "kapasitas"),
      perangkat_id: form.elements.perangkat_id.value || null },
  }), (r) => { toast(`Ruang ${r.nama} ditambahkan.`); muatUlang(); }));

  box.querySelectorAll("tr[data-ruang]").forEach((tr) => {
    const id = tr.dataset.ruang;
    const nama = tr.querySelector("th").textContent;
    tr.querySelector("select").addEventListener("change", async (e) => {
      try { await api(`/api/ruang/${id}`, { method: "PATCH", body: { perangkat_id: e.target.value || null } }); toast(`Panel pemasok ${nama} disimpan.`); }
      catch (ex) { toast(ex.message, "err"); muatUlang(); }
    });
    tr.querySelector("[data-hapus-ruang]").addEventListener("click", async (e) => {
      if (!confirm(`Hapus ruang ${nama}?`)) return;
      try { await busy(e.currentTarget, "Menghapus…", () => api(`/api/ruang/${id}`, { method: "DELETE" })); toast(`Ruang ${nama} dihapus.`); muatUlang(); }
      catch (ex) { toast(ex.message, "err"); }
    });
  });

  box.querySelectorAll("form[data-konsumsi]").forEach((form) => kirim(form, "Menyimpan…", () => api(`/api/gedung/${form.dataset.konsumsi}/konsumsi`, {
    method: "PUT", body: { periode: form.elements.periode.value, kwh: angka(form, "kwh") ?? 0, sumber: form.elements.sumber.value },
  }), (r) => { toast(`Konsumsi ${f.bulan(r.periode + "-01")} disimpan. Indeks efisiensi ${f.fix(r.indeks, 1)}.`); muatUlang(); }));

  box.querySelectorAll("[data-hapus-gedung]").forEach((b) => b.addEventListener("click", async () => {
    const nama = b.closest("section").querySelector("h2").textContent;
    if (!confirm(`Hapus ${nama} beserta riwayat konsumsi dan skornya?`)) return;
    try { await busy(b, "Menghapus…", () => api(`/api/gedung/${b.dataset.hapusGedung}`, { method: "DELETE" })); toast(`${nama} dihapus.`); muatUlang(); }
    catch (ex) { toast(ex.message, "err"); }
  }));

  const fb = box.querySelector("#f-gedung-baru");
  kirim(fb, "Menambahkan…", () => api("/api/gedung", {
    method: "POST",
    body: { nama: fb.elements.nama.value.trim(), fungsi: fb.elements.fungsi.value, luas_m2: angka(fb, "luas_m2") ?? 0,
      jam_operasional_pekan: angka(fb, "jam_operasional_pekan") ?? 0 },
  }), (g) => { toast(`${g.nama} ditambahkan. Isi konsumsi bulanannya agar masuk papan peringkat.`); muatUlang(); });
}
