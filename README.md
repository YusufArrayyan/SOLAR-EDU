# SOLAR-EDU AI · versi 1.0.0

Aplikasi web yang membaca konsumsi listrik dan produksi panel surya satu gedung kampus, memprediksi beban 24 jam ke depan dengan Random Forest, menandai pemborosan dari residu prediksi, lalu mengubahnya menjadi rekomendasi yang **selalu diverifikasi manusia**. Dibangun sesuai `PRD SOLAR-EDU AI.docx` (versi 1: delapan modul, lima peran, satu gedung).

> Prototipe berjalan dengan **data simulasi** dan setiap layar diberi label "Data simulasi". Angka-angkanya bukan hasil pengukuran.

## Menjalankan (mode simulasi)

Butuh Python 3.11 atau lebih baru.

```bash
python -m pip install -r backend/requirements.txt
python backend/run.py
```

Buka http://localhost:8080. Saat pertama kali dijalankan, sistem membangkitkan 150 hari data simulasi (sekitar 35 detik), melatih model, dan memutar ulang 60 hari masa pilot. Port bisa diganti lewat variabel `PORT`. Di Windows bisa juga klik ganda `scripts/jalankan.bat`.

### Akun uji (hanya untuk pengembangan lokal)

Semua akun memakai kata sandi yang sama, yaitu `DEMO_PASSWORD` di [backend/app/seed.py](backend/app/seed.py).

| Peran | Email | Layar utama |
|---|---|---|
| Pengelola gedung | pengelola@solar-edu.test | Ringkasan, Rekomendasi |
| Mahasiswa piket | bima.piket@solar-edu.test (juga nadia., sari.) | Tugas dan rekomendasi |
| Tim pengelola | tim@solar-edu.test | Pengaturan, semua layar |
| Pimpinan kampus | pimpinan@solar-edu.test | Dampak, Papan peringkat |
| Mahasiswa dan dosen | mahasiswa@solar-edu.test | Pusat belajar |

Untuk mengulang data simulasi dari awal, hapus folder `backend/data/` lalu jalankan lagi.

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

## Dokumentasi

- [docs/SOP.md](docs/SOP.md): prosedur harian pengelola dan piket, tugas tim, penanganan gangguan, cadangan, latihan pemulihan, serah terima kepengurusan.
- [docs/TEKNIS.md](docs/TEKNIS.md): arsitektur, siklus kerja, model, format data masuk, variabel lingkungan.
- [docs/VERIFIKASI.md](docs/VERIFIKASI.md): hasil uji akhir per kebutuhan PRD, uji keamanan, kinerja, aksesibilitas, dan hal yang belum diuji.

## Desain

[PRODUCT.md](PRODUCT.md) dan [DESIGN.md](DESIGN.md) memuat konteks produk dan token desain dari PRD (gaya Vercel, huruf Inter, biru untuk prediksi, kuning untuk surya, merah hanya untuk anomali). Antarmuka tanpa langkah build: HTML, CSS, dan modul JavaScript di `frontend/`.
