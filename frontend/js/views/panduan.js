import { html, raw, render } from "../ui.js";

const PERAN = [
  { kode: "pengelola", judul: "Pengelola gedung", langkah: [
    "Buka Ringkasan setiap pagi. Peringatan anomali selalu tampil paling atas.",
    "Buka Rekomendasi, lalu pilih filter Diusulkan. Baca alasan, grafik aktual dan prediksi, serta panel yang dicurigai.",
    "Bila masuk akal, pilih pelaksana dan batas waktu, lalu tekan Verifikasi rekomendasi. Bila tidak, tekan Tolak rekomendasi dan tulis alasannya.",
    "Tanggapi notifikasi eskalasi saat tugas melewati batas waktu.",
    "Setelah pemantauan 14 hari selesai, buka rekomendasinya, periksa angka sebelum dan sesudah, lalu tekan Catat hasil.",
  ] },
  { kode: "piket", judul: "Mahasiswa piket", langkah: [
    "Masuk, lalu buka Tugas dan rekomendasi. Tugas aktif kamu ada di bagian atas.",
    "Datangi ruang yang disebut, lakukan tindakannya, misalnya mematikan AC dan lampu.",
    "Tekan Tandai sudah dilaksanakan, tulis catatan bukti (ruang, jam, apa yang dilakukan), lalu simpan.",
    "Jangan mengubah instalasi listrik. Laporkan kerusakan ke teknisi gedung.",
  ] },
  { kode: "tim", judul: "Tim pengelola", langkah: [
    "Ikuti daftar Persiapan sistem di Ringkasan sampai semua langkah wajib selesai.",
    "Pengaturan > Gedung: periksa luas dan jam operasional, daftarkan meter dan inverter dengan kode yang sama dengan gateway, lalu petakan ruang ke panel.",
    "Pengaturan > Jadwal kuliah: impor CSV jadwal tiap awal semester.",
    "Pengaturan > Pengguna: buat akun pengelola, piket, dan pimpinan.",
    "Pengaturan > Status sistem: pastikan semua perangkat Aktif dan kelengkapan data minimal 95 %.",
    "Akhir semester: unduh laporan CSV di Dampak dan lakukan latihan pemulihan cadangan.",
  ] },
  { kode: "pimpinan", judul: "Pimpinan kampus", langkah: [
    "Buka Dampak untuk melihat penghematan terukur, biaya dan emisi terhindarkan, serta indikator keberhasilan.",
    "Buka Papan peringkat untuk membandingkan indeks efisiensi antargedung.",
    "Unduh laporan CSV per semester sebagai dasar keputusan perluasan.",
  ] },
  { kode: "akademik", judul: "Mahasiswa dan dosen", langkah: [
    "Buka Pusat belajar untuk mengunduh dataset agregat per jam.",
    "Ikuti modul praktikum dan pilih topik tugas akhir yang tersedia.",
    "Bandingkan hasil modelmu dengan riwayat versi model sistem.",
  ] },
];

export default async function panduan({ main, user }) {
  let adaVideo = false;
  try { adaVideo = (await fetch("/assets/video/panduan.mp4", { method: "HEAD" })).ok; } catch { /* abaikan */ }
  const urut = [...PERAN].sort((a, b) => (a.kode === user.peran ? -1 : b.kode === user.peran ? 1 : 0));
  render(main, html`
    <div class="page-head"><div><h1>Panduan</h1><p>Cara memakai SOLAR-EDU AI. Sistem hanya mengusulkan; manusia yang memverifikasi dan melaksanakan.</p></div></div>
    <section class="panel panel-pad" aria-labelledby="h-video">
      <h2 id="h-video">Video cara pemakaian</h2>
      ${adaVideo ? html`<p class="muted">Tampilan di video memakai data contoh. Teks keterangan bisa dinyalakan lewat tombol CC.</p>
        <video class="video section-sm" controls preload="metadata" playsinline width="1280" height="720" poster="/assets/video/panduan-poster.jpg">
          <source src="/assets/video/panduan.mp4" type="video/mp4">
          <track kind="captions" src="/assets/video/panduan.vtt" srclang="id" label="Bahasa Indonesia" default>
          Peramban ini tidak bisa memutar video. <a href="/assets/video/panduan.mp4">Unduh videonya</a>.
        </video>
        <p class="muted section-sm"><a href="/assets/video/panduan.vtt" download>Unduh transkrip</a></p>`
        : html`<p class="body section-sm">Video belum tersedia. Gunakan langkah tertulis di bawah.</p>`}
    </section>
    <section class="section" aria-labelledby="h-langkah">
      <div class="section-head"><h2 id="h-langkah">Langkah per peran</h2><p>Peranmu ditampilkan paling atas.</p></div>
      <div class="panel">${urut.map((p) => html`<details class="acc" ${raw(p.kode === user.peran ? "open" : "")}>
        <summary><span class="code">${p.kode === user.peran ? "Peranmu" : ""}</span><span><b>${p.judul}</b></span></summary>
        <div class="acc-body"><ol>${p.langkah.map((l) => html`<li>${l}</li>`)}</ol></div>
      </details>`)}</div>
    </section>
    <section class="panel panel-pad section" aria-labelledby="h-prinsip">
      <h2 id="h-prinsip">Arti warna</h2>
      <ul class="legend section-sm">
        <li><i class="key key-pred" aria-hidden="true"></i>Biru: prediksi dan rentangnya</li>
        <li><i class="key key-pv" aria-hidden="true"></i>Kuning: produksi panel surya</li>
        <li><i class="key key-crit" aria-hidden="true"></i>Merah: hanya untuk anomali, selalu disertai label teks</li>
        <li><i class="key key-act" aria-hidden="true"></i>Hitam: beban aktual</li>
      </ul>
    </section>`);
}
