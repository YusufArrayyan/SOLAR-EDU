"""Siklus kerja data (PRD: diagram siklus harian) dan worker terjadwal."""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import config
from ..db import SessionLocal
from ..models import AgregatJam, Anomali, Gedung, Perangkat, PeristiwaData, Prediksi, Rekomendasi, VersiModel
from . import anomaly, data_pipeline, forecast, impact, notify, recommend, sim_state, simulate

log = logging.getLogger("solar.jobs")
STATUS: dict = {"terakhir_jam": None, "terakhir_harian": None, "terakhir_latih": None, "galat": None}


def gedung_pilot(db: Session) -> Gedung:
    return db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))


def gedung_meter(db: Session) -> list[Gedung]:
    return list(db.scalars(select(Gedung).where(Gedung.peran.in_(["percontohan", "pembanding"]))))


def _perangkat_dict(db: Session, g: Gedung) -> list[dict]:
    return [{"id": p.id, "kode": p.kode, "jenis": p.jenis} for p in db.scalars(
        select(Perangkat).where(Perangkat.gedung_id == g.id))]


def simulasikan(db: Session, mulai: datetime, selesai: datetime, catat_hilang: bool = False) -> int:
    """Mode simulasi: bangkitkan pembacaan semua perangkat untuk [mulai, selesai), lalu agregasi."""
    state = sim_state.get(db)
    if state is None or selesai <= mulai:
        return 0
    jadwal = data_pipeline.jadwal_dict(db)
    n = 0
    for g in gedung_meter(db):
        rows = simulate.bangkitkan_pembacaan(_perangkat_dict(db, g), mulai, selesai, jadwal, state,
                                             g.kapasitas_pv_kwp)
        n += data_pipeline.simpan_pembacaan(db, rows)
    for g in gedung_meter(db):
        data_pipeline.agregasi(db, g, simulate.hour_floor(mulai), simulate.hour_floor(selesai),
                               60 // simulate.STEP_MIN,
                               catat_jam=simulate.hour_floor(selesai) - timedelta(hours=1) if catat_hilang else None)
    return n


def perbarui_cuaca(db: Session, sekarang: datetime) -> None:
    """F02: prakiraan 48 jam; kegagalan API memicu peringatan admin dan jatuh ke prakiraan cadangan."""
    awal = simulate.hour_floor(sekarang) - timedelta(hours=3)
    akhir = simulate.hour_floor(sekarang) + timedelta(hours=49)
    if config.WEATHER_LIVE:
        try:
            data = data_pipeline.ambil_cuaca_open_meteo(config.SITE_LAT, config.SITE_LON)
            data_pipeline.simpan_cuaca(db, awal, akhir, "open-meteo", [d for d in data if awal <= d[0] < akhir])
            return
        except Exception as e:  # noqa: BLE001
            data_pipeline.catat_peristiwa(db, "cuaca_gagal", str(e)[:300])
            notify.ke_peran(db, ["tim"], "galat_data", "Prakiraan cuaca gagal diambil",
                            "Sistem memakai prakiraan cadangan dari cuaca jam yang sama kemarin. "
                            "Cek koneksi server ke penyedia cuaca.", "#/pengaturan?tab=sistem", waktu=sekarang)
    if config.SIMULATION:
        data_pipeline.simpan_cuaca(db, awal, akhir, "simulasi")
    else:
        data_pipeline.isi_cuaca_cadangan(db, awal, akhir)


def cek_perangkat_diam(db: Session, sekarang: datetime) -> None:
    """Peringatan bila meter atau inverter tidak mengirim data lebih dari 2 jam."""
    for p in db.scalars(select(Perangkat)):
        if p.terakhir_lapor and sekarang - p.terakhir_lapor > timedelta(hours=2):
            if p.status_terakhir != "diam":
                p.status_terakhir = "diam"
                data_pipeline.catat_peristiwa(db, "perangkat_diam", f"{p.nama} sejak {p.terakhir_lapor:%H.%M}")
                notify.ke_peran(db, ["tim", "pengelola"], "galat_data", f"Data {p.nama} belum masuk",
                                f"Data belum masuk sejak {p.terakhir_lapor:%H.%M}. Cek koneksi gateway, "
                                "lalu muat ulang.", "#/pengaturan", waktu=sekarang)


def deteksi_dan_rekomendasi(db: Session, g: Gedung, mulai: datetime, selesai: datetime,
                            sekarang: datetime) -> list[Rekomendasi]:
    anomaly.deteksi(db, g, mulai, selesai, sekarang)
    db.flush()
    baru = []
    tanpa_rek = db.scalars(select(Anomali).where(Anomali.gedung_id == g.id, Anomali.status == "baru",
                                                 Anomali.dibuat_pada >= sekarang - timedelta(days=2),
                                                 ~Anomali.id.in_(select(Rekomendasi.anomali_id))))
    for an in list(tanpa_rek):
        if an.selesai >= simulate.hour_floor(sekarang):
            continue  # masih berlangsung; tunggu sampai selesai agar kelebihan kWh lengkap
        r = recommend.buat_dari_anomali(db, an, waktu=sekarang)
        if r:
            baru.append(r)
    return baru


