"""Papan peringkat, dampak, laporan, pusat belajar."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AgregatJam, Gedung, Pengguna, VersiModel
from ..security import audit, require
from ..services import forecast, impact

router = APIRouter(prefix="/api", tags=["laporan"])


@router.get("/peringkat")
def peringkat(periode: str | None = None, user: Pengguna = Depends(require("dampak.lihat")),
              db: Session = Depends(get_db)):
    p = None
    if periode:
        try:
            p = date.fromisoformat(periode)
        except ValueError:
            raise HTTPException(422, "Format periode harus YYYY-MM-01.")
    return impact.peringkat(db, p)


@router.get("/dampak")
def dampak(user: Pengguna = Depends(require("dampak.lihat")), db: Session = Depends(get_db)):
    return impact.dampak(db)


@router.get("/laporan.csv")
def laporan(mulai: str, selesai: str, user: Pengguna = Depends(require("dampak.lihat")),
            db: Session = Depends(get_db)):
    try:
        a, b = date.fromisoformat(mulai), date.fromisoformat(selesai)
    except ValueError:
        raise HTTPException(422, "Tanggal harus berformat YYYY-MM-DD.")
    if b < a:
        raise HTTPException(422, "Tanggal selesai harus sama atau setelah tanggal mulai.")
    if (b - a).days > 400:
        raise HTTPException(422, "Rentang laporan maksimal 400 hari.")
    isi = impact.laporan_csv(db, a, b)
    audit(db, user.id, "laporan.unduh", f"{a} s.d. {b}")
    db.commit()
    return Response(isi, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="solar-edu-laporan-{a}-{b}.csv"'})


MODUL = [
    {"kode": "P1", "judul": "Membaca profil beban gedung", "prodi": "Teknik Elektro, Teknik Informatika",
     "durasi": "2 x 50 menit",
     "tujuan": "Mengenali beban dasar, beban terjadwal, dan pengaruh suhu dari dataset per jam.",
     "langkah": ["Unduh dataset 30 hari.", "Gambar beban rata-rata per jam untuk hari kerja dan akhir pekan.",
                 "Hitung beban dasar malam hari dan bandingkan dengan beban siang.",
                 "Tulis tiga pola yang kamu temukan beserta dugaan penyebabnya."]},
    {"kode": "P2", "judul": "Melatih Random Forest untuk prakiraan beban", "prodi": "Teknik Informatika",
     "durasi": "3 x 50 menit",
     "tujuan": "Melatih ulang model dengan fitur yang sama seperti sistem dan membandingkan MAPE.",
     "langkah": ["Bagi data: 14 hari terakhir sebagai data uji.",
                 "Latih RandomForestRegressor(n_estimators=300, min_samples_leaf=3).",
                 "Hitung MAE dan MAPE, lalu bandingkan dengan model aktif di halaman ini.",
                 "Coba hapus satu fitur dan catat perubahan akurasinya."]},
    {"kode": "P3", "judul": "Mendeteksi pemborosan dari residu", "prodi": "Teknik Informatika, Teknik Elektro",
     "durasi": "2 x 50 menit",
     "tujuan": "Memahami ambang max(4 kW, 3 x MAD) selama 2 jam dan menguji kepekaannya.",
     "langkah": ["Hitung residu aktual dikurangi prediksi.", "Hitung MAD residu 28 hari.",
                 "Tandai jam yang melewati ambang selama 2 jam atau lebih.",
                 "Bandingkan temuanmu dengan kolom anomali pada dataset."]},
    {"kode": "P4", "judul": "Menghitung biaya dan emisi terhindarkan", "prodi": "Ekonomi, Teknik Sipil",
     "durasi": "2 x 50 menit",
     "tujuan": "Mengubah kWh hemat menjadi rupiah dan kg CO2e serta memahami selisih-dalam-selisih.",
     "langkah": ["Ambil hasil evaluasi dari halaman Dampak.", "Kalikan dengan tarif dan faktor emisi.",
                 "Jelaskan mengapa gedung pembanding diperlukan.",
                 "Susun satu paragraf ringkasan untuk pimpinan kampus."]},
    {"kode": "P5", "judul": "Merancang pesan perubahan perilaku", "prodi": "Ilmu Komunikasi",
     "durasi": "2 x 50 menit",
     "tujuan": "Membuat materi pengingat untuk ruang kuliah berdasarkan anomali yang paling sering muncul.",
     "langkah": ["Pilih satu rekomendasi yang sudah dievaluasi.", "Rancang stiker atau poster pengingat.",
                 "Tentukan cara mengukur apakah pesan itu berhasil.",
                 "Presentasikan hasilnya kepada tim pengelola."]},
]

TOPIK_TA = [
    {"judul": "Perbandingan Random Forest, gradient boosting, dan LSTM untuk prakiraan beban gedung kampus",
     "prodi": "Teknik Informatika"},
    {"judul": "Kalibrasi ambang deteksi anomali berbasis umpan balik penolakan pengelola gedung",
     "prodi": "Teknik Informatika"},
    {"judul": "Analisis kualitas daya dan harmonisa pada panel distribusi gedung percontohan",
     "prodi": "Teknik Elektro"},
    {"judul": "Optimasi sudut dan pembersihan modul surya terhadap produksi PLTS atap kampus",
     "prodi": "Teknik Elektro"},
    {"judul": "Pengaruh selubung bangunan terhadap beban pendingin ruang kuliah di iklim tropis",
     "prodi": "Teknik Sipil, Arsitektur"},
    {"judul": "Analisis biaya-manfaat replikasi sistem pemantauan energi ke gedung lain", "prodi": "Ekonomi"},
    {"judul": "Efektivitas pesan pengingat terhadap keberlanjutan perilaku hemat energi mahasiswa",
     "prodi": "Ilmu Komunikasi"},
]

KAMUS = [
    {"kolom": "waktu_wib", "arti": "Awal jam pengukuran, zona waktu WIB"},
    {"kolom": "beban_kw", "arti": "Rerata daya seluruh panel gedung selama satu jam (kW)"},
    {"kolom": "produksi_pv_kw", "arti": "Rerata daya keluaran inverter panel surya (kW)"},
    {"kolom": "suhu_c", "arti": "Suhu udara luar (°C)"},
    {"kolom": "radiasi_w_m2", "arti": "Radiasi matahari global horizontal (W/m²)"},
    {"kolom": "ruang_terjadwal", "arti": "Jumlah ruang dengan kelas terjadwal sedikitnya 30 menit dalam jam itu"},
    {"kolom": "kelengkapan", "arti": "Porsi pembacaan valid dalam jam itu (0 sampai 1)"},
    {"kolom": "anomali", "arti": "1 bila jam itu bagian dari anomali yang tercatat"},
]


@router.get("/belajar")
def belajar(user: Pengguna = Depends(require("belajar.lihat")), db: Session = Depends(get_db)):
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    kini = datetime.now().replace(minute=0, second=0, microsecond=0)
    contoh = list(db.scalars(select(AgregatJam).where(AgregatJam.gedung_id == g.id,
                                                      AgregatJam.waktu >= kini - timedelta(hours=12))
                             .order_by(AgregatJam.waktu.desc()).limit(12)))
    versi = list(db.scalars(select(VersiModel).order_by(VersiModel.tanggal_latih.desc()).limit(12)))
    return {
        "contoh": [{"waktu": a.waktu.isoformat(), "beban_kw": a.beban_kw, "produksi_pv_kw": a.produksi_pv_kw,
                    "suhu": a.suhu, "radiasi": a.radiasi, "ruang_terjadwal": a.ruang_terjadwal,
                    "kelengkapan": a.kelengkapan, "anomali": a.anomali} for a in contoh],
        "kamus": KAMUS, "modul": MODUL, "topik": TOPIK_TA,
        "model": [{"id": v.id, "tanggal_latih": v.tanggal_latih.isoformat(), "mape": v.mape, "mae": v.mae,
                   "jam_latih": v.jam_latih, "jam_uji": v.jam_uji, "aktif": v.aktif, "catatan": v.catatan,
                   "fitur": [{"fitur": k, "label": forecast.LABEL_FITUR.get(k, k), "bobot": b}
                             for k, b in sorted(v.fitur_penting.items(), key=lambda kv: -kv[1])]}
                  for v in versi],
    }


@router.get("/dataset.csv")
def dataset(hari: int = 90, user: Pengguna = Depends(require("belajar.lihat")), db: Session = Depends(get_db)):
    if not 1 <= hari <= 365:
        raise HTTPException(422, "Jumlah hari harus antara 1 dan 365.")
    isi = impact.dataset_csv(db, hari)
    return Response(isi, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="solar-edu-dataset-{hari}-hari.csv"'})
