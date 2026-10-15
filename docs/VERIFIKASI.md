# Laporan verifikasi akhir · SOLAR-EDU AI 1.0.0

Tanggal uji: 15 Oktober 2026. Lingkungan: Windows 11, Python 3.14, SQLite, mode simulasi. Semua angka model dan dampak berasal dari **data simulasi**.

## Ringkasan

| Pemeriksaan | Hasil |
|---|---|
| Uji otomatis (`pytest`) | 29 dari 29 lulus |
| Uji serangan dari luar (sesi, CSRF, IDOR, rate limit, traversal, header, injeksi CSV) | 27 dari 27 lulus |
| Matriks hak akses di antarmuka, 5 peran × 7 layar | Cocok dengan PRD |
| Kontras warna WCAG 2.2 AA, 18 pasangan token terang dan gelap | 18 dari 18 lulus (terendah 4,55:1) |
| Uji beban 20 pengguna bersamaan | Ringkasan median 249 ms, maksimum 691 ms (batas 3 detik) |
| Gambar grafik 72 jam | 3 ms (batas 1 detik) |
| Lebar 360 piksel | Tanpa geser horizontal di 12 layar |
| Pedoman antarmuka web (Vercel) | Tanpa temuan |
| Akurasi model (MAPE, uji mundur 14 hari) | 5,0–10,2 % pada 10 versi mingguan (target ≤ 15 %) |

## Kebutuhan fungsional

| ID | Kebutuhan | Status | Bukti |
|---|---|---|---|
| F01 | Pembacaan meter dan inverter lewat MQTT, stempel WIB, paket hilang tercatat | Terpenuhi | `/api/ingest`, `scripts/mqtt_bridge.py`, peristiwa `paket_hilang` |
| F02 | Prakiraan cuaca 48 jam; kegagalan API memicu peringatan admin | Terpenuhi | `jobs.perbarui_cuaca` (tiap jam), notifikasi `galat_data` |
| F03 | Impor jadwal CSV, baris salah ditandai per baris | Terpenuhi | `test_impor_jadwal_tandai_baris_salah` |
| F04 | Validasi dan bendera kualitas | Terpenuhi | `test_validasi_pembacaan` |
| F05 | Agregasi per jam dalam toleransi 0,5 % | Terpenuhi | `test_agregasi_per_jam_dalam_toleransi_05_persen` |
| F06 | Prediksi beban 24 jam sebelum 03.00 dengan rentang 10–90 % | Terpenuhi | Siklus 02.00 (48 jam), P10/P90 dari pohon |
| F07 | Prediksi produksi PV | Terpenuhi | `forecast.prediksi_pv` |
| F08 | Latih ulang mingguan, versi tercatat | Terpenuhi | Pusat belajar > Riwayat versi model |
| F09 | Anomali ≥ 2 jam dengan waktu, kelebihan kWh, ruang terjadwal | Terpenuhi | `test_runs_*`, `test_ambang_*` |
| F10 | Aturan beban tinggi tanpa kelas, bisa dimatikan | Terpenuhi | Parameter `aturan_jadwal_aktif` |
| F11 | Rekomendasi dengan alasan, ruang, pelaksana, estimasi | Terpenuhi | Halaman detail rekomendasi |
| F12 | Verifikasi atau tolak; penolakan wajib beralasan; tercatat di audit | Terpenuhi | `test_alur_rekomendasi_penuh` |
| F13 | Status tidak bisa melompat | Terpenuhi | `test_status_tidak_bisa_melompat`, uji API 409 |
| F14 | Evaluasi setelah 14 hari, konsumsi terisi otomatis | Terpenuhi | Uji API 422 sebelum 14 hari; 3 evaluasi pada data simulasi |
| F15 | Notifikasi dalam aplikasi ≤ 5 menit | Terpenuhi | Dibuat saat peristiwa; antarmuka memeriksa tiap 60 detik |
| F16 | Email ringkasan mingguan, bisa dimatikan per pengguna | Terpenuhi* | Halaman Akun; *pengiriman SMTP belum diuji dengan server surat sungguhan |
| F17 | Piket melihat dan menandai tugasnya | Terpenuhi | Uji IDOR: piket tidak bisa membuka atau menandai tugas orang lain |
| F18 | Indeks efisiensi, rumus tampil di layar | Terpenuhi | `test_indeks_efisiensi`, Papan peringkat |
| F19 | Baseline, kWh, rupiah, emisi; faktor bisa diubah | Terpenuhi | `test_intensitas_emisi_rupiah`, halaman Dampak |
| F20 | Laporan CSV semester | Terpenuhi | `test_laporan_csv_aman` (BOM, koma desimal, aman dari injeksi rumus) |
| F21 | Dataset agregat tanpa identitas | Terpenuhi | `test_dataset_tanpa_identitas` |
| F22 | Pengaturan dengan validasi per kolom dan audit | Terpenuhi | `test_validasi_pengaturan` |
| F23 | Lima peran sesuai matriks | Terpenuhi | `test_matriks_hak_akses` × 5 peran |
| F24 | Log audit tidak bisa diubah | Terpenuhi | `test_log_audit_tidak_bisa_diubah` |
| U9 | Mengelola pengguna dan gedung | Terpenuhi | Pengaturan > Pengguna dan Gedung, `test_ubah_gedung` |

