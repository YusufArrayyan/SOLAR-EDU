"""M6 notifikasi dalam aplikasi dan email ringkasan mingguan."""
from __future__ import annotations

import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..models import Anomali, KotakKeluar, Notifikasi, Pengguna, Prediksi, Rekomendasi


def kirim(db: Session, penerima: list[Pengguna], jenis: str, judul: str, isi: str = "", tautan: str = "",
          waktu: datetime | None = None) -> None:
    for p in penerima:
        if not p.aktif or not p.notif_aplikasi:
            continue
        db.add(Notifikasi(pengguna_id=p.id, jenis=jenis, judul=judul, isi=isi, tautan=tautan,
                          waktu=waktu or datetime.now()))


def ke_peran(db: Session, peran: list[str], *args, **kw) -> None:
    users = list(db.scalars(select(Pengguna).where(Pengguna.peran.in_(peran), Pengguna.aktif.is_(True))))
    kirim(db, users, *args, **kw)


def _fmt(x: float) -> str:
    return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ringkasan_mingguan(db: Session, gedung_id: str, sekarang: datetime | None = None) -> tuple[str, str]:
    """F16: anomali, tindakan, dan prediksi pekan depan."""
    sekarang = sekarang or datetime.now()
    awal = sekarang - timedelta(days=7)
    anom = list(db.scalars(select(Anomali).where(Anomali.gedung_id == gedung_id, Anomali.mulai >= awal)))
    recs = list(db.scalars(select(Rekomendasi).where(Rekomendasi.dibuat_pada >= awal)))
    selesai = db.scalar(select(func.count()).select_from(Rekomendasi).where(
        Rekomendasi.dilaksanakan_pada >= awal)) or 0
    pred = db.scalar(select(func.sum(Prediksi.nilai_kw)).where(
        Prediksi.gedung_id == gedung_id, Prediksi.waktu_target >= sekarang,
        Prediksi.waktu_target < sekarang + timedelta(days=1))) or 0
    subjek = f"Ringkasan mingguan SOLAR-EDU AI, {sekarang:%d-%m-%Y}"
    baris = [
        "Ringkasan pekan lalu untuk gedung percontohan.",
        "",
        f"Anomali terdeteksi: {len(anom)} (kelebihan {_fmt(sum(a.kelebihan_kwh for a in anom))} kWh)",
        f"Rekomendasi baru: {len(recs)}",
        f"Tindakan dilaksanakan: {selesai}",
        f"Prediksi konsumsi 24 jam ke depan: {_fmt(pred)} kWh",
        "",
        "Buka dashboard untuk memverifikasi rekomendasi yang menunggu.",
        "Email ini dapat dimatikan di Pengaturan > Notifikasi.",
    ]
    return subjek, "\n".join(baris)


def kirim_ringkasan_mingguan(db: Session, gedung_id: str) -> int:
    if not settings_store.get(db, "ringkasan_mingguan_aktif"):
        return 0
    subjek, isi = ringkasan_mingguan(db, gedung_id)
    if db.scalar(select(KotakKeluar.id).where(KotakKeluar.subjek == subjek).limit(1)):
        return 0  # sudah dikirim hari ini
    n = 0
    for u in db.scalars(select(Pengguna).where(Pengguna.aktif.is_(True), Pengguna.email_mingguan.is_(True),
                                               Pengguna.peran.in_(["pengelola", "tim", "pimpinan"]))):
        ok = _smtp(u.email, subjek, isi)
        db.add(KotakKeluar(kepada=u.email, subjek=subjek, isi=isi, terkirim=ok))
        n += 1
    return n


def _smtp(kepada: str, subjek: str, isi: str) -> bool:
    if not config.SMTP_HOST:
        return False  # tersimpan di kotak keluar; dikirim bila SMTP dikonfigurasi
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, kepada, subjek
        msg.set_content(isi)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception:
        return False
