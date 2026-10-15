// Daftar tugas piket dengan formulir "Tandai sudah dilaksanakan" (F17).
import { api } from "../api.js";
import * as f from "../fmt.js";
import { busy, fieldErrors, html, toast } from "../ui.js";

export function tugasList(tugas, sapaKamu = false) {
  return html`<ul class="list">${tugas.map((t) => {
    const late = t.terlambat;
    return html`<li class="task" data-tugas="${t.id}">
      <div>
        <h3>${t.judul}</h3>
        <p class="body">${t.lokasi}</p>
        <p class="deadline ${late ? "late" : ""}">${late ? "Lewat batas waktu" : "Batas waktu"} ${f.waktu(t.batas_waktu)} WIB${late ? "" : ` · ${f.relatif(t.batas_waktu)}`}</p>
      </div>
      <div class="row"><a class="btn btn-sm btn-ghost" href="#/rekomendasi/${t.rekomendasi_id}">Detail</a>
        <button class="btn btn-sm btn-primary" type="button" data-buka="${t.id}" aria-expanded="false" aria-controls="form-${t.id}">Tandai sudah dilaksanakan</button></div>
      <form id="form-${t.id}" class="stack" hidden novalidate>
        <div class="field">
          <label for="bukti-${t.id}">Catatan bukti</label>
          <textarea class="input" id="bukti-${t.id}" name="catatan" autocomplete="off" required placeholder="Contoh: AC A2.01–A2.04 sudah dimatikan pukul 17.15…"></textarea>
          <span class="hint">${sapaKamu ? "Tulis apa yang kamu lakukan dan ruang yang sudah dicek." : "Tulis tindakan dan ruang yang sudah dicek."}</span>
          <span class="err" data-for="catatan" hidden></span>
        </div>
        <div class="row row-end">
          <button class="btn btn-sm" type="button" data-batal>Batal</button>
          <button class="btn btn-sm btn-primary" type="submit">Simpan sebagai dilaksanakan</button>
        </div>
      </form>
    </li>`;
  })}</ul>`;
}

export function bindTugas(root, onDone) {
  root.querySelectorAll("[data-buka]").forEach((b) => {
    const form = root.querySelector(`#form-${CSS.escape(b.dataset.buka)}`);
    b.addEventListener("click", () => {
      form.hidden = false;
      b.setAttribute("aria-expanded", "true");
      b.hidden = true;
      form.elements.catatan.focus();
    });
    form.querySelector("[data-batal]").addEventListener("click", () => {
      form.hidden = true; b.hidden = false; b.setAttribute("aria-expanded", "false"); b.focus();
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const catatan = form.elements.catatan.value.trim();
      if (catatan.length < 3) return fieldErrors(form, { catatan: "Tulis catatan singkat sebagai bukti, minimal 3 karakter." });
      try {
        await busy(form.querySelector('[type="submit"]'), "Menyimpan…", () =>
          api(`/api/tugas/${b.dataset.buka}/selesai`, { method: "POST", body: { catatan } }));
        toast("Tugas ditandai sudah dilaksanakan. Pemantauan 14 hari dimulai.");
        onDone();
      } catch (ex) { fieldErrors(form, { catatan: ex.message }); }
    });
  });
}
