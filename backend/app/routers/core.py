"""Ringkasan, rekomendasi, tugas, notifikasi."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (AgregatJam, Anomali, Gedung, Notifikasi, Pengguna, Perangkat, Prediksi, Rekomendasi, Tugas,
                      VersiModel)
from ..security import IZIN, current_user, require
from ..services import anomaly, recommend, simulate

router = APIRouter(prefix="/api", tags=["inti"])


def _pilot(db: Session) -> Gedung:
    return db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))


def _r(x, d=2):
    return None if x is None else round(float(x), d)


# ------------------------------------------------------------------ ringkasan
@router.get("/ringkasan")
def ringkasan(user: Pengguna = Depends(require("ringkasan.lihat")), db: Session = Depends(get_db)):
    g = _pilot(db)
    now = datetime.now()
    jam = simulate.hour_floor(now)
    awal, akhir = jam - timedelta(hours=48), jam + timedelta(hours=24)
    akt = {a.waktu: a for a in db.scalars(select(AgregatJam).where(
        AgregatJam.gedung_id == g.id, AgregatJam.waktu >= awal, AgregatJam.waktu < akhir))}
    pred = {p.waktu_target: p for p in db.scalars(select(Prediksi).where(
        Prediksi.gedung_id == g.id, Prediksi.waktu_target >= awal, Prediksi.waktu_target < akhir))}
    seri = []
    t = awal
    while t < akhir:
        a, p = akt.get(t), pred.get(t)
        seri.append({"t": t.isoformat(), "aktual": _r(a.beban_kw) if a else None,
                     "pv": _r(a.produksi_pv_kw) if a else None, "anomali": bool(a and a.anomali),
                     "prediksi": _r(p.nilai_kw) if p else None, "bawah": _r(p.batas_bawah) if p else None,
                     "atas": _r(p.batas_atas) if p else None, "pv_prediksi": _r(p.pv_kw) if p else None})
        t += timedelta(hours=1)

    terakhir = max((a for a in akt.values() if a.beban_kw is not None), key=lambda a: a.waktu, default=None)
    hari_ini = jam.replace(hour=0)
    hari = [akt[k] for k in akt if hari_ini <= k < jam and akt[k].beban_kw is not None]
    kwh_hari = sum(a.beban_kw for a in hari)
    kwh_pred = sum(pred[a.waktu].nilai_kw for a in hari if a.waktu in pred)
    pv_hari = sum((a.produksi_pv_kw or 0) for a in hari)

    besok = hari_ini + timedelta(days=1)
    pb = list(db.scalars(select(Prediksi).where(
        Prediksi.gedung_id == g.id, Prediksi.waktu_target >= besok,
        Prediksi.waktu_target < besok + timedelta(days=1)).order_by(Prediksi.waktu_target)))
    prediksi_besok = None
    if len(pb) >= 20:
        puncak = max(pb, key=lambda p: p.nilai_kw)
        pv_max = max(p.pv_kw for p in pb)
        jendela = [p.waktu_target for p in pb if pv_max > 0 and p.pv_kw >= 0.6 * pv_max]
        prediksi_besok = {
            "tanggal": besok.date().isoformat(), "kwh": _r(sum(p.nilai_kw for p in pb), 1),
            "kwh_bawah": _r(sum(p.batas_bawah for p in pb), 1), "kwh_atas": _r(sum(p.batas_atas for p in pb), 1),
            "puncak_kw": _r(puncak.nilai_kw, 1), "puncak_jam": puncak.waktu_target.isoformat(),
            "pv_kwh": _r(sum(p.pv_kw for p in pb), 1),
            "jendela_surya": [jendela[0].isoformat(), (jendela[-1] + timedelta(hours=1)).isoformat()] if jendela else None,
        }

    # peringatan: anomali 48 jam terakhir yang rekomendasinya masih terbuka atau belum ada
    peringatan = []
    for an in db.scalars(select(Anomali).where(Anomali.gedung_id == g.id, Anomali.selesai >= now - timedelta(hours=48),
                                               Anomali.status.in_(["baru", "berulang", "valid"]))
                         .order_by(Anomali.mulai.desc())):
        rec = db.scalar(select(Rekomendasi).where(Rekomendasi.anomali_id == an.id))
        if rec is None and an.status == "berulang":
            rec = recommend.rekomendasi_terbuka_serupa(db, an)
        if rec and rec.status not in ("Diusulkan", "Diverifikasi", "Dilaksanakan"):
            continue
        peringatan.append({
            "id": an.id, "mulai": an.mulai.isoformat(), "selesai": an.selesai.isoformat(),
            "berlangsung": an.selesai >= jam, "kelebihan_kwh": an.kelebihan_kwh, "puncak_kw": an.puncak_residu_kw,
            "lokasi": an.perangkat.nama if an.perangkat else "Seluruh gedung", "ruang_terjadwal": an.ruang_terjadwal,
            "rekomendasi": {"id": rec.id, "judul": rec.judul, "status": rec.status, "nomor": rec.nomor} if rec else None,
        })

    data_diam = [{"nama": p.nama, "terakhir": p.terakhir_lapor.isoformat() if p.terakhir_lapor else None}
                 for p in db.scalars(select(Perangkat).where(Perangkat.gedung_id == g.id,
                                                             Perangkat.status_terakhir == "diam"))]
    menunggu = db.scalar(select(func.count()).select_from(Rekomendasi).where(Rekomendasi.status == "Diusulkan")) or 0
    tugas_saya = [_tugas_dict(t) for t in db.scalars(select(Tugas).where(
        Tugas.pelaksana_id == user.id, Tugas.selesai_pada.is_(None)).order_by(Tugas.batas_waktu))
        if t.rekomendasi.status == "Diverifikasi"]
    model = db.scalar(select(VersiModel).where(VersiModel.aktif.is_(True)))
    lengkap = [a.kelengkapan for a in hari]
    return {
        "gedung": {"nama": g.nama, "luas_m2": g.luas_m2, "pv_kwp": g.kapasitas_pv_kwp},
        "waktu": now.isoformat(),
        "seri": seri,
        "angka": {
            "beban_kini_kw": _r(terakhir.beban_kw, 1) if terakhir else None,
            "beban_kini_jam": terakhir.waktu.isoformat() if terakhir else None,
            "beban_kini_prediksi": _r(pred[terakhir.waktu].nilai_kw, 1) if terakhir and terakhir.waktu in pred else None,
            "kwh_hari_ini": _r(kwh_hari, 1), "kwh_prediksi_hari_ini": _r(kwh_pred, 1),
            "pv_kwh_hari_ini": _r(pv_hari, 1), "pv_porsi": _r(pv_hari / kwh_hari * 100, 1) if kwh_hari else None,
            "rekomendasi_menunggu": menunggu, "tugas_aktif": len(tugas_saya),
        },
        "prediksi_besok": prediksi_besok,
        "peringatan": peringatan,
        "data_diam": data_diam,
        "tugas_saya": tugas_saya,
        "model": {"mape": model.mape, "mae": model.mae, "tanggal_latih": model.tanggal_latih.isoformat()} if model else None,
        "kelengkapan_hari_ini": _r(sum(lengkap) / len(lengkap) * 100, 1) if lengkap else None,
    }


# ------------------------------------------------------------------ rekomendasi
def _tugas_dict(t: Tugas) -> dict:
    r = t.rekomendasi
    return {"id": t.id, "rekomendasi_id": r.id, "nomor": r.nomor, "judul": r.judul, "lokasi": r.lokasi,
            "batas_waktu": t.batas_waktu.isoformat(), "selesai_pada": t.selesai_pada.isoformat() if t.selesai_pada else None,
            "catatan_bukti": t.catatan_bukti, "pelaksana": {"id": t.pelaksana.id, "nama": t.pelaksana.nama},
            "terlambat": t.selesai_pada is None and datetime.now() > t.batas_waktu, "dieskalasi": t.dieskalasi}


def _rec_dict(r: Rekomendasi, detail: bool = False) -> dict:
    an = r.anomali
    pemantauan_selesai = (r.dilaksanakan_pada + timedelta(days=recommend.PEMANTAUAN_HARI)) if r.dilaksanakan_pada else None
    d = {
        "id": r.id, "nomor": r.nomor, "judul": r.judul, "alasan": r.alasan, "lokasi": r.lokasi,
        "status": r.status, "estimasi_hemat_kwh": r.estimasi_hemat_kwh, "peluang_berulang": r.peluang_berulang,
        "kelebihan_kwh": an.kelebihan_kwh, "fitur_penting": r.fitur_penting,
        "dibuat_pada": r.dibuat_pada.isoformat(),
        "batas_respons": (r.dibuat_pada + timedelta(days=7)).isoformat(),
        "anomali": {"mulai": an.mulai.isoformat(), "selesai": an.selesai.isoformat(), "aturan": an.aturan,
                    "puncak_kw": an.puncak_residu_kw, "ruang_terjadwal": an.ruang_terjadwal},
        "pelaksana_disarankan": ({"id": r.pelaksana_disarankan.id, "nama": r.pelaksana_disarankan.nama}
                                 if r.pelaksana_disarankan else None),
        "diverifikasi_oleh": r.verifikator.nama if r.verifikator else None,
        "diverifikasi_pada": r.diverifikasi_pada.isoformat() if r.diverifikasi_pada else None,
        "alasan_tolak": r.alasan_tolak,
        "dilaksanakan_pada": r.dilaksanakan_pada.isoformat() if r.dilaksanakan_pada else None,
        "pemantauan_selesai": pemantauan_selesai.isoformat() if pemantauan_selesai else None,
        "siap_evaluasi": bool(r.status == "Dilaksanakan" and pemantauan_selesai and datetime.now() >= pemantauan_selesai),
        "tugas": [_tugas_dict(t) for t in r.tugas],
        "kejadian_berulang": sum(1 for h in r.riwayat if h.catatan.startswith("kejadian_berulang")),
        "evaluasi": ({"sebelum": r.evaluasi.konsumsi_sebelum_kwh, "sesudah": r.evaluasi.konsumsi_sesudah_kwh,
                      "pembanding_sebelum": r.evaluasi.pembanding_sebelum_kwh,
                      "pembanding_sesudah": r.evaluasi.pembanding_sesudah_kwh,
                      "hemat": r.evaluasi.hemat_kwh, "catatan": r.evaluasi.catatan,
                      "waktu": r.evaluasi.waktu.isoformat()} if r.evaluasi else None),
    }
    if detail:
        d["riwayat"] = [{"waktu": h.waktu.isoformat(), "dari": h.dari, "ke": h.ke, "catatan": h.catatan,
                         "oleh": h.oleh.nama if h.oleh else "Sistem"} for h in r.riwayat]
    return d


def _boleh_lihat(user: Pengguna, r: Rekomendasi) -> bool:
    if user.peran == "piket":
        return any(t.pelaksana_id == user.id for t in r.tugas)
    return True


@router.get("/rekomendasi")
def daftar_rekomendasi(status: str | None = None, user: Pengguna = Depends(require("rekomendasi.lihat")),
                       db: Session = Depends(get_db)):
    q = select(Rekomendasi).order_by(Rekomendasi.dibuat_pada.desc())
    if user.peran == "piket":
        q = q.where(Rekomendasi.id.in_(select(Tugas.rekomendasi_id).where(Tugas.pelaksana_id == user.id)))
    semua = list(db.scalars(q))
    hitung = {s: 0 for s in recommend.STATUS_URUT}
    for r in semua:
        hitung[r.status] += 1
    if status:
        semua = [r for r in semua if r.status == status]
    return {"hitung": hitung, "baris": [_rec_dict(r) for r in semua]}


def _ambil(db: Session, rid: str, user: Pengguna) -> Rekomendasi:
    r = db.get(Rekomendasi, rid)
    if not r or not _boleh_lihat(user, r):
        raise HTTPException(404, "Rekomendasi tidak ditemukan.")
    return r


@router.get("/rekomendasi/{rid}")
def detail_rekomendasi(rid: str, user: Pengguna = Depends(require("rekomendasi.lihat")),
                       db: Session = Depends(get_db)):
    r = _ambil(db, rid, user)
    d = _rec_dict(r, detail=True)
    an = r.anomali
    a, b = an.mulai - timedelta(hours=6), an.selesai + timedelta(hours=6)
    df = anomaly.residu(db, an.gedung_id, a, b)
    d["seri"] = [{"t": row.waktu.isoformat(), "aktual": _r(row.aktual), "prediksi": _r(row.prediksi),
                  "atas": _r(row.atas), "anomali": an.mulai <= row.waktu < an.selesai}
                 for row in df.itertuples()] if not df.empty else []
    if r.status == "Dilaksanakan" and user.peran in IZIN["evaluasi.catat"]:
        d["evaluasi_pratinjau"] = recommend.hitung_evaluasi(db, r)
    return d


class VerifikasiIn(BaseModel):
    pelaksana_id: str | None = None
    batas_jam: int | None = None
    catatan: str = ""


class TolakIn(BaseModel):
    alasan: str


class CatatanIn(BaseModel):
    catatan: str = ""


def _jalankan(db: Session, fn):
    try:
        hasil = fn()
        db.commit()
        return hasil
    except recommend.TransisiTidakSah as e:
        db.rollback()
        raise HTTPException(409, str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e))


@router.post("/rekomendasi/{rid}/verifikasi")
def verifikasi(rid: str, data: VerifikasiIn, user: Pengguna = Depends(require("rekomendasi.verifikasi")),
               db: Session = Depends(get_db)):
    r = _ambil(db, rid, user)
    if data.batas_jam is not None and not 2 <= data.batas_jam <= 336:
        raise HTTPException(422, "Batas waktu harus antara 2 jam dan 14 hari.")
    _jalankan(db, lambda: recommend.verifikasi(db, r, user, data.pelaksana_id, data.batas_jam, data.catatan))
    return _rec_dict(r, detail=True)


@router.post("/rekomendasi/{rid}/tolak")
def tolak(rid: str, data: TolakIn, user: Pengguna = Depends(require("rekomendasi.verifikasi")),
          db: Session = Depends(get_db)):
    r = _ambil(db, rid, user)
    _jalankan(db, lambda: recommend.tolak(db, r, user, data.alasan))
    return _rec_dict(r, detail=True)


@router.post("/rekomendasi/{rid}/evaluasi")
def evaluasi(rid: str, data: CatatanIn, user: Pengguna = Depends(require("evaluasi.catat")),
             db: Session = Depends(get_db)):
    r = _ambil(db, rid, user)
    _jalankan(db, lambda: recommend.catat_evaluasi(db, r, user, data.catatan))
    return _rec_dict(r, detail=True)


@router.post("/tugas/{tid}/selesai")
def tugas_selesai(tid: str, data: CatatanIn, user: Pengguna = Depends(require("tugas.tandai")),
                  db: Session = Depends(get_db)):
    t = db.get(Tugas, tid)
    if not t or (user.peran == "piket" and t.pelaksana_id != user.id):
        raise HTTPException(404, "Tugas tidak ditemukan.")
    if t.rekomendasi.status != "Diverifikasi":
        raise HTTPException(409, f"Rekomendasi berstatus {t.rekomendasi.status}; tugas tidak bisa ditandai.")
    _jalankan(db, lambda: recommend.tandai_selesai(db, t, user, data.catatan))
    return _tugas_dict(t)


@router.get("/pelaksana")
def pelaksana(user: Pengguna = Depends(require("rekomendasi.verifikasi")), db: Session = Depends(get_db)):
    out = []
    for p in db.scalars(select(Pengguna).where(Pengguna.peran == "piket", Pengguna.aktif.is_(True))
                        .order_by(Pengguna.nama)):
        aktif = db.scalar(select(func.count()).select_from(Tugas).where(
            Tugas.pelaksana_id == p.id, Tugas.selesai_pada.is_(None))) or 0
        out.append({"id": p.id, "nama": p.nama, "tugas_aktif": aktif})
    return out


# ------------------------------------------------------------------ notifikasi
@router.get("/notifikasi")
def notifikasi(user: Pengguna = Depends(current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Notifikasi).where(Notifikasi.pengguna_id == user.id)
                           .order_by(Notifikasi.waktu.desc()).limit(40)))
    belum = db.scalar(select(func.count()).select_from(Notifikasi).where(
        Notifikasi.pengguna_id == user.id, Notifikasi.dibaca.is_(False))) or 0
    return {"belum_dibaca": belum, "baris": [
        {"id": n.id, "jenis": n.jenis, "judul": n.judul, "isi": n.isi, "tautan": n.tautan, "dibaca": n.dibaca,
         "waktu": n.waktu.isoformat()} for n in rows]}


class BacaIn(BaseModel):
    ids: list[str] | None = None


@router.post("/notifikasi/baca")
def baca(data: BacaIn, user: Pengguna = Depends(current_user), db: Session = Depends(get_db)):
    q = update(Notifikasi).where(Notifikasi.pengguna_id == user.id)
    if data.ids:
        q = q.where(Notifikasi.id.in_(data.ids))
    db.execute(q.values(dibaca=True))
    db.commit()
    return {"ok": True}
