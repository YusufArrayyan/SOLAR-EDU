"""Model data sesuai ERD pada PRD.

Seluruh waktu disimpan sebagai datetime naif dalam WIB (Asia/Jakarta, UTC+7, tanpa DST).
"""
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text,
                        event, JSON)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Gedung(Base):
    __tablename__ = "gedung"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nama: Mapped[str] = mapped_column(String(120))
    fungsi: Mapped[str] = mapped_column(String(40))  # kuliah, laboratorium, kantor, perpustakaan
    luas_m2: Mapped[float] = mapped_column(Float)
    jam_operasional_pekan: Mapped[float] = mapped_column(Float)
    kapasitas_pv_kwp: Mapped[float] = mapped_column(Float, default=0)
    peran: Mapped[str] = mapped_column(String(20), default="lain")  # percontohan | pembanding | lain

    ruang = relationship("Ruang", back_populates="gedung")
    perangkat = relationship("Perangkat", back_populates="gedung")


class Perangkat(Base):
    __tablename__ = "perangkat"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"))
    kode: Mapped[str] = mapped_column(String(40), unique=True)  # topik MQTT, mis. "fk-a/panel-l2"
    nama: Mapped[str] = mapped_column(String(80))
    jenis: Mapped[str] = mapped_column(String(20))  # meter | inverter
    protokol: Mapped[str] = mapped_column(String(20), default="Modbus/MQTT")
    status_terakhir: Mapped[str] = mapped_column(String(20), default="aktif")
    terakhir_lapor: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batas_fisik_kw: Mapped[float] = mapped_column(Float, default=100.0)

    gedung = relationship("Gedung", back_populates="perangkat")


class Ruang(Base):
    __tablename__ = "ruang"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"))
    nama: Mapped[str] = mapped_column(String(60))
    kapasitas: Mapped[int] = mapped_column(Integer, default=40)
    perangkat_id: Mapped[str | None] = mapped_column(ForeignKey("perangkat.id"), nullable=True)  # panel pemasok

    gedung = relationship("Gedung", back_populates="ruang")


class Pengukuran(Base):
    __tablename__ = "pengukuran"
    waktu: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    perangkat_id: Mapped[str] = mapped_column(ForeignKey("perangkat.id"), primary_key=True)
    beban_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    produksi_pv_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    kualitas: Mapped[int] = mapped_column(SmallInteger, default=0)  # 0 valid, 1 diperbaiki, 2 dibuang


class AgregatJam(Base):
    """Agregat per jam gedung beserta fitur model."""
    __tablename__ = "agregat_jam"
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"), primary_key=True)
    waktu: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    beban_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    produksi_pv_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    suhu: Mapped[float | None] = mapped_column(Float, nullable=True)
    radiasi: Mapped[float | None] = mapped_column(Float, nullable=True)
    ruang_terjadwal: Mapped[int] = mapped_column(Integer, default=0)
    kelengkapan: Mapped[float] = mapped_column(Float, default=1.0)  # porsi pembacaan valid dalam jam itu
    anomali: Mapped[bool] = mapped_column(Boolean, default=False)


class Cuaca(Base):
    __tablename__ = "cuaca"
    waktu: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    suhu: Mapped[float] = mapped_column(Float)
    radiasi: Mapped[float] = mapped_column(Float)  # W/m2
    sumber: Mapped[str] = mapped_column(String(30), default="simulasi")
    diambil_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class JadwalKuliah(Base):
    __tablename__ = "jadwal_kuliah"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ruang_id: Mapped[str] = mapped_column(ForeignKey("ruang.id"))
    mata_kuliah: Mapped[str] = mapped_column(String(120), default="")
    hari: Mapped[int] = mapped_column(Integer)  # 0 Senin ... 6 Minggu
    mulai: Mapped[str] = mapped_column(String(5))  # "07:30"
    selesai: Mapped[str] = mapped_column(String(5))

    ruang = relationship("Ruang")


