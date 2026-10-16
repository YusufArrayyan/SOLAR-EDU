"""Pengelolaan produksi: perangkat, ruang, gedung lain, konsumsi bulanan, dan daftar persiapan sistem."""
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..db import get_db
from ..models import (AgregatJam, Cuaca, Gedung, JadwalKuliah, KonsumsiBulanan, Pengguna, Pengukuran, Perangkat,
                      Ruang, SkorPeringkat, VersiModel)
from ..security import audit, require
from ..services import impact

router = APIRouter(prefix="/api", tags=["kelola"])
_KODE = re.compile(r"^[a-z0-9][a-z0-9_\-/.]{1,38}$")


def _galat(kolom: dict[str, str]):
    raise HTTPException(422, {"pesan": "Periksa kolom yang ditandai.", "kolom": kolom})


def _gedung(db: Session, gid: str) -> Gedung:
    g = db.get(Gedung, gid)
    if not g:
        raise HTTPException(404, "Gedung tidak ditemukan.")
    return g


# ------------------------------------------------------------------ perangkat
def _p(p: Perangkat) -> dict:
    return {"id": p.id, "gedung_id": p.gedung_id, "kode": p.kode, "nama": p.nama, "jenis": p.jenis,
            "protokol": p.protokol, "batas_fisik_kw": p.batas_fisik_kw, "status": p.status_terakhir,
            "terakhir_lapor": p.terakhir_lapor.isoformat() if p.terakhir_lapor else None}


class PerangkatIn(BaseModel):
    gedung_id: str | None = None
    kode: str | None = None
    nama: str | None = None
    jenis: str | None = None
    protokol: str | None = None
    batas_fisik_kw: float | None = None


def _cek_perangkat(db: Session, data: PerangkatIn, pid: str | None = None) -> None:
    err = {}
    if data.kode is not None:
        if not _KODE.match(data.kode):
            err["kode"] = "Kode 2–39 karakter: huruf kecil, angka, - _ / . (sama dengan topik MQTT)."
        elif db.scalar(select(Perangkat.id).where(Perangkat.kode == data.kode, Perangkat.id != (pid or ""))):
            err["kode"] = "Kode ini sudah dipakai perangkat lain."
    if data.nama is not None and len(data.nama.strip()) < 3:
        err["nama"] = "Nama minimal 3 karakter."
    if data.jenis is not None and data.jenis not in ("meter", "inverter"):
        err["jenis"] = "Jenis harus meter atau inverter."
    if data.batas_fisik_kw is not None and not 1 <= data.batas_fisik_kw <= 5000:
        err["batas_fisik_kw"] = "Batas fisik harus antara 1 dan 5.000 kW."
    if err:
        _galat(err)


