"""M3 mesin prediksi: Random Forest untuk beban gedung, model fisik sederhana untuk produksi PV."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import config, settings_store
from ..config import DATA_DIR
from ..models import AgregatJam, Cuaca, Gedung, Prediksi, VersiModel
from . import data_pipeline, simulate

FITUR = ["jam", "hari", "ruang_terjadwal", "suhu", "radiasi"]
LABEL_FITUR = {
    "jam": "Jam dalam hari",
    "hari": "Hari dalam pekan",
    "ruang_terjadwal": "Jumlah ruang terjadwal",
    "suhu": "Suhu prakiraan",
    "radiasi": "Radiasi matahari prakiraan",
}
MODEL_DIR = DATA_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
_cache: dict[str, RandomForestRegressor] = {}


# Jumlah thread pelatihan dibatasi agar muat di server kecil (mis. 512 MB); atur lewat SOLAR_JOBS.
N_JOBS = int(os.getenv("SOLAR_JOBS", str(min(4, os.cpu_count() or 1))))


def _rf(seed: int = 42) -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=300, min_samples_leaf=3, oob_score=True, n_jobs=N_JOBS,
                                 random_state=seed)


def frame(db: Session, gedung_id: str, mulai: datetime | None = None, selesai: datetime | None = None) -> pd.DataFrame:
    q = select(AgregatJam).where(AgregatJam.gedung_id == gedung_id)
    if mulai:
        q = q.where(AgregatJam.waktu >= mulai)
    if selesai:
        q = q.where(AgregatJam.waktu < selesai)
    rows = [{"waktu": a.waktu, "beban": a.beban_kw, "pv": a.produksi_pv_kw, "suhu": a.suhu, "radiasi": a.radiasi,
             "ruang_terjadwal": a.ruang_terjadwal, "kelengkapan": a.kelengkapan, "anomali": a.anomali}
            for a in db.scalars(q.order_by(AgregatJam.waktu))]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["waktu"] = pd.to_datetime(df["waktu"])
    df["jam"] = df["waktu"].dt.hour
    df["hari"] = df["waktu"].dt.weekday
    return df


def _bersih(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["beban"].notna() & df["suhu"].notna() & (df["kelengkapan"] >= 0.75)]


def _dua_lintasan(df: pd.DataFrame, ambang_kw: float, mad_kali: float) -> tuple[RandomForestRegressor, pd.Series]:
    """Lintasan 1 melatih model awal; residu ekstrem (berbasis OOB) dibuang; lintasan 2 melatih ulang.

    Mengembalikan model akhir dan mask baris yang dipakai.
    """
    X, y = df[FITUR].to_numpy(float), df["beban"].to_numpy(float)
    m1 = _rf()
    m1.fit(X, y)
    resid = y - m1.oob_prediction_
    mad = float(np.median(np.abs(resid - np.median(resid))))
    batas = max(ambang_kw, mad_kali * mad)
    keep = (np.abs(resid) <= batas) & ~df["anomali"].to_numpy(bool)
    m2 = _rf()
    m2.fit(X[keep], y[keep])
    return m2, pd.Series(keep, index=df.index)


def prediksi_rentang(model: RandomForestRegressor, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nilai tengah, persentil 10 dan 90 dari prediksi tiap pohon."""
    semua = np.stack([t.predict(X) for t in model.estimators_])
    return semua.mean(axis=0), np.percentile(semua, 10, axis=0), np.percentile(semua, 90, axis=0)


def mape(y: np.ndarray, p: np.ndarray) -> float:
    m = y > 0.5
    return float(np.mean(np.abs((y[m] - p[m]) / y[m])) * 100)


def latih(db: Session, gedung: Gedung, sekarang: datetime | None = None, catatan: str = "") -> VersiModel:
    """F08: latih ulang, uji mundur 14 hari terakhir, simpan versi, aktifkan bila MAPE <= 110 % model lama."""
    sekarang = sekarang or datetime.now()
    ambang_kw = settings_store.get(db, "ambang_kw")
    mad_kali = settings_store.get(db, "ambang_mad_kali")
    df = _bersih(frame(db, gedung.id, selesai=simulate.hour_floor(sekarang)))
    if len(df) < 24 * 21:
        raise ValueError("Data bersih kurang dari 21 hari. Model belum bisa dilatih.")
    batas_uji = df["waktu"].max() - pd.Timedelta(days=14)
    latih_df, uji_df = df[df["waktu"] <= batas_uji], df[df["waktu"] > batas_uji]

    # evaluasi rolling-origin: model dilatih hanya dari data sebelum jendela uji
    m_eval, _ = _dua_lintasan(latih_df, ambang_kw, mad_kali)
    uji_bersih = uji_df[~uji_df["anomali"]]
    p_uji, _, _ = prediksi_rentang(m_eval, uji_bersih[FITUR].to_numpy(float))
    y_uji = uji_bersih["beban"].to_numpy(float)
    nilai_mape, nilai_mae = mape(y_uji, p_uji), float(np.mean(np.abs(y_uji - p_uji)))

    # model produksi dilatih dari seluruh data bersih
    model, keep = _dua_lintasan(df, ambang_kw, mad_kali)
    penting = {k: round(float(v), 4) for k, v in zip(FITUR, model.feature_importances_)}

    versi = VersiModel(algoritma="RandomForestRegressor (300 pohon, min. 3 sampel per daun)",
                       tanggal_latih=sekarang, mape=round(nilai_mape, 2), mae=round(nilai_mae, 3),
                       jam_latih=int(keep.sum()), jam_uji=len(uji_bersih), fitur_penting=penting,
                       catatan=catatan)
    db.add(versi)
    db.flush()
    path = MODEL_DIR / f"{versi.id}.joblib"
    joblib.dump(model, path, compress=3)
    versi.berkas = str(path.name)

    lama = db.scalar(select(VersiModel).where(VersiModel.aktif.is_(True)))
    if lama is None or versi.mape <= lama.mape * 1.10:
        if lama:
            lama.aktif = False
        versi.aktif = True
        versi.catatan = (catatan + " Dipakai sebagai model aktif.").strip()
        _cache.clear()  # hanya model aktif yang disimpan di memori
        _cache[versi.id] = model
    else:
        versi.catatan = (catatan + f" Tidak dipakai: MAPE {versi.mape:.1f} % lebih buruk dari 110 % model aktif "
                                   f"({lama.mape:.1f} %).").strip()
    _bersihkan_berkas_lama(db)
    return versi


