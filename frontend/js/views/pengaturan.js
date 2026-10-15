import { api } from "../api.js";
import { go, user } from "../app.js";
import * as f from "../fmt.js";
import { busy, emptyState, fieldErrors, html, raw, render, setDirty, toast } from "../ui.js";

const TABS = [
  ["parameter", "Parameter"], ["gedung", "Gedung"], ["jadwal", "Jadwal kuliah"], ["pengguna", "Pengguna"], ["sistem", "Status sistem"], ["audit", "Log audit"],
];
const GRUP = { dampak: "Dampak dan peringkat", anomali: "Deteksi anomali", prediksi: "Prediksi", notifikasi: "Tugas dan notifikasi" };

export default async function pengaturan(ctx) {
  const tab = TABS.some(([k]) => k === ctx.query.get("tab")) ? ctx.query.get("tab") : "parameter";
  const head = html`
    <div class="page-head"><div><h1>Pengaturan</h1><p>Hanya tim pengelola. Setiap perubahan tercatat di log audit.</p></div></div>
    <nav class="tabs" aria-label="Bagian pengaturan">${TABS.map(([k, l]) => html`<a href="#/pengaturan?tab=${k}" ${raw(k === tab ? 'aria-current="page"' : "")}>${l}</a>`)}</nav>
    <div id="isi"></div>`;
  render(ctx.main, head);
  const box = ctx.main.querySelector("#isi");
  const fn = { parameter, gedung, jadwal, pengguna, sistem, audit }[tab];
  return fn(box, ctx);
}

/* ------------------------------------------------------------------ parameter */
async function parameter(box, { isCurrent }) {
  const d = await api("/api/pengaturan");
  if (!isCurrent()) return;
  const grup = {};
  for (const s of d.spesifikasi) (grup[s.grup] ||= []).push(s);
  const input = (s) => {
    const v = d.nilai[s.kunci];
    if (s.tipe === "bool") return html`<label class="check"><input type="checkbox" name="${s.kunci}" ${raw(v ? "checked" : "")}><span><b>${s.label}</b><span class="sub muted">${s.bantuan}</span></span></label>`;
    if (s.tipe === "json") return html`<fieldset class="field"><legend class="label">${s.label} <span class="muted">(${s.satuan})</span></legend><p class="hint">${s.bantuan}</p>
      <div class="grid-4">${Object.entries(v).map(([k, x]) => html`<div class="field"><label for="pf-${k}">${k[0].toUpperCase() + k.slice(1)}</label><input class="input" id="pf-${k}" name="pf:${k}" type="number" inputmode="decimal" step="0.1" min="1" max="100" value="${x}" autocomplete="off"></div>`)}</div>
      <span class="err" data-for="${s.kunci}" hidden></span></fieldset>`;
    return html`<div class="field"><label for="p-${s.kunci}">${s.label}</label>
      <div class="input-unit"><input class="input" id="p-${s.kunci}" name="${s.kunci}" type="number" inputmode="decimal" step="${s.tipe === "int" ? 1 : "any"}" ${raw(s.min !== null ? `min="${s.min}"` : "")} ${raw(s.max !== null ? `max="${s.max}"` : "")} value="${v}" autocomplete="off" aria-describedby="h-${s.kunci}">${s.satuan ? html`<span>${s.satuan}</span>` : ""}</div>
      <span class="hint" id="h-${s.kunci}">${s.bantuan}</span><span class="err" data-for="${s.kunci}" hidden></span></div>`;
  };
  render(box, html`<form id="f-param" class="stack" novalidate>
    ${Object.entries(GRUP).map(([g, judul]) => grup[g] ? html`<section class="panel panel-pad"><h2>${judul}</h2><div class="grid-form section-sm">${grup[g].map(input)}</div></section>` : "")}
    <div class="row row-end sticky-save"><span class="muted" id="status-simpan" aria-live="polite"></span><button class="btn" type="reset">Batal</button><button class="btn btn-primary" type="submit">Simpan perubahan</button></div>
  </form>`);
  const form = box.querySelector("#f-param");
  form.addEventListener("input", () => { setDirty(true); box.querySelector("#status-simpan").textContent = "Ada perubahan yang belum disimpan."; });
  form.addEventListener("reset", () => { setDirty(false); box.querySelector("#status-simpan").textContent = ""; fieldErrors(form, {}); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {};
    for (const s of d.spesifikasi) {
      if (s.tipe === "bool") body[s.kunci] = form.elements[s.kunci].checked;
      else if (s.tipe === "json") body[s.kunci] = Object.fromEntries(Object.keys(d.nilai[s.kunci]).map((k) => [k, form.elements[`pf:${k}`].value]));
      else body[s.kunci] = form.elements[s.kunci].value;
    }
    try {
      const r = await busy(form.querySelector('[type="submit"]'), "Menyimpan…", () => api("/api/pengaturan", { method: "PUT", body }));
      fieldErrors(form, {});
      setDirty(false);
      box.querySelector("#status-simpan").textContent = "";
      toast(r.berubah.length ? `${r.berubah.length} pengaturan disimpan dan dicatat di log audit.` : "Tidak ada perubahan.");
    } catch (ex) { fieldErrors(form, ex.kolom); toast(ex.message, "err"); }
  });
}

