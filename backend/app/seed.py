"""Isi basis data dengan DATA SIMULASI untuk prototipe.

Baseline 90 hari dibangkitkan sekaligus. Masa pilot (60 hari terakhir) diputar ulang hari demi hari dengan
logika sistem yang sama dengan produksi: prediksi, deteksi anomali, rekomendasi, lalu tindakan manusia
yang ditulis sebagai skrip (verifikasi, tolak, tugas piket, evaluasi).

Akun uji (khusus pengembangan lokal). Semua memakai kata sandi DEMO_PASSWORD di bawah.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import config, settings_store
from .db import Base, SessionLocal, engine
from .models import (Gedung, JadwalKuliah, Notifikasi, Pengguna, Perangkat, Rekomendasi, Ruang, SkorPeringkat,
                     Tugas)
from .security import audit, hash_sandi
from .services import data_pipeline, forecast, impact, jobs, recommend, sim_state, simulate

log = logging.getLogger("solar.seed")

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "SolarEdu#2026")  # akun demo publik, bukan akun asli

PENGGUNA = [
    ("Rudi Hartono", "pengelola@solar-edu.test", "pengelola"),
    ("Nadia Putri", "nadia.piket@solar-edu.test", "piket"),
    ("Bima Saputra", "bima.piket@solar-edu.test", "piket"),
    ("Sari Wulandari", "sari.piket@solar-edu.test", "piket"),
    ("Dr. Indra Kusuma", "tim@solar-edu.test", "tim"),
    ("Fajar Ramadhan", "fajar.admin@solar-edu.test", "tim"),
    ("Prof. Hendra Wijaya", "pimpinan@solar-edu.test", "pimpinan"),
    ("Ayu Lestari", "mahasiswa@solar-edu.test", "akademik"),
    ("Dimas Pratama", "dimas.ta@solar-edu.test", "akademik"),
]

GEDUNG_LAIN = [  # untuk papan peringkat antargedung; nilai bulanan dari meter utama kampus (simulasi)
    ("Perpustakaan Pusat", "perpustakaan", 4200, 66, 9.6),
    ("Laboratorium Terpadu", "laboratorium", 2600, 55, 15.8),
    ("Gedung Rektorat", "kantor", 5100, 45, 12.4),
    ("Gedung Kuliah Bersama", "kuliah", 3800, 60, 10.7),
]

ALASAN_TOLAK = {
    "SEMINAR_SABTU": "Seminar fakultas di aula. Kegiatan sah yang tidak tercatat di jadwal kuliah.",
    None: "Sudah dicek di lokasi, tidak ditemukan peralatan menyala. Kemungkinan lonjakan sesaat.",
}
CATATAN_SELESAI = [
    "Sudah dicek, AC dan lampu dimatikan. Stiker pengingat ditempel di pintu.",
    "Saklar utama dimatikan setelah kelas terakhir, dicatat di buku piket.",
    "Sudah dimatikan dan dilaporkan ke satpam jaga malam.",
    "Komputer dimatikan, jadwal pengecekan ditempel di lab.",
]


def _habit(db: Session, rec: Rekomendasi) -> str | None:
    an = rec.anomali
    if not an.perangkat_id:
        return None
    kode = db.get(Perangkat, an.perangkat_id).kode
    cocok = simulate.kebiasaan_cocok(kode, an.mulai)
    return cocok[-1].kode if cocok else None


def buat_struktur(db: Session, pengguna_demo: bool = True) -> tuple[Gedung, Gedung]:
    pilot = Gedung(nama="Gedung A Fakultas Teknik", fungsi="kuliah", luas_m2=3200, jam_operasional_pekan=60,
                   kapasitas_pv_kwp=30, peran="percontohan")
    banding = Gedung(nama="Gedung V FKIP (pembanding)", fungsi="kuliah", luas_m2=3000, jam_operasional_pekan=60,
                     kapasitas_pv_kwp=0, peran="pembanding")
    db.add_all([pilot, banding])
    db.flush()
    nama_panel = {"fk-a/panel-l1": "Panel lantai 1", "fk-a/panel-l2": "Panel lantai 2",
                  "fk-a/panel-l3": "Panel lantai 3", "fk-a/panel-lab": "Panel laboratorium"}
    for kode, nama in nama_panel.items():
        p = Perangkat(gedung_id=pilot.id, kode=kode, nama=nama, jenis="meter", protokol="Modbus RTU ke MQTT",
                      batas_fisik_kw=60)
        db.add(p)
        db.flush()
        for r in simulate.RUANG_PILOT[kode]:
            db.add(Ruang(gedung_id=pilot.id, nama=r, kapasitas=60 if "Lab" not in r else 40, perangkat_id=p.id))
    db.add(Perangkat(gedung_id=pilot.id, kode="fk-a/inverter", nama="Inverter PV 30 kWp", jenis="inverter",
                     protokol="Modbus TCP ke MQTT", batas_fisik_kw=36))
    db.add(Perangkat(gedung_id=banding.id, kode="fkip-v/utama", nama="Meter utama Gedung V", jenis="meter",
                     protokol="Modbus RTU ke MQTT", batas_fisik_kw=150))
    for nama, fungsi, luas, jam, _ in GEDUNG_LAIN:
        db.add(Gedung(nama=nama, fungsi=fungsi, luas_m2=luas, jam_operasional_pekan=jam, peran="lain"))
    db.flush()
    ruang = {r.nama: r for r in db.scalars(select(Ruang))}
    for j in simulate.jadwal_bawaan():
        db.add(JadwalKuliah(ruang_id=ruang[j["ruang"]].id, hari=j["hari"], mulai=j["mulai"], selesai=j["selesai"],
                            mata_kuliah=j["mata_kuliah"]))
    for nama, email, peran in (PENGGUNA if pengguna_demo else []):
        db.add(Pengguna(nama=nama, email=email, peran=peran, hash_sandi=hash_sandi(DEMO_PASSWORD), demo=True,
                        dibuat_pada=datetime.now() - timedelta(days=150)))
    db.flush()
    return pilot, banding


def _skor_gedung_lain(db: Session, bulan: list[date]) -> None:
    acuan = settings_store.get(db, "pembanding_fungsi")
    rng = np.random.default_rng(7)
    for g in db.scalars(select(Gedung).where(Gedung.peran == "lain")):
        dasar = next(x[4] for x in GEDUNG_LAIN if x[0] == g.nama)
        for i, b in enumerate(bulan):
            inten = dasar * (1 + 0.04 * np.sin(i)) * float(rng.uniform(0.96, 1.04))
            db.add(SkorPeringkat(gedung_id=g.id, periode=b, intensitas_wh_m2_jam=round(inten, 2),
                                 indeks_efisiensi=impact.indeks_efisiensi(acuan[g.fungsi], inten)))


def seed(days: int | None = None) -> None:
    days = days or config.SEED_DAYS
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(Gedung.id).limit(1)):
            return
        sekarang = datetime.now()
        jam_kini = simulate.hour_floor(sekarang)
        hari_ini = jam_kini.replace(hour=0)
        mulai = hari_ini - timedelta(days=days)
        pilot_mulai = mulai + timedelta(days=90)
        log.info("Seeding data simulasi %s s.d. %s", mulai, jam_kini)

        pilot, banding = buat_struktur(db)
        sim_state.save(db, {"epoch": hari_ini.isoformat(), "fixed": {}})
        data_pipeline.simpan_cuaca(db, mulai, jam_kini + timedelta(hours=49))
        db.commit()

        # ---- baseline 90 hari (Fase 1), tanpa rekomendasi
        t = mulai
        while t < pilot_mulai:  # per pekan agar memori tetap kecil
            jobs.simulasikan(db, t, min(t + timedelta(days=7), pilot_mulai))
            db.commit()
            t += timedelta(days=7)
        forecast.latih(db, pilot, pilot_mulai, "Model awal dari baseline Fase 1.")
        db.commit()

        # ---- masa pilot, diputar ulang per hari
        rencana: list[tuple[datetime, str, str]] = []  # (waktu, aksi, rekomendasi_id)
        sudah_abaikan: set[str] = set()
        hari = pilot_mulai
        while hari <= hari_ini:
            akhir_hari = min(hari + timedelta(days=1), jam_kini)
            # 1) tindakan manusia yang jatuh pada hari ini
            for waktu, aksi, rid in sorted([r for r in rencana if r[0] < hari + timedelta(days=1)]):
                if waktu > sekarang:
                    continue
                _jalankan(db, aksi, rid, waktu)
            rencana = [r for r in rencana if r[0] >= hari + timedelta(days=1)]
            db.commit()
            # 2) pekerjaan 02.00: latih ulang Minggu, prediksi 48 jam, tenggat
            t2 = hari + timedelta(hours=2)
            if hari.weekday() == 6 and t2 <= sekarang:
                try:
                    forecast.latih(db, pilot, t2, "Latih ulang mingguan terjadwal.")
                except ValueError:
                    pass
            forecast.prediksi(db, pilot, hari, 48)
            recommend.proses_tenggat(db, min(t2, sekarang))
            db.commit()
            # 3) data hari ini
            if akhir_hari > hari:
                jobs.simulasikan(db, hari, akhir_hari)
            db.commit()
            # 4) deteksi pada akhir hari (atau sekarang) lalu buat rekomendasi
            t_det = min(hari + timedelta(days=1, hours=2), sekarang)
            baru = jobs.deteksi_dan_rekomendasi(db, pilot, hari - timedelta(hours=12),
                                                simulate.hour_floor(akhir_hari), t_det)
            db.commit()
            for rec in baru:
                rencana += _rencanakan(db, rec, sekarang, sudah_abaikan)
            for gd in (pilot, banding):
                impact.hitung_skor_bulanan(db, gd, date(hari.year, hari.month, 1))
            db.commit()
            hari += timedelta(days=1)

        # sisa tindakan yang sudah lewat
        for waktu, aksi, rid in sorted(rencana):
            if waktu <= sekarang:
                _jalankan(db, aksi, rid, waktu)
        recommend.proses_tenggat(db, sekarang)
        forecast.prediksi(db, pilot, jam_kini, 48)

        bulan = sorted({b for b in db.scalars(select(SkorPeringkat.periode).distinct())})
        _skor_gedung_lain(db, bulan)
        # notifikasi lebih dari 2 hari dianggap sudah dibaca
        db.execute(update(Notifikasi).where(Notifikasi.waktu < sekarang - timedelta(days=2)).values(dibaca=True))
        audit(db, None, "sistem.seed", f"Data simulasi {days} hari dibuat.")
        db.commit()
        log.info("Seeding selesai")


def _rencanakan(db: Session, rec: Rekomendasi, sekarang: datetime, sudah_abaikan: set[str]):
    rng = np.random.default_rng(rec.nomor * 13)
    t0 = rec.dibuat_pada
    umur = sekarang - t0
    habit = _habit(db, rec)
    if habit == "SEMINAR_SABTU" or habit is None:
        return [(t0 + timedelta(hours=float(rng.uniform(3, 9))), "tolak", rec.id)]
    if habit == "AC_L3_SIANG" and habit not in sudah_abaikan:
        sudah_abaikan.add(habit)
        return []  # tidak direspons, menjadi Kedaluwarsa setelah 7 hari
    if umur < timedelta(hours=30):
        return []  # masih menunggu verifikasi
    tv = t0 + timedelta(hours=float(rng.uniform(3, 14)))
    out = [(tv, "verifikasi", rec.id)]
    if umur < timedelta(days=3.5):
        return out  # tugas belum dilaksanakan
    td = tv + timedelta(hours=float(rng.uniform(4, 30)))
    out.append((td, "selesai", rec.id))
    te = (td + timedelta(days=15)).replace(hour=9, minute=15)
    if te < sekarang - timedelta(days=3):
        out.append((te, "evaluasi", rec.id))
    return out


def _jalankan(db: Session, aksi: str, rid: str, waktu: datetime) -> None:
    rec = db.get(Rekomendasi, rid)
    pengelola = db.scalar(select(Pengguna).where(Pengguna.peran == "pengelola"))
    try:
        if aksi == "tolak" and rec.status == "Diusulkan":
            recommend.tolak(db, rec, pengelola, ALASAN_TOLAK.get(_habit(db, rec), ALASAN_TOLAK[None]), waktu)
        elif aksi == "verifikasi" and rec.status == "Diusulkan":
            recommend.verifikasi(db, rec, pengelola, waktu=waktu)
        elif aksi == "selesai" and rec.status == "Diverifikasi":
            t = db.scalar(select(Tugas).where(Tugas.rekomendasi_id == rec.id, Tugas.selesai_pada.is_(None)))
            if t:
                recommend.tandai_selesai(db, t, t.pelaksana, CATATAN_SELESAI[rec.nomor % len(CATATAN_SELESAI)], waktu)
        elif aksi == "evaluasi" and rec.status == "Dilaksanakan":
            recommend.catat_evaluasi(db, rec, pengelola, "Penurunan konsumsi terlihat setelah tindakan.", waktu)
    except (ValueError, recommend.TransisiTidakSah) as e:
        log.warning("Aksi %s R-%s dilewati: %s", aksi, rec.nomor, e)


def pastikan_admin(wajib: bool = False) -> None:
    """Buat akun admin asli (peran tim pengelola) dari ADMIN_EMAIL dan ADMIN_PASSWORD bila belum ada.

    Dipakai di kedua mode: di mode demo, akun ini berdampingan dengan akun demo tetapi tidak bisa
    disentuh atau dilihat oleh akun demo.
    """
    email, sandi = os.getenv("ADMIN_EMAIL", "").strip().lower(), os.getenv("ADMIN_PASSWORD", "")
    if not email or not sandi:
        if wajib:
            raise RuntimeError("Isi ADMIN_EMAIL dan ADMIN_PASSWORD (minimal 10 karakter) untuk pemasangan pertama.")
        return
    if len(sandi) < 10:
        raise RuntimeError("ADMIN_PASSWORD minimal 10 karakter.")
    with SessionLocal() as db:
        if db.scalar(select(Pengguna.id).where(func.lower(Pengguna.email) == email)):
            return  # sudah ada; kata sandi tidak ditimpa agar perubahan dari halaman Akun tetap berlaku
        nama = os.getenv("ADMIN_NAMA", "Admin tim pengelola").strip() or "Admin tim pengelola"
        db.add(Pengguna(nama=nama, email=email, peran="tim", hash_sandi=hash_sandi(sandi), demo=False))
        audit(db, None, "pengguna.admin_awal", "Akun admin asli dibuat dari variabel lingkungan.")
        db.commit()


def siapkan_produksi() -> None:
    """Mode produksi: struktur gedung, perangkat, jadwal awal, dan akun admin asli. Data energi lewat MQTT."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(Gedung.id).limit(1)):
            buat_struktur(db, pengguna_demo=False)
            audit(db, None, "sistem.pasang", "Pemasangan awal mode produksi.")
            db.commit()
    pastikan_admin(wajib=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
