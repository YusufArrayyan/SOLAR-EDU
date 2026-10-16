# Dokumentasi teknis SOLAR-EDU AI

## Arsitektur

```
Meter per panel (Modbus) ─┐
Inverter PV (Modbus TCP) ─┴─ Gateway IoT ─TLS─> Mosquitto ─> mqtt_bridge ─> POST /api/ingest
Open-Meteo (prakiraan 48 jam) ─────────────────────────────────────────────> worker (tiap jam)
Jadwal kuliah CSV ─────────────────────────────────────────────────────────> Pengaturan > Jadwal

FastAPI (backend/app) ── PostgreSQL + TimescaleDB ── worker terjadwal (thread)
        └── frontend/ (HTML + CSS + modul JS, tanpa build) di balik Nginx HTTPS
```

| Folder | Isi |
|---|---|
| `backend/app/models.py` | Tabel sesuai ERD PRD. Waktu disimpan naif dalam WIB. |
| `backend/app/services/` | `data_pipeline` (M1–M2), `forecast` (M3), `anomaly` (M4), `recommend` (M5), `notify` (M6), `impact` (M7), `jobs` (siklus kerja), `simulate` (data simulasi) |
| `backend/app/routers/` | API: `auth`, `core` (ringkasan, rekomendasi, tugas, notifikasi), `report` (peringkat, dampak, belajar), `admin` (pengaturan, gedung, jadwal, pengguna, audit, model, ingest) |
| `backend/app/security.py` | Hash kata sandi, sesi, dan **matriks hak akses** (`IZIN`) |
| `backend/app/settings_store.py` | Parameter yang bisa diubah tim (F22) beserta validasinya |
| `frontend/js/views/` | Satu berkas per layar |

## Siklus kerja (`services/jobs.py`)

| Waktu | Pekerjaan |
|---|---|
| Tiap jam | Ambil prakiraan cuaca; agregasi per jam (mode produksi: 3 jam terakhir); cek perangkat diam > 2 jam; deteksi anomali 30 jam terakhir; buat rekomendasi; proses tenggat (pengingat, eskalasi, kedaluwarsa, pemantauan selesai) |
| Harian 02.00 | Prediksi 48 jam ke depan; skor peringkat bulan berjalan |
| Minggu 02.00 | Latih ulang Random Forest dua lintasan, uji mundur 14 hari, simpan versi |
| Senin 07.00 | Email ringkasan mingguan (SMTP; tanpa SMTP tersimpan di kotak keluar) |

## Model

- Fitur: jam, hari, jumlah ruang terjadwal, suhu, dan radiasi. Model: `RandomForestRegressor(n_estimators=300, min_samples_leaf=3)`.
- Pembersihan dua lintasan: residu out-of-bag di atas max(ambang kW, k×MAD) dan jam yang sudah ditandai anomali dibuang sebelum pelatihan ulang.
- Rentang prediksi: persentil 10 dan 90 dari prediksi tiap pohon.
- Berkas model disimpan di `SOLAR_DATA_DIR/models/` (8 versi terakhir). Metrik semua versi tetap tercatat di tabel `model_versi`.
- Rekomendasi yang ditolak mengembalikan jam anomalinya menjadi data normal, sehingga ikut dipelajari pada pelatihan ulang berikutnya.

## Menambah perangkat, ruang, atau gedung

Semuanya lewat **Pengaturan > Gedung**:

- **Perangkat:** kode harus sama dengan topik MQTT `solar/<kode>` atau kolom `perangkat` di `/api/ingest`. Perangkat yang sudah punya data tidak bisa dihapus.
- **Ruang:** nama harus sama persis dengan kolom `ruang` di CSV jadwal; panel pemasok dipakai untuk lokasi rekomendasi.
- **Gedung lain:** untuk papan peringkat antargedung. Konsumsinya diisi per bulan dari tagihan PLN.

Versi 1 dikunci pada satu gedung percontohan. Perluasan termasuk Fase 3 dan butuh kalibrasi ulang ambang.

## Format data masuk

```json
POST /api/ingest   Header: X-Ingest-Token: <INGEST_TOKEN>
[{"perangkat": "fk-a/panel-l2", "waktu": "2026-10-15T08:01:00+07:00", "beban_kw": 12.4},
 {"perangkat": "fk-a/inverter", "waktu": "2026-10-15T08:01:00+07:00", "produksi_pv_kw": 18.2}]
```

Nilai negatif atau di atas `batas_fisik_kw` diberi kualitas 2 dan tidak dipakai. Nginx menutup `/api/ingest` dari luar; hanya jembatan di jaringan internal Docker yang boleh memanggilnya.

## Variabel lingkungan

| Variabel | Bawaan | Arti |
|---|---|---|
| `DATABASE_URL` | SQLite di `backend/data` | `postgresql+psycopg://…` untuk produksi |
| `SOLAR_SIMULATION` | `0` | `0` = produksi (bawaan); `1` = data simulasi dan akun uji untuk pengembangan, sama dengan `run.py --simulasi` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | – | Akun tim pengelola pertama (wajib di produksi) |
| `SOLAR_JOBS` | `min(4, CPU)` | Thread pelatihan Random Forest; set kecil di server 512 MB |
| `WEATHER_LIVE` | `1` di produksi, `0` di simulasi | Prakiraan Open-Meteo. Bila gagal, dipakai cuaca jam yang sama kemarin (persistensi). |
| `SITE_LAT`, `SITE_LON` | Universitas Bengkulu | Lokasi prakiraan cuaca |
| `INGEST_TOKEN` | `dev-ingest-token` | Token jembatan MQTT. **Wajib diganti di produksi.** |
| `COOKIE_SECURE` | `0` | `1` di belakang HTTPS |
| `SESSION_IDLE_MINUTES` | `30` | Sesi berakhir setelah tidak aktif |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | – | Email ringkasan mingguan |
| `PORT`, `HOST` | `8080`, `127.0.0.1` | Server pengembangan |

## Pengujian

`cd backend && python -m pytest -q` menjalankan uji aturan (anomali, indeks, emisi, status, validasi), uji setiap sel matriks hak akses untuk lima peran, alur rekomendasi dari usulan sampai dilaksanakan, log audit yang tidak bisa diubah, impor jadwal, dan dataset tanpa identitas.