## Kebutuhan nonfungsional

| Kategori | Status | Catatan |
|---|---|---|
| Kinerja | Terpenuhi | Lihat ringkasan di atas |
| Ketersediaan | Terpenuhi sebagian | Kegagalan sumber data tidak menjatuhkan dashboard (worker menangkap galat). Waktu aktif 99 % diukur di server. |
| Akurasi data | Terpenuhi | Kelengkapan per hari di Status sistem; indikator ≥ 95 % |
| Privasi | Terpenuhi | Hanya agregat gedung dan panel |
| Keamanan | Terpenuhi untuk aplikasi | PBKDF2, sesi 30 menit, RBAC di server, CSRF, CSP, rate limit per email+IP, token ingest wajib di produksi. HTTPS lewat Nginx (konfigurasi tersedia). |
| Aksesibilitas | Terpenuhi | Kontras AA, papan ketik, grafik dengan teks alternatif dan panah, `prefers-reduced-motion`, target sentuh 44 piksel |
| Responsif | Terpenuhi | 360 piksel tanpa geser horizontal |
| Keterpeliharaan | Terpenuhi | `scripts/pasang.sh`, `docs/TEKNIS.md`, `docs/SOP.md` |
| Keterjelasan model | Terpenuhi | Setiap rekomendasi menampilkan alasan dan fitur paling berpengaruh |
| Pemulihan | Disiapkan | Cadangan harian terenkripsi dan `scripts/pulihkan.sh`; latihan pemulihan dilakukan di server |

## Perbaikan dari uji akhir

1. Batas percobaan masuk sebelumnya dikunci per email saja, sehingga orang lain bisa mengunci akun seseorang. Sekarang dikunci per email + IP, dengan batas tambahan per IP.
2. Mode produksi kini menolak berjalan bila `INGEST_TOKEN` masih bawaan atau terlalu pendek.
3. Zona waktu proses dipaksa WIB (kontainer Docker bawaannya UTC), dan `tzdata` ditambahkan.
4. Laporan CSV aman dari injeksi rumus spreadsheet, memakai koma desimal dan BOM UTF-8.
5. Paket hilang kini dicatat sebagai peristiwa data (F01).
6. Sesi kedaluwarsa dibersihkan tiap jam. Dokumentasi API (`/api/docs`) ditutup di mode produksi.
7. Reset kata sandi oleh tim memakai formulir dengan isian tersamar, bukan kotak `prompt()`.

## Belum diuji di lingkungan ini

- Docker Compose, PostgreSQL + TimescaleDB, Mosquitto, Nginx, dan skrip cadangan atau pemulihan, karena Docker Desktop tidak terpasang di komputer pengembang. Konfigurasi Compose lolos validasi sintaks. Uji pertama dilakukan dengan `sh scripts/pasang.sh` di server kampus.
- Pengiriman email SMTP dan prakiraan Open-Meteo sungguhan (`WEATHER_LIVE=1`).
- Akurasi pada data nyata. Angka MAPE di atas berasal dari data simulasi dan harus dibuktikan pada Fase 1.