/* ------------------------------------------------------------------ gedung (U9) */
const LABEL_FUNGSI = { kuliah: "Gedung kuliah", laboratorium: "Laboratorium", kantor: "Kantor", perpustakaan: "Perpustakaan" };
const PERAN_GEDUNG = { percontohan: "Gedung percontohan", pembanding: "Gedung pembanding", lain: "Gedung lain (papan peringkat)" };

async function gedung(box, { isCurrent }) {
  const d = await api("/api/gedung");
  if (!isCurrent()) return;
  render(box, html`
    <p class="muted">Luas dan jam operasional dipakai untuk intensitas energi dan indeks efisiensi. Kapasitas panel surya dipakai untuk prediksi produksi.</p>
    <div class="stack section-sm">${d.baris.map((g) => html`<section class="panel panel-pad" aria-labelledby="g-${g.id}">
      <div class="section-head"><h2 id="g-${g.id}">${g.nama}</h2><span class="chip chip-plain">${PERAN_GEDUNG[g.peran] || g.peran}</span></div>
      <form class="grid-form" data-gedung="${g.id}" novalidate>
        <div class="field"><label for="n-${g.id}">Nama</label><input class="input" id="n-${g.id}" name="nama" value="${g.nama}" autocomplete="off"><span class="err" data-for="nama" hidden></span></div>
        <div class="field"><label for="f-${g.id}">Fungsi</label><select class="input" id="f-${g.id}" name="fungsi" autocomplete="off">${d.fungsi.map((k) => html`<option value="${k}" ${raw(k === g.fungsi ? "selected" : "")}>${LABEL_FUNGSI[k] || k}</option>`)}</select><span class="err" data-for="fungsi" hidden></span></div>
        <div class="field"><label for="l-${g.id}">Luas lantai</label><div class="input-unit"><input class="input" id="l-${g.id}" name="luas_m2" type="number" inputmode="decimal" min="50" step="any" value="${g.luas_m2}" autocomplete="off"><span>m²</span></div><span class="err" data-for="luas_m2" hidden></span></div>
        <div class="field"><label for="j-${g.id}">Jam operasional</label><div class="input-unit"><input class="input" id="j-${g.id}" name="jam_operasional_pekan" type="number" inputmode="decimal" min="1" max="168" step="any" value="${g.jam_operasional_pekan}" autocomplete="off"><span>jam/pekan</span></div><span class="err" data-for="jam_operasional_pekan" hidden></span></div>
        ${g.peran === "percontohan" ? html`<div class="field"><label for="p-${g.id}">Kapasitas panel surya</label><div class="input-unit"><input class="input" id="p-${g.id}" name="kapasitas_pv_kwp" type="number" inputmode="decimal" min="0" step="any" value="${g.kapasitas_pv_kwp}" autocomplete="off"><span>kWp</span></div><span class="err" data-for="kapasitas_pv_kwp" hidden></span></div>` : ""}
        <div class="row row-end span-all"><button class="btn btn-primary" type="submit">Simpan ${g.peran === "lain" ? "data gedung" : "gedung ini"}</button></div>
      </form>
    </section>`)}</div>`);
  box.querySelectorAll("form[data-gedung]").forEach((form) => {
    form.addEventListener("input", () => setDirty(true));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { nama: form.elements.nama.value, fungsi: form.elements.fungsi.value,
        luas_m2: Number(form.elements.luas_m2.value), jam_operasional_pekan: Number(form.elements.jam_operasional_pekan.value) };
      if (form.elements.kapasitas_pv_kwp) body.kapasitas_pv_kwp = Number(form.elements.kapasitas_pv_kwp.value);
      try {
        const g = await busy(form.querySelector('[type="submit"]'), "Menyimpan…", () => api(`/api/gedung/${form.dataset.gedung}`, { method: "PATCH", body }));
        fieldErrors(form, {});
        setDirty(false);
        form.closest("section").querySelector("h2").textContent = g.nama;
        toast(g.berubah ? `${g.nama} disimpan dan dicatat di log audit.` : "Tidak ada perubahan.");
      } catch (ex) { fieldErrors(form, ex.kolom); toast(ex.message, "err"); }
    });
  });
}

