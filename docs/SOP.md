# SOP operasional SOLAR-EDU AI

Prosedur ini dipakai pengurus untuk menjalankan sistem sehari-hari dan saat serah terima antargenerasi. Sistem hanya mengusulkan; tidak ada perangkat yang dikendalikan otomatis.

## 1. Pengelola gedung (harian, sekitar 10 menit)

1. Buka **Ringkasan** pada pagi hari. Peringatan anomali selalu tampil paling atas.
2. Buka **Rekomendasi**, lalu filter **Diusulkan**. Untuk setiap rekomendasi:
   - Baca alasan, grafik aktual dan prediksi, serta panel yang dicurigai.
   - Bila masuk akal, pilih pelaksana dan batas waktu, lalu tekan **Verifikasi rekomendasi**.
   - Bila tidak, tekan **Tolak rekomendasi…** dan tulis alasannya, misalnya ada seminar di luar jadwal kuliah. Alasan ini wajib diisi dan dipakai untuk mengkalibrasi ambang.
   - Target: setiap rekomendasi diputuskan dalam 24 jam. Rekomendasi tanpa respons selama 7 hari otomatis menjadi Kedaluwarsa.
3. Tanggapi notifikasi **eskalasi**, yaitu tugas yang melewati batas waktu: hubungi pelaksana atau tetapkan ulang.
4. Rekomendasi yang pemantauan 14 harinya sudah selesai akan memunculkan notifikasi **Siap dievaluasi**. Buka rekomendasinya, periksa angka sebelum dan sesudah yang sudah terisi otomatis, lalu tekan **Catat hasil**.

## 2. Mahasiswa piket

1. Masuk, lalu buka **Tugas dan rekomendasi**.
2. Datangi lokasi, lakukan tindakan, misalnya mematikan AC dan lampu, lalu tekan **Tandai sudah dilaksanakan**.
3. Tulis catatan bukti yang jelas: ruang yang dicek, jam, dan apa yang dilakukan.
4. Jangan mengubah instalasi listrik. Kerusakan atau bahaya dilaporkan ke teknisi gedung.

## 3. Tim pengelola

| Kapan | Tugas |
|---|---|
| Awal semester | Impor jadwal kuliah (Pengaturan > Jadwal kuliah). Periksa baris yang ditandai salah. Perbarui akun piket: tambah anggota baru, nonaktifkan yang sudah selesai. |
| Mingguan (Senin) | Baca email ringkasan mingguan. Periksa Pengaturan > Status sistem: semua perangkat Aktif dan kelengkapan data ≥ 95 %. |
| Mingguan (otomatis) | Model dilatih ulang Minggu 02.00 WIB. Periksa Pusat belajar > Riwayat versi model. Versi baru dipakai bila MAPE ≤ 110 % model lama. |
| Bulanan | Tinjau presisi anomali di Dampak > Indikator keberhasilan. Bila banyak penolakan dengan alasan serupa, naikkan ambang atau kelipatan MAD di Parameter. |
| Akhir semester | Unduh laporan CSV (Dampak > Laporan CSV), susun laporan evaluasi, lakukan latihan pemulihan cadangan (bagian 5), dan serah terima kepengurusan (bagian 6). |

Perubahan tarif listrik atau faktor emisi diisi di **Pengaturan > Parameter** setelah ada data resmi terbaru. Setiap perubahan tercatat di log audit.

## 4. Gangguan data

| Gejala | Tindakan |
|---|---|
| Notifikasi "Data … belum masuk" | Cek daya dan jaringan gateway gedung, lalu periksa log jembatan: `docker compose logs bridge`. |
| Prakiraan cuaca gagal diambil | Sistem otomatis memakai prakiraan cadangan. Cek akses internet server ke penyedia cuaca. |
| Banyak nilai ditandai tidak wajar | Minta Teknik Elektro mengkalibrasi meter. Nilai negatif atau di atas batas fisik dibuang otomatis (kualitas 2). |
| Dashboard tidak bisa dibuka | `docker compose ps`, lalu `docker compose restart app`. |

## 5. Cadangan dan pemulihan

- Cadangan otomatis dibuat setiap hari pukul 02.30 WIB di `backups/`, terenkripsi AES-256 dengan `BACKUP_PASSPHRASE`, dan disimpan 30 hari. Folder `backups/` harus dipasang ke penyimpanan yang terpisah dari server.
- Simpan `BACKUP_PASSPHRASE` di dua tempat aman yang berbeda. Tanpa frasa itu, cadangan tidak bisa dibuka.
- Untuk memulihkan: `sh scripts/pulihkan.sh backups/solar-YYYYMMDD-0230.sql.gz.enc`. Targetnya pemulihan penuh dalam 4 jam.
- **Latihan pemulihan tiap semester:** pulihkan cadangan terbaru di server uji, masuk, lalu cocokkan jumlah rekomendasi dan entri log audit dengan server utama. Catat hasilnya di laporan semester.

## 6. Serah terima kepengurusan

1. Pengurus lama menambahkan akun pengurus baru dengan peran Tim pengelola.
2. Bersama-sama, jalankan seluruh SOP ini satu kali.
3. Serahkan: isi `.env` (melalui pengelola kata sandi kampus, bukan chat), lokasi cadangan, sertifikat, dan kontak teknisi gedung.
4. Pengurus lama menonaktifkan akunnya sendiri melalui akun pengurus baru.
5. Dosen pembina memastikan serah terima tercatat di laporan semester.
