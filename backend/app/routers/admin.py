"""Pengaturan, jadwal kuliah, pengguna, log audit, status sistem, penerimaan data meter."""
import csv
import io
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..db import get_db
from ..models import (Gedung, JadwalKuliah, KotakKeluar, LogAudit, Pengguna, Perangkat, PeristiwaData, Ruang, Sesi,
                      VersiModel)
from ..security import COOKIE, PERAN, audit, cek_sandi, current_user, hash_sandi, hash_token, require
from ..services import data_pipeline, forecast, jobs, simulate

router = APIRouter(prefix="/api", tags=["admin"])
HARI = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]


# ------------------------------------------------------------------ pengaturan (F22)
@router.get("/pengaturan")
def ambil_pengaturan(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    perangkat = [{"id": p.id, "nama": p.nama, "kode": p.kode, "jenis": p.jenis, "protokol": p.protokol,
                  "status": p.status_terakhir,
                  "terakhir_lapor": p.terakhir_lapor.isoformat() if p.terakhir_lapor else None}
                 for p in db.scalars(select(Perangkat).order_by(Perangkat.gedung_id, Perangkat.kode))]
    peristiwa = [{"waktu": e.waktu.isoformat(), "jenis": e.jenis, "detail": e.detail}
                 for e in db.scalars(select(PeristiwaData).order_by(PeristiwaData.waktu.desc()).limit(10))]
    kel = data_pipeline.kelengkapan_harian(db, g.id, 30)
    keluar = [{"kepada": k.kepada, "subjek": k.subjek, "waktu": k.waktu.isoformat(), "terkirim": k.terkirim}
              for k in db.scalars(select(KotakKeluar).order_by(KotakKeluar.waktu.desc()).limit(5))]
    return {"nilai": settings_store.all_values(db), "spesifikasi": settings_store.describe(),
            "perangkat": perangkat, "peristiwa": peristiwa, "kelengkapan": kel,
            "pekerja": jobs.STATUS, "simulasi": config.SIMULATION, "smtp": bool(config.SMTP_HOST),
            "kotak_keluar": keluar}


@router.put("/pengaturan")
def simpan_pengaturan(data: dict, user: Pengguna = Depends(require("pengaturan.ubah")),
                      db: Session = Depends(get_db)):
    ok, err = settings_store.validate(data)
    if err:
        raise HTTPException(422, {"pesan": "Periksa kolom yang ditandai.", "kolom": err})
    lama = settings_store.all_values(db)
    berubah = {k: v for k, v in ok.items() if lama.get(k) != v}
    settings_store.save(db, berubah)
    for k, v in berubah.items():
        audit(db, user.id, "pengaturan.ubah", f"{k}: {lama.get(k)} -> {v}")
    db.commit()
    return {"nilai": settings_store.all_values(db), "berubah": list(berubah)}


# ------------------------------------------------------------------ jadwal kuliah (F03)
@router.get("/jadwal")
def jadwal(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    rows = db.execute(select(JadwalKuliah, Ruang).join(Ruang).order_by(JadwalKuliah.hari, JadwalKuliah.mulai,
                                                                       Ruang.nama)).all()
    ruang = [r.nama for r in db.scalars(select(Ruang).order_by(Ruang.nama))]
    return {"ruang": ruang, "baris": [{"ruang": r.nama, "hari": HARI[j.hari].capitalize(), "mulai": j.mulai,
                                       "selesai": j.selesai, "mata_kuliah": j.mata_kuliah} for j, r in rows]}


class ImporIn(BaseModel):
    csv: str
    simpan: bool = False


_JAM = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")


def _jam(s: str) -> str | None:
    m = _JAM.match(s.strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


@router.post("/jadwal/impor")
def impor_jadwal(data: ImporIn, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    if len(data.csv) > 500_000:
        raise HTTPException(413, "Berkas terlalu besar. Maksimal 500 KB.")
    teks = data.csv.lstrip("﻿")
    try:
        dialek = csv.Sniffer().sniff(teks.splitlines()[0] if teks else ",", delimiters=",;\t")
    except csv.Error:
        dialek = csv.excel
    reader = csv.DictReader(io.StringIO(teks), dialect=dialek)
    kolom = [c.strip().lower() for c in (reader.fieldnames or [])]
    wajib = {"ruang", "hari", "mulai", "selesai"}
    if not wajib <= set(kolom):
        raise HTTPException(422, f"Kolom wajib tidak lengkap. Berkas harus memuat kolom: ruang, hari, mulai, "
                                 f"selesai (opsional: mata_kuliah). Ditemukan: {', '.join(kolom) or 'kosong'}.")
    ruang = {r.nama.lower(): r for r in db.scalars(select(Ruang))}
    hasil, valid = [], []
    for i, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        galat = []
        r = ruang.get(row.get("ruang", "").lower())
        if not r:
            galat.append(f"Ruang “{row.get('ruang', '')}” tidak dikenal")
        h = row.get("hari", "").lower()
        hari = HARI.index(h) if h in HARI else (int(h) - 1 if h.isdigit() and 1 <= int(h) <= 7 else None)
        if hari is None:
            galat.append("Hari harus Senin sampai Minggu")
        m, s = _jam(row.get("mulai", "")), _jam(row.get("selesai", ""))
        if not m:
            galat.append("Jam mulai harus berformat JJ:MM")
        if not s:
            galat.append("Jam selesai harus berformat JJ:MM")
        if m and s and m >= s:
            galat.append("Jam selesai harus setelah jam mulai")
        hasil.append({"baris": i, "data": row, "galat": galat})
        if not galat:
            valid.append(JadwalKuliah(ruang_id=r.id, hari=hari, mulai=m, selesai=s,
                                      mata_kuliah=row.get("mata_kuliah", "")[:120]))
    if not hasil:
        raise HTTPException(422, "Berkas tidak berisi baris data.")
    if data.simpan:
        if not valid:
            raise HTTPException(422, "Tidak ada baris valid untuk diimpor.")
        db.execute(delete(JadwalKuliah))
        db.add_all(valid)
        audit(db, user.id, "jadwal.impor", f"{len(valid)} baris valid, {len(hasil) - len(valid)} dilewati")
        db.flush()
        g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
        forecast.prediksi(db, g, simulate.hour_floor(datetime.now()), 48)
        db.commit()
    return {"total": len(hasil), "valid": len(valid), "salah": [h for h in hasil if h["galat"]][:200],
            "disimpan": data.simpan}


# ------------------------------------------------------------------ pengguna (F23)
def _u(p: Pengguna) -> dict:
    return {"id": p.id, "nama": p.nama, "email": p.email, "peran": p.peran, "peran_label": PERAN[p.peran],
            "aktif": p.aktif, "dibuat_pada": p.dibuat_pada.isoformat()}


@router.get("/pengguna")
def daftar_pengguna(user: Pengguna = Depends(require("pengguna.kelola")), db: Session = Depends(get_db)):
    return {"peran": PERAN, "baris": [_u(p) for p in db.scalars(select(Pengguna).order_by(Pengguna.peran,
                                                                                           Pengguna.nama))]}


class PenggunaIn(BaseModel):
    nama: str
    email: EmailStr
    peran: str
    sandi: str


class PenggunaUbah(BaseModel):
    peran: str | None = None
    aktif: bool | None = None
    nama: str | None = None
    sandi_baru: str | None = None


@router.post("/pengguna", status_code=201)
def tambah_pengguna(data: PenggunaIn, user: Pengguna = Depends(require("pengguna.kelola")),
                    db: Session = Depends(get_db)):
    if data.peran not in PERAN:
        raise HTTPException(422, "Peran tidak dikenal.")
    if len(data.nama.strip()) < 2:
        raise HTTPException(422, "Nama minimal 2 karakter.")
    if len(data.sandi) < 10:
        raise HTTPException(422, "Kata sandi awal minimal 10 karakter.")
    email = str(data.email).lower()
    if db.scalar(select(Pengguna.id).where(func.lower(Pengguna.email) == email)):
        raise HTTPException(409, "Email ini sudah terdaftar.")
    p = Pengguna(nama=data.nama.strip(), email=email, peran=data.peran, hash_sandi=hash_sandi(data.sandi))
    db.add(p)
    db.flush()
    audit(db, user.id, "pengguna.tambah", f"{p.nama} ({p.peran})")
    db.commit()
    return _u(p)


@router.patch("/pengguna/{pid}")
def ubah_pengguna(pid: str, data: PenggunaUbah, user: Pengguna = Depends(require("pengguna.kelola")),
                  db: Session = Depends(get_db)):
    p = db.get(Pengguna, pid)
    if not p:
        raise HTTPException(404, "Pengguna tidak ditemukan.")
    if p.id == user.id and (data.aktif is False or (data.peran and data.peran != "tim")):
        raise HTTPException(422, "Akun sendiri tidak bisa dinonaktifkan atau diturunkan perannya.")
    perubahan = []
    if data.peran is not None:
        if data.peran not in PERAN:
            raise HTTPException(422, "Peran tidak dikenal.")
        perubahan.append(f"peran {p.peran} -> {data.peran}")
        p.peran = data.peran
    if data.aktif is not None:
        perubahan.append("diaktifkan" if data.aktif else "dinonaktifkan")
        p.aktif = data.aktif
        if not data.aktif:
            db.execute(delete(Sesi).where(Sesi.pengguna_id == p.id))
    if data.nama:
        p.nama = data.nama.strip()
    if data.sandi_baru is not None:
        if len(data.sandi_baru) < 10:
            raise HTTPException(422, {"pesan": "Kata sandi baru minimal 10 karakter.",
                                      "kolom": {"sandi_baru": "Minimal 10 karakter."}})
        p.hash_sandi = hash_sandi(data.sandi_baru)
        db.execute(delete(Sesi).where(Sesi.pengguna_id == p.id))
        perubahan.append("kata sandi direset")
    audit(db, user.id, "pengguna.ubah", f"{p.nama}: {', '.join(perubahan) or 'nama'}")
    db.commit()
    return _u(p)


# ------------------------------------------------------------------ preferensi notifikasi (F16)
class PreferensiIn(BaseModel):
    email_mingguan: bool | None = None
    notif_aplikasi: bool | None = None


@router.put("/saya/notifikasi")
def preferensi(data: PreferensiIn, user: Pengguna = Depends(current_user), db: Session = Depends(get_db)):
    if data.email_mingguan is not None:
        user.email_mingguan = data.email_mingguan
    if data.notif_aplikasi is not None:
        user.notif_aplikasi = data.notif_aplikasi
    audit(db, user.id, "preferensi.ubah",
          f"email mingguan {'aktif' if user.email_mingguan else 'mati'}, "
          f"notifikasi aplikasi {'aktif' if user.notif_aplikasi else 'mati'}")
    db.commit()
    return {"email_mingguan": user.email_mingguan, "notif_aplikasi": user.notif_aplikasi}


class SandiIn(BaseModel):
    lama: str
    baru: str


@router.put("/saya/sandi")
def ganti_sandi(data: SandiIn, request: Request, user: Pengguna = Depends(current_user),
                db: Session = Depends(get_db)):
    if not cek_sandi(data.lama, user.hash_sandi):
        raise HTTPException(422, {"pesan": "Kata sandi lama salah.", "kolom": {"lama": "Kata sandi lama salah."}})
    if len(data.baru) < 10:
        raise HTTPException(422, {"pesan": "Kata sandi baru minimal 10 karakter.",
                                  "kolom": {"baru": "Minimal 10 karakter."}})
    if data.baru == data.lama:
        raise HTTPException(422, {"pesan": "Kata sandi baru harus berbeda dari yang lama.",
                                  "kolom": {"baru": "Harus berbeda dari kata sandi lama."}})
    user.hash_sandi = hash_sandi(data.baru)
    # akhiri sesi lain; sesi perangkat ini tetap aktif
    kini = hash_token(request.cookies.get(COOKIE, ""))
    db.execute(delete(Sesi).where(Sesi.pengguna_id == user.id, Sesi.token_hash != kini))
    audit(db, user.id, "sandi.ganti", "Kata sandi diganti; sesi lain diakhiri.")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ gedung (U9)
def _g(g: Gedung) -> dict:
    return {"id": g.id, "nama": g.nama, "fungsi": g.fungsi, "luas_m2": g.luas_m2,
            "jam_operasional_pekan": g.jam_operasional_pekan, "kapasitas_pv_kwp": g.kapasitas_pv_kwp,
            "peran": g.peran}


@router.get("/gedung")
def daftar_gedung(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    urut = {"percontohan": 0, "pembanding": 1, "lain": 2}
    rows = sorted(db.scalars(select(Gedung)), key=lambda g: (urut.get(g.peran, 3), g.nama))
    return {"fungsi": sorted(settings_store.get(db, "pembanding_fungsi")), "baris": [_g(g) for g in rows]}


class GedungUbah(BaseModel):
    nama: str | None = None
    fungsi: str | None = None
    luas_m2: float | None = None
    jam_operasional_pekan: float | None = None
    kapasitas_pv_kwp: float | None = None


@router.patch("/gedung/{gid}")
def ubah_gedung(gid: str, data: GedungUbah, user: Pengguna = Depends(require("pengaturan.ubah")),
                db: Session = Depends(get_db)):
    g = db.get(Gedung, gid)
    if not g:
        raise HTTPException(404, "Gedung tidak ditemukan.")
    err = {}
    if data.nama is not None and len(data.nama.strip()) < 3:
        err["nama"] = "Nama gedung minimal 3 karakter."
    if data.fungsi is not None and data.fungsi not in settings_store.get(db, "pembanding_fungsi"):
        err["fungsi"] = "Fungsi harus salah satu yang punya nilai pembanding di Parameter."
    if data.luas_m2 is not None and not 50 <= data.luas_m2 <= 200_000:
        err["luas_m2"] = "Luas harus antara 50 dan 200.000 m²."
    if data.jam_operasional_pekan is not None and not 1 <= data.jam_operasional_pekan <= 168:
        err["jam_operasional_pekan"] = "Jam operasional harus antara 1 dan 168 jam per pekan."
    if data.kapasitas_pv_kwp is not None and not 0 <= data.kapasitas_pv_kwp <= 5_000:
        err["kapasitas_pv_kwp"] = "Kapasitas panel surya harus antara 0 dan 5.000 kWp."
    if err:
        raise HTTPException(422, {"pesan": "Periksa kolom yang ditandai.", "kolom": err})
    lama = _g(g)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(g, k, v.strip() if isinstance(v, str) else v)
    berubah = [f"{k}: {lama[k]} -> {v}" for k, v in _g(g).items() if lama[k] != v]
    if berubah:
        audit(db, user.id, "gedung.ubah", f"{g.nama}; " + "; ".join(berubah))
        if g.peran in ("percontohan", "pembanding"):
            from datetime import date
            from ..services import impact
            hari = date.today()
            impact.hitung_skor_bulanan(db, g, date(hari.year, hari.month, 1))
    db.commit()
    return {**_g(g), "berubah": len(berubah)}


# ------------------------------------------------------------------ log audit (F24)
@router.get("/audit")
def log_audit(halaman: int = 1, aksi: str | None = None, user: Pengguna = Depends(require("audit.lihat")),
              db: Session = Depends(get_db)):
    halaman = max(1, halaman)
    q = select(LogAudit)
    if aksi:
        q = q.where(LogAudit.aksi.like(f"{aksi}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(LogAudit.waktu.desc()).offset((halaman - 1) * 50).limit(50))
    return {"total": total, "halaman": halaman, "baris": [
        {"waktu": r.waktu.isoformat(), "pengguna": r.pengguna.nama if r.pengguna else "Sistem", "aksi": r.aksi,
         "detail": r.detail} for r in rows]}


# ------------------------------------------------------------------ model (F08)
@router.post("/model/latih")
def latih_model(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    try:
        v = forecast.latih(db, g, datetime.now(), f"Latih ulang manual oleh {user.nama}.")
    except ValueError as e:
        raise HTTPException(422, str(e))
    forecast.prediksi(db, g, simulate.hour_floor(datetime.now()), 48)
    audit(db, user.id, "model.latih", f"MAPE {v.mape} %, MAE {v.mae} kW, aktif={v.aktif}")
    db.commit()
    return {"id": v.id, "mape": v.mape, "mae": v.mae, "aktif": v.aktif, "catatan": v.catatan}


@router.get("/model")
def daftar_model(user: Pengguna = Depends(require("belajar.lihat")), db: Session = Depends(get_db)):
    return [{"id": v.id, "tanggal_latih": v.tanggal_latih.isoformat(), "mape": v.mape, "mae": v.mae,
             "aktif": v.aktif} for v in db.scalars(select(VersiModel).order_by(VersiModel.tanggal_latih.desc()))]


# ------------------------------------------------------------------ penerimaan data meter (F01)
class Pembacaan(BaseModel):
    perangkat: str  # kode perangkat / topik MQTT
    waktu: datetime  # WIB
    beban_kw: float | None = None
    produksi_pv_kw: float | None = None


@router.post("/ingest")
def ingest(data: list[Pembacaan], x_ingest_token: str = Header(default=""), db: Session = Depends(get_db)):
    """Dipanggil jembatan MQTT (scripts/mqtt_bridge.py). Bukan untuk peramban."""
    if x_ingest_token != config.INGEST_TOKEN:
        raise HTTPException(401, "Token penerimaan data tidak sah.")
    if len(data) > 10_000:
        raise HTTPException(413, "Maksimal 10.000 pembacaan per kiriman.")
    kode = {p.kode: p for p in db.scalars(select(Perangkat))}
    rows, tak_dikenal = [], set()
    for d in data:
        p = kode.get(d.perangkat)
        if not p:
            tak_dikenal.add(d.perangkat)
            continue
        w = d.waktu.astimezone(config.TZ).replace(tzinfo=None) if d.waktu.tzinfo else d.waktu
        rows.append({"waktu": w.replace(second=0, microsecond=0), "perangkat_id": p.id,
                     "beban_kw": d.beban_kw, "produksi_pv_kw": d.produksi_pv_kw, "kualitas": 0})
    n = data_pipeline.simpan_pembacaan(db, rows)
    if tak_dikenal:
        data_pipeline.catat_peristiwa(db, "perangkat_tak_dikenal", ", ".join(sorted(tak_dikenal))[:300])
    db.commit()
    return {"diterima": n, "ditolak": len(data) - n}
