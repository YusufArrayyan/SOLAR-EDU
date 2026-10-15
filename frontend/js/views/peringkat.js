import { api } from "../api.js";
import * as f from "../fmt.js";
import { bar, emptyState, html, raw, render } from "../ui.js";
import { go } from "../app.js";

const FUNGSI = { kuliah: "Gedung kuliah", laboratorium: "Laboratorium", kantor: "Kantor", perpustakaan: "Perpustakaan" };

export default async function peringkat({ main, query, isCurrent }) {
  const p = query.get("periode");
  const d = await api(`/api/peringkat${p ? `?periode=${encodeURIComponent(p)}` : ""}`);
  if (!isCurrent()) return;
  if (!d.baris.length) {
    render(main, html`<div class="page-head"><h1>Papan peringkat</h1></div>${emptyState("Belum ada skor", "Skor dihitung setelah satu bulan data meter terkumpul.")}`);
    return;
  }
  const maks = Math.max(...d.baris.map((b) => b.indeks), 100);
  render(main, html`
    <div class="page-head">
      <div><h1>Papan peringkat</h1><p>Indeks efisiensi per fungsi gedung. Gedung yang lebih besar atau lebih lama beroperasi tidak dirugikan.</p></div>
      <div class="field">
        <label for="periode">Periode</label>
        <select class="input" id="periode" name="periode" autocomplete="off">
          ${d.daftar_periode.map((x) => html`<option value="${x}" ${raw(x === d.periode ? "selected" : "")}>${f.bulan(x)}</option>`)}
        </select>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <caption class="sr">Peringkat indeks efisiensi gedung, ${f.bulan(d.periode)}</caption>
        <thead><tr>
          <th scope="col" class="n">#</th><th scope="col">Gedung</th><th scope="col" class="n">Intensitas</th>
          <th scope="col" class="n">Pembanding</th><th scope="col">Indeks efisiensi</th><th scope="col" class="n">Perubahan</th>
        </tr></thead>
        <tbody>${d.baris.map((b) => html`<tr class="${b.peran === "percontohan" ? "me" : ""}">
          <td class="n">${b.peringkat}</td>
          <th scope="row">${b.nama}<span class="sub">${FUNGSI[b.fungsi] || b.fungsi} · ${f.int(b.luas_m2)} m² · ${f.int(b.jam_operasional_pekan)} jam/pekan${b.peran === "percontohan" ? " · percontohan" : b.peran === "pembanding" ? " · pembanding" : ""}</span></th>
          <td class="n">${f.fix(b.intensitas, 2)}<span class="sub">Wh/m²/jam</span></td>
          <td class="n">${f.fix(b.pembanding, 1)}</td>
          <td><div class="row"><b class="num">${f.fix(b.indeks, 1)}</b><span class="grow">${bar(b.indeks, maks, b.indeks >= 100 ? "good" : "")}</span></div></td>
          <td class="n">${b.perubahan === null ? "–" : html`<span class="${b.perubahan > 0 ? "up" : b.perubahan < 0 ? "down" : ""}">${b.perubahan > 0 ? "▲ " : b.perubahan < 0 ? "▼ " : ""}${f.fix(Math.abs(b.perubahan), 1)}</span>`}</td>
        </tr>`)}</tbody>
      </table>
    </div>
    <section class="panel panel-pad section" aria-labelledby="h-cara">
      <h2 id="h-cara">Cara skor dihitung</h2>
      <div class="grid-2 section-sm">
        <div class="stack">
          <p class="formula">intensitas = kWh bulan × 1.000 ÷ (luas m² × jam operasional)</p>
          <p class="formula">indeks = pembanding fungsi ÷ intensitas aktual × 100</p>
        </div>
        <ul class="body bullets">
          <li>Indeks 100 berarti setara nilai acuan untuk fungsi gedung yang sama. Di atas 100 lebih efisien.</li>
          <li>Pembanding tiap fungsi diatur tim pengelola di Pengaturan.</li>
          <li>Gedung selain percontohan dan pembanding memakai data bulanan meter utama kampus (data simulasi pada prototipe).</li>
        </ul>
      </div>
    </section>`);
  main.querySelector("#periode").addEventListener("change", (e) => go(`#/peringkat?periode=${e.target.value}`));
}