def siklus_jam(db: Session, sekarang: datetime | None = None) -> None:
    sekarang = sekarang or datetime.now()
    jam = simulate.hour_floor(sekarang)
    perbarui_cuaca(db, sekarang)
    if config.SIMULATION:
        g = gedung_pilot(db)
        terakhir = db.scalar(select(AgregatJam.waktu).where(AgregatJam.gedung_id == g.id)
                             .order_by(AgregatJam.waktu.desc()).limit(1))
        mulai = (terakhir + timedelta(hours=1)) if terakhir else jam - timedelta(days=1)
        simulasikan(db, mulai, jam, catat_hilang=True)
    else:
        # data nyata masuk lewat /api/ingest; agregasi ulang 3 jam terakhir agar paket terlambat ikut terhitung
        for gd in gedung_meter(db):
            data_pipeline.agregasi(db, gd, jam - timedelta(hours=3), jam, 60, catat_jam=jam - timedelta(hours=3))
    cek_perangkat_diam(db, sekarang)
    g = gedung_pilot(db)
    # pastikan selalu ada prediksi untuk 24 jam ke depan
    if forecast.model_aktif(db):
        ada = db.scalar(select(Prediksi.waktu_target).where(Prediksi.gedung_id == g.id)
                        .order_by(Prediksi.waktu_target.desc()).limit(1))
        if ada is None or ada < jam + timedelta(hours=24):
            forecast.prediksi(db, g, jam, 48)
    deteksi_dan_rekomendasi(db, g, jam - timedelta(hours=30), jam, sekarang)
    recommend.proses_tenggat(db, sekarang)
    # sesi yang sudah lama tidak aktif dihapus
    from ..config import SESSION_IDLE_MINUTES
    from ..models import Sesi
    db.execute(delete(Sesi).where(Sesi.terakhir_aktif < sekarang - timedelta(minutes=SESSION_IDLE_MINUTES)))
    STATUS["terakhir_jam"] = sekarang.isoformat()


def siklus_harian(db: Session, sekarang: datetime | None = None, latih: bool | None = None) -> None:
    """02.00 WIB: latih ulang (Minggu), prediksi 48 jam, skor bulanan."""
    sekarang = sekarang or datetime.now()
    g = gedung_pilot(db)
    if latih is None:
        aktif = forecast.model_aktif(db)
        sudah = db.scalar(select(VersiModel.id).where(
            VersiModel.tanggal_latih >= sekarang.replace(hour=0, minute=0, second=0, microsecond=0)).limit(1))
        latih = aktif is None or (sekarang.weekday() == 6 and sudah is None)
    if latih:
        try:
            forecast.latih(db, g, sekarang, "Latih ulang mingguan terjadwal.")
            STATUS["terakhir_latih"] = sekarang.isoformat()
        except ValueError as e:
            # saat masih mengumpulkan data, cukup dicatat sekali per pekan agar daftar peristiwa tidak banjir
            sudah = db.scalar(select(PeristiwaData.id).where(PeristiwaData.jenis == "latih_gagal",
                                                            PeristiwaData.waktu >= sekarang - timedelta(days=7)).limit(1))
            if not sudah:
                data_pipeline.catat_peristiwa(db, "latih_gagal", str(e))
    hari_ini = sekarang.replace(hour=0, minute=0, second=0, microsecond=0)
    forecast.prediksi(db, g, hari_ini + timedelta(hours=sekarang.hour), 48)
    for gd in gedung_meter(db):
        impact.hitung_skor_bulanan(db, gd, date(sekarang.year, sekarang.month, 1))
    STATUS["terakhir_harian"] = sekarang.isoformat()


class Worker(threading.Thread):
    """Penjadwal sederhana: tiap menit memeriksa apakah ada pekerjaan jam, harian, atau mingguan."""

    def __init__(self):
        super().__init__(daemon=True, name="solar-worker")
        self._stop = threading.Event()
        self._jam = None
        self._harian = None
        self._email = None

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self.tick()
                STATUS["galat"] = None
            except Exception as e:  # noqa: BLE001
                log.exception("worker gagal")
                STATUS["galat"] = str(e)[:300]
            self._stop.wait(60)

    def tick(self):
        now = datetime.now()
        with SessionLocal() as db:
            if self._jam != simulate.hour_floor(now):
                siklus_jam(db, now)
                db.commit()
                self._jam = simulate.hour_floor(now)
            if now.hour >= 2 and self._harian != now.date():
                siklus_harian(db, now)
                db.commit()
                self._harian = now.date()
            if now.weekday() == 0 and now.hour >= 7 and self._email != now.date():
                notify.kirim_ringkasan_mingguan(db, gedung_pilot(db).id)
                db.commit()
                self._email = now.date()