class VersiModel(Base):
    __tablename__ = "model_versi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    algoritma: Mapped[str] = mapped_column(String(80), default="RandomForestRegressor")
    tanggal_latih: Mapped[datetime] = mapped_column(DateTime)
    mape: Mapped[float] = mapped_column(Float)
    mae: Mapped[float] = mapped_column(Float)
    jam_latih: Mapped[int] = mapped_column(Integer)
    jam_uji: Mapped[int] = mapped_column(Integer)
    aktif: Mapped[bool] = mapped_column(Boolean, default=False)
    fitur_penting: Mapped[dict] = mapped_column(JSON, default=dict)
    catatan: Mapped[str] = mapped_column(Text, default="")
    berkas: Mapped[str] = mapped_column(String(255), default="")


class Prediksi(Base):
    __tablename__ = "prediksi"
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"), primary_key=True)
    waktu_target: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_versi.id"))
    nilai_kw: Mapped[float] = mapped_column(Float)
    batas_bawah: Mapped[float] = mapped_column(Float)
    batas_atas: Mapped[float] = mapped_column(Float)
    pv_kw: Mapped[float] = mapped_column(Float, default=0)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Anomali(Base):
    __tablename__ = "anomali"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"))
    mulai: Mapped[datetime] = mapped_column(DateTime)
    selesai: Mapped[datetime] = mapped_column(DateTime)
    kelebihan_kwh: Mapped[float] = mapped_column(Float)
    puncak_residu_kw: Mapped[float] = mapped_column(Float, default=0)
    ruang_terjadwal: Mapped[int] = mapped_column(Integer, default=0)
    perangkat_id: Mapped[str | None] = mapped_column(ForeignKey("perangkat.id"), nullable=True)
    aturan: Mapped[str] = mapped_column(String(30), default="residu")  # residu | jadwal
    status: Mapped[str] = mapped_column(String(20), default="baru")  # baru | valid | tidak_valid
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    perangkat = relationship("Perangkat")


class Pengguna(Base):
    __tablename__ = "pengguna"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nama: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    peran: Mapped[str] = mapped_column(String(20))  # pengelola | piket | tim | pimpinan | akademik
    hash_sandi: Mapped[str] = mapped_column(String(255))
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    email_mingguan: Mapped[bool] = mapped_column(Boolean, default=True)
    notif_aplikasi: Mapped[bool] = mapped_column(Boolean, default=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)  # akun uji publik; dibatasi terhadap akun asli
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Sesi(Base):
    __tablename__ = "sesi"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    pengguna_id: Mapped[str] = mapped_column(ForeignKey("pengguna.id", ondelete="CASCADE"))
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    terakhir_aktif: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Rekomendasi(Base):
    __tablename__ = "rekomendasi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nomor: Mapped[int] = mapped_column(Integer, default=0)
    anomali_id: Mapped[str] = mapped_column(ForeignKey("anomali.id"))
    judul: Mapped[str] = mapped_column(String(200))
    alasan: Mapped[str] = mapped_column(Text)
    fitur_penting: Mapped[list] = mapped_column(JSON, default=list)
    lokasi: Mapped[str] = mapped_column(String(120), default="")
    estimasi_hemat_kwh: Mapped[float] = mapped_column(Float)
    peluang_berulang: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="Diusulkan")
    pelaksana_disarankan_id: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    diverifikasi_oleh: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    diverifikasi_pada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    alasan_tolak: Mapped[str | None] = mapped_column(Text, nullable=True)
    dilaksanakan_pada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dievaluasi_pada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    anomali = relationship("Anomali")
    pelaksana_disarankan = relationship("Pengguna", foreign_keys=[pelaksana_disarankan_id])
    verifikator = relationship("Pengguna", foreign_keys=[diverifikasi_oleh])
    tugas = relationship("Tugas", back_populates="rekomendasi", order_by="Tugas.batas_waktu")
    evaluasi = relationship("Evaluasi", back_populates="rekomendasi", uselist=False)
    riwayat = relationship("RiwayatStatus", order_by="RiwayatStatus.waktu")


class RiwayatStatus(Base):
    __tablename__ = "riwayat_status"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rekomendasi_id: Mapped[str] = mapped_column(ForeignKey("rekomendasi.id"))
    dari: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ke: Mapped[str] = mapped_column(String(20))
    oleh_id: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    catatan: Mapped[str] = mapped_column(Text, default="")

    oleh = relationship("Pengguna")