def _bersihkan_berkas_lama(db: Session, simpan: int = 8) -> None:
    """Simpan berkas model untuk 8 versi terakhir; metrik semua versi tetap tercatat."""
    versi = list(db.scalars(select(VersiModel).order_by(VersiModel.tanggal_latih.desc())))
    for v in versi[simpan:]:
        if v.aktif or not v.berkas:
            continue
        p = MODEL_DIR / v.berkas
        if p.exists():
            p.unlink()
        v.berkas = ""


def model_aktif(db: Session) -> tuple[VersiModel, RandomForestRegressor] | None:
    v = db.scalar(select(VersiModel).where(VersiModel.aktif.is_(True)))
    if not v:
        return None
    if v.id not in _cache:
        p = MODEL_DIR / v.berkas
        if not p.exists():
            return None
        _cache.clear()
        _cache[v.id] = joblib.load(p)
    return v, _cache[v.id]


def fitur_masa_depan(db: Session, gedung: Gedung, mulai: datetime, jam: int = 24) -> pd.DataFrame:
    jadwal = data_pipeline.jadwal_dict(db, gedung.id)
    cuaca = {c.waktu: c for c in db.scalars(select(Cuaca).where(
        Cuaca.waktu >= mulai, Cuaca.waktu < mulai + timedelta(hours=jam)))}
    rows = []
    for i in range(jam):
        t = mulai + timedelta(hours=i)
        c = cuaca.get(t)
        if c is not None:
            suhu, rad = c.suhu, c.radiasi
        elif config.SIMULATION:
            suhu, rad = simulate.cuaca_jam(t + timedelta(minutes=30))
        else:
            cad = data_pipeline.cuaca_cadangan(db, t)
            if cad is None:
                continue  # tanpa data cuaca sama sekali, jam ini tidak diprediksi
            suhu, rad = cad
        rows.append({"waktu": t, "jam": t.hour, "hari": t.weekday(),
                     "ruang_terjadwal": simulate.ruang_terjadwal_jam(jadwal, t), "suhu": suhu, "radiasi": rad})
    return pd.DataFrame(rows)


def prediksi_pv(db: Session, gedung: Gedung, radiasi: np.ndarray) -> np.ndarray:
    """F07: radiasi prakiraan x kapasitas terpasang (kWp) x faktor kinerja."""
    fk = settings_store.get(db, "faktor_kinerja_pv")
    return np.asarray(radiasi, float) / 1000.0 * gedung.kapasitas_pv_kwp * fk


def prediksi(db: Session, gedung: Gedung, mulai: datetime, jam: int = 24) -> int:
    """F06: simpan prediksi beban dan produksi PV untuk [mulai, mulai + jam)."""
    aktif = model_aktif(db)
    if not aktif:
        return 0
    versi, model = aktif
    f = fitur_masa_depan(db, gedung, mulai, jam)
    if f.empty:
        return 0
    mean, lo, hi = prediksi_rentang(model, f[FITUR].to_numpy(float))
    pv = prediksi_pv(db, gedung, f["radiasi"].to_numpy())
    db.execute(delete(Prediksi).where(Prediksi.gedung_id == gedung.id, Prediksi.waktu_target >= mulai,
                                      Prediksi.waktu_target < mulai + timedelta(hours=jam)))
    now = datetime.now()
    for i, t in enumerate(f["waktu"]):
        db.add(Prediksi(gedung_id=gedung.id, waktu_target=t.to_pydatetime() if hasattr(t, "to_pydatetime") else t,
                        model_id=versi.id, nilai_kw=round(float(mean[i]), 3), batas_bawah=round(float(lo[i]), 3),
                        batas_atas=round(float(hi[i]), 3), pv_kw=round(float(pv[i]), 3), dibuat_pada=now))
    return jam


def prediksi_riwayat(db: Session, gedung: Gedung, mulai: datetime, selesai: datetime) -> int:
    """Isi prediksi untuk jam lampau (seeding). Memakai model aktif; setara prediksi harian yang
    seharusnya sudah dibuat sehari sebelumnya."""
    n = 0
    t = mulai
    while t < selesai:
        jam = int(min(24 * 7, (selesai - t).total_seconds() // 3600))
        n += prediksi(db, gedung, t, jam)
        t += timedelta(hours=jam)
    return n


def penjelasan(versi: VersiModel, n: int = 3) -> list[dict]:
    items = sorted(versi.fitur_penting.items(), key=lambda kv: -kv[1])[:n]
    return [{"fitur": k, "label": LABEL_FITUR.get(k, k), "bobot": v} for k, v in items]


def model_path(versi: VersiModel) -> Path:
    return MODEL_DIR / versi.berkas