/* ------------------------------------------------------------------ jadwal (F03) */
async function jadwal(box, { isCurrent }) {
  const d = await api("/api/jadwal");
  if (!isCurrent()) return;
  const HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
  const perHari = HARI.map((h) => [h, d.baris.filter((b) => b.hari === h)]).filter(([, x]) => x.length);
  render(box, html`
    <section class="panel panel-pad" aria-labelledby="h-impor">
      <h2 id="h-impor">Impor jadwal dari CSV</h2>
      <p class="muted">Kolom wajib: <span class="mono">ruang, hari, mulai, selesai</span>. Opsional: <span class="mono">mata_kuliah</span>. Impor mengganti seluruh jadwal; baris yang salah dilewati.</p>
      <form id="f-impor" class="stack section-sm" novalidate>
        <div class="field"><label for="berkas">Berkas CSV dari sistem akademik</label><input class="input" id="berkas" name="berkas" type="file" accept=".csv,text/csv"></div>
        <div class="field"><label for="csv">Atau tempel isi CSV</label>
          <textarea class="input mono" id="csv" name="csv" rows="6" spellcheck="false" autocomplete="off" placeholder="ruang,hari,mulai,selesai,mata_kuliah&#10;A2.01,Senin,07:30,09:10,Basis Data…"></textarea>
          <span class="err" data-for="csv" hidden></span></div>
        <div class="row row-end"><button class="btn" type="submit" data-mode="periksa">Periksa berkas</button><button class="btn btn-primary" type="submit" data-mode="simpan" disabled>Impor baris valid</button></div>
      </form>
      <div id="hasil" aria-live="polite"></div>
    </section>
    <section class="section" aria-labelledby="h-jadwal">
      <div class="section-head"><h2 id="h-jadwal">Jadwal aktif</h2><p>${d.baris.length} sesi kuliah per pekan · ${d.ruang.length} ruang terdaftar</p></div>
      ${perHari.length ? html`<div class="table-wrap"><table>
        <thead><tr><th scope="col">Hari</th><th scope="col">Jam</th><th scope="col">Ruang</th><th scope="col">Mata kuliah</th></tr></thead>
        <tbody>${perHari.flatMap(([h, rows]) => rows.map((b, i) => html`<tr><td>${i === 0 ? h : ""}</td><td class="num">${b.mulai.replace(":", ".")}–${b.selesai.replace(":", ".")}</td><td>${b.ruang}</td><td class="body">${b.mata_kuliah || "–"}</td></tr>`))}</tbody>
      </table></div>` : emptyState("Belum ada jadwal", "Impor jadwal kuliah supaya prediksi dan aturan beban tanpa kelas bekerja.")}
      <p class="muted section-sm">Ruang terdaftar: ${d.ruang.join(", ")}</p>
    </section>`);
  const form = box.querySelector("#f-impor");
  const simpanBtn = form.querySelector('[data-mode="simpan"]');
  const hasil = box.querySelector("#hasil");
  form.elements.berkas.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 500000) { fieldErrors(form, { csv: "Berkas terlalu besar. Maksimal 500 KB." }); return; }
    form.elements.csv.value = await file.text();
    simpanBtn.disabled = true;
  });
  form.elements.csv.addEventListener("input", () => { simpanBtn.disabled = true; setDirty(true); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const mode = e.submitter?.dataset.mode || "periksa";
    const csv = form.elements.csv.value.trim();
    if (!csv) return fieldErrors(form, { csv: "Pilih berkas atau tempel isi CSV terlebih dahulu." });
    if (mode === "simpan" && !confirm("Impor akan mengganti seluruh jadwal aktif. Lanjutkan?")) return;
    try {
      const r = await busy(e.submitter, mode === "simpan" ? "Mengimpor…" : "Memeriksa…", () => api("/api/jadwal/impor", { method: "POST", body: { csv, simpan: mode === "simpan" } }));
      fieldErrors(form, {});
      if (r.disimpan) { setDirty(false); toast(`${r.valid} baris jadwal diimpor. Prediksi 48 jam diperbarui.`); go("#/pengaturan?tab=jadwal"); return; }
      simpanBtn.disabled = r.valid === 0;
      simpanBtn.textContent = `Impor ${r.valid} baris valid`;
      render(hasil, html`<div class="section-sm">
        <p><b>${r.valid} dari ${r.total} baris valid.</b> ${r.salah.length ? "Baris berikut akan dilewati:" : "Semua baris siap diimpor."}</p>
        ${r.salah.length ? html`<div class="table-wrap section-sm"><table><thead><tr><th scope="col" class="n">Baris</th><th scope="col">Isi</th><th scope="col">Masalah</th></tr></thead>
          <tbody>${r.salah.map((s) => html`<tr><td class="n">${s.baris}</td><td class="mono">${Object.values(s.data).join(", ")}</td><td class="crit">${s.galat.join("; ")}</td></tr>`)}</tbody></table></div>` : ""}
      </div>`);
    } catch (ex) { fieldErrors(form, { csv: ex.message }); }
  });
}

