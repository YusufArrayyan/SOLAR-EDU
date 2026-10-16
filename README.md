# SOLAR-EDU AI · versi 1.1.0

Aplikasi web yang membaca konsumsi listrik dan produksi panel surya satu gedung kampus, memprediksi beban 24 jam ke depan dengan Random Forest, menandai pemborosan dari residu prediksi, lalu mengubahnya menjadi rekomendasi yang **selalu diverifikasi manusia**. Dibangun sesuai `PRD SOLAR-EDU AI.docx` (versi 1: delapan modul, lima peran, satu gedung).

Bawaan aplikasi adalah **mode produksi**: hanya data nyata dari meter dan inverter gedung, tanpa data simulasi dan tanpa akun demo. Mode simulasi tersedia khusus untuk pengembangan dan pengujian.

## Mulai cepat (produksi)

1. Deploy ([Render](#deploy-ke-render) atau [server kampus](#pemasangan-di-server-kampus)) dengan `ADMIN_EMAIL`, `ADMIN_PASSWORD`, dan `INGEST_TOKEN`.
2. Masuk dengan akun admin. Ringkasan menampilkan **Persiapan sistem**: daftar langkah sampai sistem siap.
3. **Pengaturan > Gedung**: periksa data gedung, daftarkan meter per panel dan inverter (kode = topik gateway), lalu petakan ruang ke panel.
4. **Pengaturan > Jadwal kuliah**: impor CSV jadwal semester.
5. **Pengaturan > Pengguna**: buat akun pengelola gedung, mahasiswa piket, dan pimpinan.
6. Hubungkan gateway sesuai contoh di **Pengaturan > Status sistem** (MQTT atau HTTPS ke `/api/ingest`).
7. Setelah 21 hari data bersih terkumpul, model prediksi dilatih otomatis pukul 02.00, lalu deteksi pemborosan dan rekomendasi berjalan.

Video dan langkah tertulis per peran tersedia di menu **Panduan** di dalam aplikasi.

## Menjalankan secara lokal

Butuh Python 3.11 atau lebih baru.

```bash
python -m pip install -r backend/requirements.txt
python backend/run.py --simulasi
```

`--simulasi` mengisi 150 hari data contoh dan akun uji (kata sandi di [backend/app/seed.py](backend/app/seed.py)) agar semua fitur bisa dicoba. Di Windows bisa juga klik ganda `scripts/jalankan.bat`. Tanpa `--simulasi`, server berjalan dalam mode produksi dan wajib diberi `ADMIN_EMAIL`, `ADMIN_PASSWORD` (minimal 10 karakter), dan `INGEST_TOKEN` (minimal 24 karakter).

| Peran (mode simulasi) | Email uji | Layar utama |
|---|---|---|
| Pengelola gedung | pengelola@solar-edu.test | Ringkasan, Rekomendasi |
| Mahasiswa piket | bima.piket@solar-edu.test (juga nadia., sari.) | Tugas dan rekomendasi |
| Tim pengelola | tim@solar-edu.test | Pengaturan, semua layar |
| Pimpinan kampus | pimpinan@solar-edu.test | Dampak, Papan peringkat |
| Mahasiswa dan dosen | mahasiswa@solar-edu.test | Pusat belajar |

Server produksi yang menemukan basis data berisi data simulasi akan meresetnya otomatis saat menyala.

## Deploy ke Render

Blueprint [render.yaml](render.yaml): satu layanan web Docker mode produksi di region Singapura, paket Starter, dan disk permanen 1 GB untuk basis data serta model.

1. Di dashboard Render pilih **New > Blueprint**, lalu hubungkan repo GitHub ini.
2. Isi `ADMIN_EMAIL` dan `ADMIN_PASSWORD` saat diminta. `INGEST_TOKEN` dibuat otomatis oleh Render; salin nilainya ke konfigurasi gateway.
3. Tekan **Apply**, lalu ikuti [Mulai cepat](#mulai-cepat-produksi).

Layanan yang sebelumnya berjalan dengan data simulasi direset otomatis saat versi ini pertama kali menyala. Gateway gedung mengirim data langsung ke `https://<layanan>.onrender.com/api/ingest`; Render tidak menjalankan broker MQTT.

## Pemetaan modul PRD

| Modul | Implementasi |
|---|---|
| M1 Akuisisi data | `POST /api/ingest` + [scripts/mqtt_bridge.py](scripts/mqtt_bridge.py) (MQTT), prakiraan Open-Meteo (`WEATHER_LIVE=1`), impor jadwal CSV |
| M2 Penyimpanan dan pembersihan | [data_pipeline.py](backend/app/services/data_pipeline.py): bendera kualitas 0/1/2, agregasi per jam |
| M3 Mesin prediksi | [forecast.py](backend/app/services/forecast.py): RF 300 pohon, min. 3 sampel per daun, dua lintasan, P10–P90, uji mundur 14 hari, aktivasi bila MAPE ≤ 110 % model lama |
| M4 Deteksi anomali | [anomaly.py](backend/app/services/anomaly.py): residu > max(4 kW, 3 × MAD) selama ≥ 2 jam, aturan beban tanpa kelas, panel tersangka |
| M5 Rekomendasi dan verifikasi | [recommend.py](backend/app/services/recommend.py): alasan, fitur berpengaruh, estimasi = kelebihan × peluang berulang, state machine tanpa lompatan, kedaluwarsa 7 hari, evaluasi selisih-dalam-selisih 14 hari |
| M6 Notifikasi dan tugas | notifikasi aplikasi (polling 60 detik), pengingat, eskalasi, email ringkasan Senin 07.00 |
| M7 Peringkat dan dampak | [impact.py](backend/app/services/impact.py): indeks efisiensi, baseline, kWh, rupiah, emisi, laporan CSV |
| M8 Pusat belajar dan administrasi | dataset agregat, modul praktikum, topik TA, pengaturan, data gedung, pengguna (termasuk reset kata sandi), log audit yang hanya bisa ditambah |

Siklus kerja dijalankan oleh worker di [jobs.py](backend/app/services/jobs.py): tiap jam (data, prakiraan cuaca, deteksi, tenggat), tiap hari pukul 02.00 (prediksi 48 jam, skor bulanan), dan tiap Minggu (latih ulang).

## Keamanan dan privasi

- Kata sandi di-hash PBKDF2-SHA256, sesi berakhir setelah 30 menit tidak aktif, dan login dibatasi 5 percobaan per 10 menit. Pengguna bisa mengganti kata sandi di halaman Akun; tim pengelola bisa mereset kata sandi, dan reset itu mengakhiri semua sesi pengguna tersebut.
- Otorisasi diperiksa di server untuk setiap permintaan sesuai matriks hak akses PRD (diuji per peran di `tests/test_api.py`).
- Perlindungan CSRF memakai header wajib `X-Solar-Edu`. Header keamanan dan CSP ketat aktif (tanpa skrip atau gaya inline).
- Hanya data agregat gedung dan panel yang disimpan; tidak ada data identitas penghuni.

## Pengujian

```bash
cd backend
python -m pytest -q
```

## Pemasangan di server kampus

Butuh Docker Engine dan openssl di server.

```bash
sh scripts/pasang.sh
```

Skrip ini membuat `.env` berisi rahasia acak, sertifikat TLS (HTTPS dan broker MQTT), dan akun broker untuk jembatan serta gateway, lalu menjalankan seluruh layanan:

| Layanan | Fungsi |
|---|---|
| `nginx` | HTTPS; `/api/ingest` ditutup dari luar |
| `app` | FastAPI + worker terjadwal (mode produksi, `SOLAR_SIMULATION=0`) |
| `db` | PostgreSQL 16 + TimescaleDB (hypertable `pengukuran`, `agregat_jam`) |
| `mqtt`, `bridge` | Mosquitto dengan TLS dan kredensial; jembatan topik `solar/<kode-perangkat>` ke API |
| `backup` | Cadangan harian 02.30 WIB, terenkripsi AES-256, disimpan 30 hari di `backups/` |

Pemulihan: `sh scripts/pulihkan.sh backups/<berkas>.sql.gz.enc`. Kode perangkat bawaan: `fk-a/panel-l1`, `fk-a/panel-l2`, `fk-a/panel-l3`, `fk-a/panel-lab`, `fk-a/inverter`, `fkip-v/utama`.

## Video panduan

Video di menu Panduan dibuat ulang dengan satu perintah: rekaman layar aplikasi sungguhan (server lokal berdata contoh), narasi ElevenLabs, teks keterangan VTT, dan gambar sampul.

```bash
python -m pip install playwright imageio-ffmpeg
python tools/video/buat_video.py
```

Narasi membutuhkan `ELEVENLABS_API_KEY` di variabel lingkungan (opsional: `ELEVENLABS_VOICE_ID`). Tambahkan `--tanpa-suara` untuk versi teks keterangan saja.

## Dokumentasi

- [docs/SOP.md](docs/SOP.md): prosedur harian pengelola dan piket, tugas tim, penanganan gangguan, cadangan, latihan pemulihan, serah terima kepengurusan.
- [docs/TEKNIS.md](docs/TEKNIS.md): arsitektur, siklus kerja, model, format data masuk, variabel lingkungan.
- [docs/VERIFIKASI.md](docs/VERIFIKASI.md): hasil uji akhir per kebutuhan PRD, uji keamanan, kinerja, aksesibilitas, dan hal yang belum diuji.

## Desain

[PRODUCT.md](PRODUCT.md) dan [DESIGN.md](DESIGN.md) memuat konteks produk dan token desain dari PRD (gaya Vercel, huruf Inter, biru untuk prediksi, kuning untuk surya, merah hanya untuk anomali). Antarmuka tanpa langkah build: HTML, CSS, dan modul JavaScript di `frontend/`.
