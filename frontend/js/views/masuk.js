import { api } from "../api.js";
import { busy, html, render } from "../ui.js";

const DEMO = [
  ["Pengelola gedung", "pengelola@solar-edu.test"],
  ["Mahasiswa piket", "bima.piket@solar-edu.test"],
  ["Tim pengelola", "tim@solar-edu.test"],
  ["Pimpinan kampus", "pimpinan@solar-edu.test"],
  ["Mahasiswa dan dosen", "mahasiswa@solar-edu.test"],
];

export async function renderLogin(box, pesan, onMasuk) {
  document.title = "Masuk · SOLAR-EDU AI";
  let simulasi = false;
  try { simulasi = (await (await fetch("/api/sehat")).json()).simulasi; } catch { /* abaikan */ }
  render(box, html`
    <section class="masuk-art" aria-hidden="false">
      <div>
        <h1>AI mengusulkan, manusia memutuskan.</h1>
        <p>SOLAR-EDU AI membaca konsumsi listrik dan produksi panel surya gedung kampus, memprediksi beban 24 jam ke depan, lalu menandai pemborosan sebagai rekomendasi yang selalu diverifikasi pengelola gedung.</p>
      </div>
      <ol>
        <li><span>1</span>Ukur beban per panel, produksi inverter, cuaca, dan jadwal kuliah.</li>
        <li><span>2</span>Prediksi beban dengan Random Forest dan bandingkan dengan aktual.</li>
        <li><span>3</span>Pengelola memverifikasi, mahasiswa piket melaksanakan.</li>
        <li><span>4</span>Pantau 14 hari, bandingkan dengan gedung pembanding, catat hasil.</li>
      </ol>
      <p>Universitas Bengkulu · gedung percontohan versi 1</p>
    </section>
    <section class="masuk-form">
      <form class="masuk-card" id="form-masuk" novalidate>
        <div class="brand" translate="no"><img src="/assets/logo-128.png" width="40" height="40" alt="Logo SOLAR-EDU AI"><span>SOLAR-EDU <b>AI</b></span></div>
        <div><h2>Masuk</h2><p class="muted">Gunakan akun kampus yang didaftarkan tim pengelola.</p></div>
        ${pesan ? html`<p class="form-err" role="alert">${pesan}</p>` : ""}
        <p class="form-err" id="masuk-err" role="alert" hidden></p>
        <div class="field">
          <label for="email">Email</label>
          <input class="input" id="email" name="email" type="email" inputmode="email" autocomplete="username" spellcheck="false" placeholder="nama@unib.ac.id…" required>
        </div>
        <div class="field">
          <label for="sandi">Kata sandi</label>
          <input class="input" id="sandi" name="sandi" type="password" autocomplete="current-password" required>
        </div>
        <button class="btn btn-primary btn-block" type="submit">Masuk</button>
        ${simulasi ? html`<div class="demo">
          <b>Akun uji prototipe</b>
          <p class="muted">Pilih peran untuk mengisi email. Kata sandi uji tercatat di README dan berkas seed.</p>
          <ul>${DEMO.map(([p, e]) => html`<li><button type="button" data-email="${e}"><span>${p}</span><span>${e}</span></button></li>`)}</ul>
        </div>` : ""}
      </form>
    </section>`);
  const form = box.querySelector("#form-masuk");
  const err = box.querySelector("#masuk-err");
  box.querySelectorAll("[data-email]").forEach((b) => b.addEventListener("click", () => {
    form.elements.email.value = b.dataset.email;
    form.elements.sandi.focus();
  }));
  if (matchMedia("(pointer: fine)").matches) form.elements.email.focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const email = form.elements.email.value.trim();
    const sandi = form.elements.sandi.value;
    if (!email || !sandi) {
      err.textContent = !email ? "Isi email akun kampus." : "Isi kata sandi.";
      err.hidden = false;
      (!email ? form.elements.email : form.elements.sandi).focus();
      return;
    }
    const btn = form.querySelector('button[type="submit"]');
    try {
      const u = await busy(btn, "Memeriksa…", () => api("/api/auth/masuk", { method: "POST", body: { email, sandi } }));
      onMasuk(u);
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
      form.elements.sandi.select();
    }
  });
}