@router.get("/perangkat")
def daftar_perangkat(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    return [_p(p) for p in db.scalars(select(Perangkat).order_by(Perangkat.gedung_id, Perangkat.kode))]


@router.post("/perangkat", status_code=201)
def tambah_perangkat(data: PerangkatIn, user: Pengguna = Depends(require("pengaturan.ubah")),
                     db: Session = Depends(get_db)):
    if not data.gedung_id or not data.kode or not data.nama or not data.jenis:
        _galat({k: "Wajib diisi." for k in ("gedung_id", "kode", "nama", "jenis") if not getattr(data, k)})
    g = _gedung(db, data.gedung_id)
    if g.peran == "lain":
        raise HTTPException(422, "Gedung lain memakai input konsumsi bulanan, bukan perangkat.")
    _cek_perangkat(db, data)
    p = Perangkat(gedung_id=g.id, kode=data.kode, nama=data.nama.strip(), jenis=data.jenis,
                  protokol=(data.protokol or "Modbus ke MQTT").strip(), batas_fisik_kw=data.batas_fisik_kw or 100,
                  status_terakhir="belum lapor")
    db.add(p)
    db.flush()
    audit(db, user.id, "perangkat.tambah", f"{p.nama} ({p.kode}) di {g.nama}")
    db.commit()
    return _p(p)


@router.patch("/perangkat/{pid}")
def ubah_perangkat(pid: str, data: PerangkatIn, user: Pengguna = Depends(require("pengaturan.ubah")),
                   db: Session = Depends(get_db)):
    p = db.get(Perangkat, pid)
    if not p:
        raise HTTPException(404, "Perangkat tidak ditemukan.")
    if data.jenis is not None and data.jenis != p.jenis:
        _galat({"jenis": "Jenis perangkat tidak bisa diubah. Tambahkan perangkat baru."})
    _cek_perangkat(db, data, pid)
    lama = _p(p)
    for k in ("kode", "nama", "protokol", "batas_fisik_kw"):
        v = getattr(data, k)
        if v is not None:
            setattr(p, k, v.strip() if isinstance(v, str) else v)
    berubah = [f"{k}: {lama[k]} -> {v}" for k, v in _p(p).items() if lama[k] != v]
    if berubah:
        audit(db, user.id, "perangkat.ubah", f"{p.nama}; " + "; ".join(berubah))
    db.commit()
    return {**_p(p), "berubah": len(berubah)}


@router.delete("/perangkat/{pid}")
def hapus_perangkat(pid: str, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    p = db.get(Perangkat, pid)
    if not p:
        raise HTTPException(404, "Perangkat tidak ditemukan.")
    if db.scalar(select(Pengukuran.waktu).where(Pengukuran.perangkat_id == pid).limit(1)):
        raise HTTPException(409, "Perangkat ini sudah punya data pengukuran, jadi tidak bisa dihapus. Ubah namanya, "
                                 "atau biarkan berstatus diam.")
    for r in db.scalars(select(Ruang).where(Ruang.perangkat_id == pid)):
        r.perangkat_id = None
    audit(db, user.id, "perangkat.hapus", f"{p.nama} ({p.kode})")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ ruang
def _r(r: Ruang) -> dict:
    return {"id": r.id, "gedung_id": r.gedung_id, "nama": r.nama, "kapasitas": r.kapasitas,
            "perangkat_id": r.perangkat_id}


class RuangIn(BaseModel):
    gedung_id: str | None = None
    nama: str | None = None
    kapasitas: int | None = None
    perangkat_id: str | None = None


def _cek_ruang(db: Session, data: RuangIn, gedung_id: str, rid: str | None = None) -> None:
    err = {}
    if data.nama is not None:
        if not 2 <= len(data.nama.strip()) <= 60:
            err["nama"] = "Nama ruang 2–60 karakter, sama persis dengan kolom ruang di CSV jadwal."
        elif db.scalar(select(Ruang.id).where(func.lower(Ruang.nama) == data.nama.strip().lower(),
                                              Ruang.id != (rid or ""))):
            err["nama"] = "Nama ruang ini sudah ada."
    if data.kapasitas is not None and not 1 <= data.kapasitas <= 2000:
        err["kapasitas"] = "Kapasitas harus antara 1 dan 2.000 orang."
    if data.perangkat_id:
        p = db.get(Perangkat, data.perangkat_id)
        if not p or p.gedung_id != gedung_id or p.jenis != "meter":
            err["perangkat_id"] = "Pilih panel meter di gedung yang sama."
    if err:
        _galat(err)


@router.get("/ruang")
def daftar_ruang(user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    jadwal = dict(db.execute(select(JadwalKuliah.ruang_id, func.count()).group_by(JadwalKuliah.ruang_id)).all())
    return [{**_r(r), "sesi_jadwal": jadwal.get(r.id, 0)} for r in db.scalars(select(Ruang).order_by(Ruang.nama))]


@router.post("/ruang", status_code=201)
def tambah_ruang(data: RuangIn, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    if not data.gedung_id or not data.nama:
        _galat({"nama": "Wajib diisi."})
    g = _gedung(db, data.gedung_id)
    if g.peran != "percontohan":
        raise HTTPException(422, "Ruang dan jadwal hanya dipakai untuk gedung percontohan.")
    _cek_ruang(db, data, g.id)
    r = Ruang(gedung_id=g.id, nama=data.nama.strip(), kapasitas=data.kapasitas or 40, perangkat_id=data.perangkat_id)
    db.add(r)
    db.flush()
    audit(db, user.id, "ruang.tambah", r.nama)
    db.commit()
    return _r(r)


@router.patch("/ruang/{rid}")
def ubah_ruang(rid: str, data: RuangIn, user: Pengguna = Depends(require("pengaturan.ubah")),
               db: Session = Depends(get_db)):
    r = db.get(Ruang, rid)
    if not r:
        raise HTTPException(404, "Ruang tidak ditemukan.")
    _cek_ruang(db, data, r.gedung_id, rid)
    lama = _r(r)
    if data.nama is not None:
        r.nama = data.nama.strip()
    if data.kapasitas is not None:
        r.kapasitas = data.kapasitas
    if "perangkat_id" in data.model_fields_set:
        r.perangkat_id = data.perangkat_id or None
    berubah = [f"{k}: {lama[k]} -> {v}" for k, v in _r(r).items() if lama[k] != v]
    if berubah:
        audit(db, user.id, "ruang.ubah", f"{r.nama}; " + "; ".join(berubah))
    db.commit()
    return {**_r(r), "berubah": len(berubah)}


@router.delete("/ruang/{rid}")
def hapus_ruang(rid: str, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    r = db.get(Ruang, rid)
    if not r:
        raise HTTPException(404, "Ruang tidak ditemukan.")
    n = db.scalar(select(func.count()).select_from(JadwalKuliah).where(JadwalKuliah.ruang_id == rid)) or 0
    if n:
        raise HTTPException(409, f"Ruang ini dipakai {n} sesi jadwal. Impor ulang jadwal tanpa ruang ini, lalu hapus.")
    audit(db, user.id, "ruang.hapus", r.nama)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ gedung lain dan konsumsi bulanan
class GedungBaruIn(BaseModel):
    nama: str
    fungsi: str
    luas_m2: float
    jam_operasional_pekan: float


@router.post("/gedung", status_code=201)
def tambah_gedung(data: GedungBaruIn, user: Pengguna = Depends(require("pengaturan.ubah")),
                  db: Session = Depends(get_db)):
    err = {}
    if len(data.nama.strip()) < 3:
        err["nama"] = "Nama gedung minimal 3 karakter."
    elif db.scalar(select(Gedung.id).where(func.lower(Gedung.nama) == data.nama.strip().lower())):
        err["nama"] = "Nama gedung ini sudah ada."
    if data.fungsi not in settings_store.get(db, "pembanding_fungsi"):
        err["fungsi"] = "Fungsi harus salah satu yang punya nilai pembanding di Parameter."
    if not 50 <= data.luas_m2 <= 200_000:
        err["luas_m2"] = "Luas harus antara 50 dan 200.000 m²."
    if not 1 <= data.jam_operasional_pekan <= 168:
        err["jam_operasional_pekan"] = "Jam operasional harus antara 1 dan 168 jam per pekan."
    if err:
        _galat(err)
    g = Gedung(nama=data.nama.strip(), fungsi=data.fungsi, luas_m2=data.luas_m2,
               jam_operasional_pekan=data.jam_operasional_pekan, kapasitas_pv_kwp=0, peran="lain")
    db.add(g)
    db.flush()
    audit(db, user.id, "gedung.tambah", g.nama)
    db.commit()
    return {"id": g.id, "nama": g.nama, "fungsi": g.fungsi, "luas_m2": g.luas_m2,
            "jam_operasional_pekan": g.jam_operasional_pekan, "kapasitas_pv_kwp": 0, "peran": g.peran}


@router.delete("/gedung/{gid}")
def hapus_gedung(gid: str, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    g = _gedung(db, gid)
    if g.peran != "lain":
        raise HTTPException(409, "Gedung percontohan dan pembanding tidak bisa dihapus.")
    db.execute(delete(SkorPeringkat).where(SkorPeringkat.gedung_id == gid))
    db.execute(delete(KonsumsiBulanan).where(KonsumsiBulanan.gedung_id == gid))
    audit(db, user.id, "gedung.hapus", g.nama)
    db.delete(g)
    db.commit()
    return {"ok": True}


class KonsumsiIn(BaseModel):
    periode: str  # YYYY-MM
    kwh: float
    sumber: str = "tagihan PLN"


@router.get("/gedung/{gid}/konsumsi")
def daftar_konsumsi(gid: str, user: Pengguna = Depends(require("pengaturan.ubah")), db: Session = Depends(get_db)):
    _gedung(db, gid)
    rows = db.scalars(select(KonsumsiBulanan).where(KonsumsiBulanan.gedung_id == gid)
                      .order_by(KonsumsiBulanan.periode.desc()).limit(24))
    skor = {s.periode: s.indeks_efisiensi for s in db.scalars(select(SkorPeringkat).where(
        SkorPeringkat.gedung_id == gid))}
    return [{"periode": k.periode.isoformat()[:7], "kwh": k.kwh, "sumber": k.sumber,
             "indeks": skor.get(k.periode)} for k in rows]


@router.put("/gedung/{gid}/konsumsi")
def simpan_konsumsi(gid: str, data: KonsumsiIn, user: Pengguna = Depends(require("pengaturan.ubah")),
                    db: Session = Depends(get_db)):
    g = _gedung(db, gid)
    if g.peran != "lain":
        raise HTTPException(422, "Konsumsi gedung percontohan dan pembanding dihitung dari meter.")
    err = {}
    try:
        th, bl = (int(x) for x in data.periode.split("-"))
        periode = date(th, bl, 1)
    except (ValueError, TypeError):
        periode = None
        err["periode"] = "Periode harus berformat TTTT-BB, misalnya 2026-09."
    hari_ini = date.today()
    if periode and (periode >= date(hari_ini.year, hari_ini.month, 1) or periode.year < 2020):
        err["periode"] = "Pilih bulan yang sudah selesai."
    if not 1 <= data.kwh <= 10_000_000:
        err["kwh"] = "Konsumsi harus antara 1 dan 10.000.000 kWh."
    if err:
        _galat(err)
    row = db.scalar(select(KonsumsiBulanan).where(KonsumsiBulanan.gedung_id == gid,
                                                  KonsumsiBulanan.periode == periode))
    if row is None:
        row = KonsumsiBulanan(gedung_id=gid, periode=periode, kwh=data.kwh)
        db.add(row)
    row.kwh, row.sumber, row.dicatat_oleh, row.waktu = data.kwh, data.sumber.strip()[:60] or "tagihan PLN", user.id, datetime.now()
    s = impact.skor_dari_tagihan(db, g, periode, data.kwh)
    audit(db, user.id, "konsumsi.catat", f"{g.nama} {data.periode}: {data.kwh:g} kWh")
    db.commit()
    return {"periode": data.periode, "kwh": row.kwh, "indeks": s.indeks_efisiensi,
            "intensitas": s.intensitas_wh_m2_jam}


# ------------------------------------------------------------------ persiapan sistem
@router.get("/persiapan")
def persiapan(user: Pengguna = Depends(require("rekomendasi.verifikasi")), db: Session = Depends(get_db)):
    now = datetime.now()
    pilot = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    banding = db.scalar(select(Gedung).where(Gedung.peran == "pembanding"))

    def perangkat_status(g: Gedung | None) -> tuple[int, int]:
        if not g:
            return 0, 0
        semua = list(db.scalars(select(Perangkat).where(Perangkat.gedung_id == g.id)))
        aktif = [p for p in semua if p.terakhir_lapor and now - p.terakhir_lapor <= timedelta(hours=2)]
        return len(aktif), len(semua)

    pa, pt = perangkat_status(pilot)
    ba, bt = perangkat_status(banding)
    jadwal = db.scalar(select(func.count()).select_from(JadwalKuliah)) or 0
    # di mode simulasi, akun uji dan cuaca simulasi dihitung sebagai lingkungan yang lengkap
    q_peran = select(Pengguna.peran, func.count()).where(Pengguna.aktif.is_(True))
    if not config.SIMULATION:
        q_peran = q_peran.where(Pengguna.demo.is_(False))
    peran = dict(db.execute(q_peran.group_by(Pengguna.peran)).all())
    jam_bersih = db.scalar(select(func.count()).select_from(AgregatJam).where(
        AgregatJam.gedung_id == pilot.id, AgregatJam.beban_kw.is_not(None), AgregatJam.suhu.is_not(None),
        AgregatJam.kelengkapan >= 0.75)) or 0
    model = db.scalar(select(VersiModel).where(VersiModel.aktif.is_(True)))
    cuaca = db.scalar(select(Cuaca.sumber).where(Cuaca.waktu >= now).order_by(Cuaca.waktu).limit(1))
    hari = jam_bersih / 24

    def angka(x: float) -> str:
        return f"{x:.1f}".replace(".", ",")

    def item(kode, judul, selesai, rinci, tautan, wajib=True):
        return {"kode": kode, "judul": judul, "selesai": bool(selesai), "rinci": rinci, "tautan": tautan,
                "wajib": wajib}

    daftar = [
        item("perangkat", "Hubungkan meter dan inverter gedung percontohan", pt and pa == pt,
             f"{pa} dari {pt} perangkat mengirim data dalam 2 jam terakhir.", "#/pengaturan?tab=gedung"),
        item("cuaca", "Prakiraan cuaca masuk", cuaca == "open-meteo" or (config.SIMULATION and cuaca == "simulasi"),
             "Sumber: " + (cuaca or "belum ada") + ".", "#/pengaturan?tab=sistem"),
        item("jadwal", "Impor jadwal kuliah semester ini", jadwal > 0, f"{jadwal} sesi kuliah per pekan.",
             "#/pengaturan?tab=jadwal"),
        item("akun", "Buat akun pengelola gedung dan mahasiswa piket",
             peran.get("pengelola", 0) >= 1 and peran.get("piket", 0) >= 1,
             f"{peran.get('pengelola', 0)} pengelola, {peran.get('piket', 0)} piket, "
             f"{peran.get('pimpinan', 0)} pimpinan.", "#/pengaturan?tab=pengguna"),
        item("data", "Kumpulkan data minimal 21 hari", hari >= 21,
             f"{angka(hari)} dari 21 hari data bersih terkumpul.", "#/pengaturan?tab=sistem"),
        item("model", "Model prediksi aktif", model is not None,
             f"MAPE {angka(model.mape)} %." if model else "Dilatih otomatis pukul 02.00 setelah 21 hari data terkumpul, "
             "atau lewat tombol di Status sistem.", "#/belajar"),
        item("banding", "Hubungkan meter gedung pembanding", bt and ba == bt,
             f"{ba} dari {bt} perangkat aktif. Dibutuhkan untuk evaluasi selisih-dalam-selisih.",
             "#/pengaturan?tab=gedung", wajib=False),
        item("email", "Atur server email untuk ringkasan mingguan", bool(config.SMTP_HOST),
             "SMTP aktif." if config.SMTP_HOST else "Tanpa SMTP, email tersimpan di kotak keluar.",
             "#/pengaturan?tab=sistem", wajib=False),
    ]
    wajib = [d for d in daftar if d["wajib"]]
    return {"siap": all(d["selesai"] for d in wajib), "selesai": sum(d["selesai"] for d in wajib),
            "total": len(wajib), "hari_data": round(hari, 1), "daftar": daftar}