/* ------------------------------------------------------------------ pengguna (F23) */
async function pengguna(box, { isCurrent }) {
  const d = await api("/api/pengguna");
  if (!isCurrent()) return;
  const saya = user();
  render(box, html`
    <div class="table-wrap"><table>
      <thead><tr><th scope="col">Nama</th><th scope="col">Peran</th><th scope="col">Status</th><th scope="col"><span class="sr">Aksi</span></th></tr></thead>
      <tbody>${d.baris.map((u) => html`<tr data-id="${u.id}">
        <th scope="row">${u.nama}<span class="sub">${u.email}${u.demo && !d.demo ? " · akun demo" : ""}</span></th>
        <td><label class="sr" for="peran-${u.id}">Peran ${u.nama}</label>
          <select class="input input-auto" id="peran-${u.id}" name="peran" autocomplete="off" ${raw(u.id === saya.id ? "disabled" : "")}>
            ${Object.entries(d.peran).map(([k, l]) => html`<option value="${k}" ${raw(k === u.peran ? "selected" : "")}>${l}</option>`)}</select></td>
        <td>${u.aktif ? html`<span class="chip chip-good">Aktif</span>` : html`<span class="chip chip-plain">Nonaktif</span>`}</td>
        <td class="n">${u.id === saya.id ? html`<a class="btn btn-sm btn-ghost" href="#/akun">Akun ini</a>` : html`<div class="row row-end nowrap-row">${d.demo ? "" : html`<button class="btn btn-sm" type="button" data-reset>Reset kata sandi</button>`}<button class="btn btn-sm ${u.aktif ? "btn-danger" : ""}" type="button" data-aktif="${u.aktif ? "0" : "1"}">${u.aktif ? "Nonaktifkan" : "Aktifkan"}</button></div>`}</td>
      </tr>`)}</tbody>
    </table></div>
    ${d.demo ? html`<section class="panel panel-pad section"><h2>Akun demo</h2><p class="body section-sm">Daftar ini hanya memuat akun demo. Untuk menambah pengguna atau mereset kata sandi, masuk dengan akun asli tim pengelola.</p></section>` : html`<section class="panel panel-pad section" aria-labelledby="h-tambah">
      <h2 id="h-tambah">Tambah pengguna</h2>
      <p class="muted">Sistem hanya menyimpan nama, email, dan peran. Minta pengguna mengganti kata sandi awal setelah masuk.</p>
      <form id="f-tambah" class="grid-form section-sm" novalidate>
        <div class="field"><label for="u-nama">Nama</label><input class="input" id="u-nama" name="nama" autocomplete="off" required placeholder="Nama lengkap…"><span class="err" data-for="nama" hidden></span></div>
        <div class="field"><label for="u-email">Email</label><input class="input" id="u-email" name="email" type="email" inputmode="email" spellcheck="false" autocomplete="off" required placeholder="nama@unib.ac.id…"><span class="err" data-for="email" hidden></span></div>
        <div class="field"><label for="u-peran">Peran</label><select class="input" id="u-peran" name="peran" autocomplete="off">${Object.entries(d.peran).map(([k, l]) => html`<option value="${k}" ${raw(k === "piket" ? "selected" : "")}>${l}</option>`)}</select></div>
        <div class="field"><label for="u-sandi">Kata sandi awal</label><input class="input" id="u-sandi" name="sandi" type="password" autocomplete="new-password" minlength="10" required><span class="hint">Minimal 10 karakter.</span><span class="err" data-for="sandi" hidden></span></div>
        <div class="row row-end span-all"><button class="btn btn-primary" type="submit">Tambah pengguna</button></div>
      </form>
    </section>`}`);

  box.querySelectorAll("tr[data-id]").forEach((tr) => {
    const id = tr.dataset.id;
    tr.querySelector("select")?.addEventListener("change", async (e) => {
      try { await api(`/api/pengguna/${id}`, { method: "PATCH", body: { peran: e.target.value } }); toast("Peran diubah dan dicatat di log audit."); }
      catch (ex) { toast(ex.message, "err"); go("#/pengaturan?tab=pengguna"); }
    });
    tr.querySelector("[data-reset]")?.addEventListener("click", (e) => {
      const tombol = e.currentTarget;
      if (tr.nextElementSibling?.classList.contains("reset-row")) { tr.nextElementSibling.querySelector("input").focus(); return; }
      const nama = tr.querySelector("th").firstChild.textContent;
      const baris = document.createElement("tr");
      baris.className = "reset-row";
      render(baris, html`<td colspan="4"><form class="row" novalidate>
        <div class="field grow"><label for="rs-${id}">Kata sandi sementara untuk ${nama}</label>
          <input class="input" id="rs-${id}" name="sandi_baru" type="password" autocomplete="new-password" minlength="10" required>
          <span class="hint">Minimal 10 karakter. Sampaikan langsung kepada pengguna, lalu minta diganti di halaman Akun. Semua sesinya akan diakhiri.</span>
          <span class="err" data-for="sandi_baru" hidden></span></div>
        <div class="row align-end"><button class="btn" type="button" data-batal>Batal</button><button class="btn btn-primary" type="submit">Reset kata sandi</button></div>
      </form></td>`);
      tr.after(baris);
      const form = baris.querySelector("form");
      const tutup = () => { baris.remove(); tombol.focus(); };
      form.querySelector("[data-batal]").addEventListener("click", tutup);
      form.addEventListener("keydown", (ev) => { if (ev.key === "Escape") tutup(); });
      form.elements.sandi_baru.focus();
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const baru = form.elements.sandi_baru.value;
        if (baru.length < 10) return fieldErrors(form, { sandi_baru: "Kata sandi sementara minimal 10 karakter." });
        try {
          await busy(form.querySelector('[type="submit"]'), "Menyimpan…", () => api(`/api/pengguna/${id}`, { method: "PATCH", body: { sandi_baru: baru } }));
          toast(`Kata sandi ${nama} direset. Semua sesinya diakhiri.`);
          tutup();
        } catch (ex) { fieldErrors(form, Object.keys(ex.kolom).length ? ex.kolom : { sandi_baru: ex.message }); }
      });
    });
    tr.querySelector("[data-aktif]")?.addEventListener("click", async (e) => {
      const aktif = e.currentTarget.dataset.aktif === "1";
      const nama = tr.querySelector("th").firstChild.textContent;
      if (!aktif && !confirm(`Nonaktifkan ${nama}? Sesi yang sedang berjalan langsung berakhir.`)) return;
      try {
        await busy(e.currentTarget, "Menyimpan…", () => api(`/api/pengguna/${id}`, { method: "PATCH", body: { aktif } }));
        toast(aktif ? `${nama} diaktifkan.` : `${nama} dinonaktifkan.`);
        go("#/pengaturan?tab=pengguna");
      } catch (ex) { toast(ex.message, "err"); }
    });
  });
  const form = box.querySelector("#f-tambah");
  form?.addEventListener("input", () => setDirty(true));
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(["nama", "email", "peran", "sandi"].map((k) => [k, form.elements[k].value.trim()]));
    const err = {};
    if (body.nama.length < 2) err.nama = "Nama minimal 2 karakter.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.email)) err.email = "Masukkan email yang valid, misalnya nama@unib.ac.id.";
    if (body.sandi.length < 10) err.sandi = "Kata sandi awal minimal 10 karakter.";
    if (Object.keys(err).length) return fieldErrors(form, err);
    try {
      await busy(form.querySelector('[type="submit"]'), "Menambahkan…", () => api("/api/pengguna", { method: "POST", body }));
      setDirty(false);
      toast(`${body.nama} ditambahkan.`);
      go("#/pengaturan?tab=pengguna");
    } catch (ex) { fieldErrors(form, Object.keys(ex.kolom).length ? ex.kolom : { email: ex.message }); }
  });
}

