import { api } from "../api.js";
import { busy, fieldErrors, html, raw, render, toast } from "../ui.js";

export default async function akun({ main, user }) {
  render(main, html`
    <div class="page-head"><div><h1>Akun</h1><p>${user.nama} · ${user.peran_label}</p></div></div>
    <section class="panel panel-pad" aria-labelledby="h-notif">
      <h2 id="h-notif">Notifikasi</h2>
      <form id="f-pref" class="stack section-sm">
        <label class="check"><input type="checkbox" name="notif_aplikasi" ${raw(user.notif_aplikasi ? "checked" : "")}><span><b>Notifikasi dalam aplikasi</b><span class="sub muted">Rekomendasi baru, tugas, batas waktu, dan eskalasi.</span></span></label>
        <label class="check"><input type="checkbox" name="email_mingguan" ${raw(user.email_mingguan ? "checked" : "")}><span><b>Email ringkasan mingguan</b><span class="sub muted">Anomali, tindakan, dan prediksi pekan depan. Dikirim Senin 07.00 WIB ke ${user.email}.</span></span></label>
      </form>
    </section>
    <section class="panel panel-pad section" aria-labelledby="h-sandi">
      <h2 id="h-sandi">Ganti kata sandi</h2>
      <p class="muted">Sesi di perangkat lain akan diakhiri. Perangkat ini tetap masuk.</p>
      <form id="f-sandi" class="grid-form section-sm" novalidate>
        <input type="text" name="username" autocomplete="username" value="${user.email}" hidden>
        <div class="field"><label for="s-lama">Kata sandi lama</label><input class="input" id="s-lama" name="lama" type="password" autocomplete="current-password" required><span class="err" data-for="lama" hidden></span></div>
        <div class="field"><label for="s-baru">Kata sandi baru</label><input class="input" id="s-baru" name="baru" type="password" autocomplete="new-password" minlength="10" required><span class="hint">Minimal 10 karakter.</span><span class="err" data-for="baru" hidden></span></div>
        <div class="field"><label for="s-ulang">Ulangi kata sandi baru</label><input class="input" id="s-ulang" name="ulang" type="password" autocomplete="new-password" required><span class="err" data-for="ulang" hidden></span></div>
        <div class="row row-end span-all"><button class="btn btn-primary" type="submit">Simpan kata sandi baru</button></div>
      </form>
    </section>
    <section class="panel panel-pad section" aria-labelledby="h-privasi">
      <h2 id="h-privasi">Data yang disimpan</h2>
      <p class="body section-sm">Sistem hanya menyimpan nama, email, peran, dan log aksi untuk audit. Data energi bersifat agregat per gedung dan panel. Tidak ada kamera, pengenalan wajah, atau jejak lokasi orang.</p>
    </section>`);
  const form = main.querySelector("#f-pref");
  form.addEventListener("change", async (e) => {
    const body = { [e.target.name]: e.target.checked };
    try {
      const r = await api("/api/saya/notifikasi", { method: "PUT", body });
      Object.assign(user, r);
      toast("Preferensi notifikasi disimpan.");
    } catch (ex) { e.target.checked = !e.target.checked; toast(ex.message, "err"); }
  });
  const fs = main.querySelector("#f-sandi");
  fs.addEventListener("submit", async (e) => {
    e.preventDefault();
    const lama = fs.elements.lama.value, baru = fs.elements.baru.value, ulang = fs.elements.ulang.value;
    const err = {};
    if (!lama) err.lama = "Isi kata sandi lama.";
    if (baru.length < 10) err.baru = "Kata sandi baru minimal 10 karakter.";
    else if (baru === lama) err.baru = "Harus berbeda dari kata sandi lama.";
    if (baru !== ulang) err.ulang = "Ketik ulang kata sandi baru yang sama.";
    if (Object.keys(err).length) return fieldErrors(fs, err);
    try {
      await busy(fs.querySelector('[type="submit"]'), "Menyimpan…", () => api("/api/saya/sandi", { method: "PUT", body: { lama, baru } }));
      fs.reset();
      fieldErrors(fs, {});
      toast("Kata sandi diganti. Sesi di perangkat lain sudah diakhiri.");
    } catch (ex) { fieldErrors(fs, Object.keys(ex.kolom).length ? ex.kolom : { lama: ex.message }); }
  });
}