class Tugas(Base):
    __tablename__ = "tugas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rekomendasi_id: Mapped[str] = mapped_column(ForeignKey("rekomendasi.id"))
    pelaksana_id: Mapped[str] = mapped_column(ForeignKey("pengguna.id"))
    batas_waktu: Mapped[datetime] = mapped_column(DateTime)
    selesai_pada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    catatan_bukti: Mapped[str] = mapped_column(Text, default="")
    pengingat_terkirim: Mapped[int] = mapped_column(Integer, default=0)
    dieskalasi: Mapped[bool] = mapped_column(Boolean, default=False)

    rekomendasi = relationship("Rekomendasi", back_populates="tugas")
    pelaksana = relationship("Pengguna")


class Evaluasi(Base):
    __tablename__ = "evaluasi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rekomendasi_id: Mapped[str] = mapped_column(ForeignKey("rekomendasi.id"), unique=True)
    konsumsi_sebelum_kwh: Mapped[float] = mapped_column(Float)
    konsumsi_sesudah_kwh: Mapped[float] = mapped_column(Float)
    pembanding_sebelum_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    pembanding_sesudah_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    hemat_kwh: Mapped[float] = mapped_column(Float)  # selisih-dalam-selisih
    catatan: Mapped[str] = mapped_column(Text, default="")
    dicatat_oleh: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    rekomendasi = relationship("Rekomendasi", back_populates="evaluasi")


class SkorPeringkat(Base):
    __tablename__ = "skor_peringkat"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id"))
    periode: Mapped[datetime] = mapped_column(Date)
    intensitas_wh_m2_jam: Mapped[float] = mapped_column(Float)
    indeks_efisiensi: Mapped[float] = mapped_column(Float)

    gedung = relationship("Gedung")


class KonsumsiBulanan(Base):
    """Konsumsi bulanan gedung tanpa meter (dari tagihan PLN) untuk papan peringkat antargedung."""
    __tablename__ = "konsumsi_bulanan"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gedung_id: Mapped[str] = mapped_column(ForeignKey("gedung.id", ondelete="CASCADE"))
    periode: Mapped[datetime] = mapped_column(Date)
    kwh: Mapped[float] = mapped_column(Float)
    sumber: Mapped[str] = mapped_column(String(60), default="tagihan PLN")
    dicatat_oleh: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Notifikasi(Base):
    __tablename__ = "notifikasi"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pengguna_id: Mapped[str] = mapped_column(ForeignKey("pengguna.id", ondelete="CASCADE"))
    jenis: Mapped[str] = mapped_column(String(30))
    judul: Mapped[str] = mapped_column(String(200))
    isi: Mapped[str] = mapped_column(Text, default="")
    tautan: Mapped[str] = mapped_column(String(200), default="")
    dibaca: Mapped[bool] = mapped_column(Boolean, default=False)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LogAudit(Base):
    __tablename__ = "log_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pengguna_id: Mapped[str | None] = mapped_column(ForeignKey("pengguna.id"), nullable=True)
    aksi: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    pengguna = relationship("Pengguna")


class Pengaturan(Base):
    __tablename__ = "pengaturan"
    kunci: Mapped[str] = mapped_column(String(60), primary_key=True)
    nilai: Mapped[str] = mapped_column(Text)
    diubah_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PeristiwaData(Base):
    """Paket hilang, kegagalan API cuaca, dan peristiwa kualitas data lain."""
    __tablename__ = "peristiwa_data"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    jenis: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")


class KotakKeluar(Base):
    __tablename__ = "kotak_keluar"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kepada: Mapped[str] = mapped_column(String(160))
    subjek: Mapped[str] = mapped_column(String(200))
    isi: Mapped[str] = mapped_column(Text)
    waktu: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    terkirim: Mapped[bool] = mapped_column(Boolean, default=False)


# Log audit hanya bisa ditambah (F24).
@event.listens_for(LogAudit, "before_update")
@event.listens_for(LogAudit, "before_delete")
def _audit_immutable(*_):
    raise PermissionError("Log audit tidak dapat diubah atau dihapus.")