/* ------------------------------------------------------------------ status sistem */
async function sistem(box, { isCurrent }) {
  const d = await api("/api/pengaturan");
  if (!isCurrent()) return;
  const kel = d.kelengkapan;
  const rerata = kel.length ? (kel.reduce((a, b) => a + b.kelengkapan, 0) / kel.length) * 100 : null;
  render(box, html`
    <div class="grid-2">
      <section class="panel panel-pad" aria-labelledby="h-perangkat">
        <h2 id="h-perangkat">Perangkat</h2>
        <ul class="list section-sm">${d.perangkat.map((p) => html`<li class="list-pad row between">
          <span><b>${p.nama}</b><span class="sub muted mono">${p.kode} · ${p.protokol}</span></span>
          <span class="right">${p.status === "aktif" ? html`<span class="chip chip-good">Aktif</span>` : html`<span class="chip chip-warn">Diam</span>`}<span class="sub muted">${p.terakhir_lapor ? f.relatif(p.terakhir_lapor) : "belum lapor"}</span></span>
        </li>`)}</ul>
      </section>
      <section class="panel panel-pad" aria-labelledby="h-worker">
        <h2 id="h-worker">Pekerja terjadwal</h2>
        <dl class="kv section-sm">
          <dt>Mode</dt><dd>${d.simulasi ? "Simulasi (data dibangkitkan tiap jam)" : "Produksi (data dari MQTT)"}</dd>
          <dt>Siklus jam</dt><dd>${d.pekerja.terakhir_jam ? f.waktu(d.pekerja.terakhir_jam) : "–"}</dd>
          <dt>Siklus harian</dt><dd>${d.pekerja.terakhir_harian ? f.waktu(d.pekerja.terakhir_harian) : "–"}</dd>
          <dt>Kelengkapan 30 hari</dt><dd>${rerata === null ? "–" : f.pct(rerata, 1)} <span class="muted">target ≥ 95 %</span></dd>
          <dt>Email</dt><dd>${d.smtp ? "SMTP aktif" : "SMTP belum diatur; email tersimpan di kotak keluar"}</dd>
          ${d.pekerja.galat ? html`<dt>Galat terakhir</dt><dd class="crit">${d.pekerja.galat}</dd>` : ""}
        </dl>
        <hr class="divider">
        <p class="body">Latih ulang model di luar jadwal mingguan, misalnya setelah kalibrasi meter.</p>
        <button class="btn section-sm" type="button" id="latih">Latih ulang model sekarang</button>
      </section>
    </div>
    <section class="section" aria-labelledby="h-peristiwa">
      <div class="section-head"><h2 id="h-peristiwa">Peristiwa data</h2><p>Paket hilang, kegagalan API cuaca, perangkat diam</p></div>
      ${d.peristiwa.length ? html`<div class="table-wrap"><table><thead><tr><th scope="col">Waktu</th><th scope="col">Jenis</th><th scope="col">Detail</th></tr></thead>
        <tbody>${d.peristiwa.map((p) => html`<tr><td>${f.waktu(p.waktu)}</td><td class="mono">${p.jenis}</td><td class="body">${p.detail}</td></tr>`)}</tbody></table></div>`
        : html`<div class="panel">${emptyState("Tidak ada peristiwa", "Semua sumber data mengirim dengan normal.")}</div>`}
    </section>
    <section class="section" aria-labelledby="h-keluar">
      <div class="section-head"><h2 id="h-keluar">Kotak keluar email</h2><p>Ringkasan mingguan tiap Senin 07.00 WIB</p></div>
      ${d.kotak_keluar.length ? html`<div class="table-wrap"><table><thead><tr><th scope="col">Waktu</th><th scope="col">Kepada</th><th scope="col">Subjek</th><th scope="col">Status</th></tr></thead>
        <tbody>${d.kotak_keluar.map((k) => html`<tr><td>${f.waktu(k.waktu)}</td><td>${k.kepada}</td><td>${k.subjek}</td><td>${k.terkirim ? "Terkirim" : "Tersimpan"}</td></tr>`)}</tbody></table></div>`
        : html`<div class="panel">${emptyState("Belum ada email", "Ringkasan mingguan pertama dikirim Senin berikutnya pukul 07.00 WIB.")}</div>`}
    </section>`);
  box.querySelector("#latih").addEventListener("click", async (e) => {
    if (!confirm("Latih ulang model sekarang? Proses berjalan sekitar 10 detik.")) return;
    try {
      const r = await busy(e.currentTarget, "Melatih…", () => api("/api/model/latih", { method: "POST" }));
      toast(`Model dilatih: MAPE ${f.fix(r.mape, 1)} %. ${r.aktif ? "Dipakai sebagai model aktif." : "Tidak dipakai karena lebih buruk dari model aktif."}`);
    } catch (ex) { toast(ex.message, "err"); }
  });
}

/* ------------------------------------------------------------------ audit (F24) */
async function audit(box, { query, isCurrent }) {
  const hal = Math.max(1, Number(query.get("hal")) || 1);
  const d = await api(`/api/audit?halaman=${hal}`);
  if (!isCurrent()) return;
  const maks = Math.max(1, Math.ceil(d.total / 50));
  render(box, html`
    <p class="muted">Log hanya bisa ditambah. Tidak ada aksi ubah atau hapus dari antarmuka maupun API. ${f.int(d.total)} entri.</p>
    <div class="table-wrap section-sm"><table>
      <thead><tr><th scope="col">Waktu</th><th scope="col">Pengguna</th><th scope="col">Aksi</th><th scope="col">Detail</th></tr></thead>
      <tbody>${d.baris.map((r) => html`<tr><td class="num nowrap">${f.waktu(r.waktu)}</td><td>${r.pengguna}</td><td class="mono">${r.aksi}</td><td class="body break">${r.detail}</td></tr>`)}</tbody>
    </table></div>
    <nav class="row row-end section-sm" aria-label="Halaman log">
      ${hal > 1 ? html`<a class="btn btn-sm" href="#/pengaturan?tab=audit&hal=${hal - 1}">Sebelumnya</a>` : ""}
      <span class="muted num">Halaman ${hal} dari ${maks}</span>
      ${hal < maks ? html`<a class="btn btn-sm" href="#/pengaturan?tab=audit&hal=${hal + 1}">Berikutnya</a>` : ""}
    </nav>`);
}
