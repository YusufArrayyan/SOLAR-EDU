"""M4 deteksi anomali dari residu terhadap prediksi, ditambah aturan jadwal (F09, F10)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import settings_store
from ..models import AgregatJam, Anomali, Gedung, Pengukuran, Perangkat, Prediksi


@dataclass
class Ambang:
    kw: float
    mad_kali: float
    jam: int
    mad: float

    @property
    def nilai(self) -> float:
        return max(self.kw, self.mad_kali * self.mad)


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Rentang indeks [a, b) dengan mask True berturut-turut sepanjang min_len atau lebih."""
    out, a = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and a is None:
            a = i
        elif not v and a is not None:
            if i - a >= min_len:
                out.append((a, i))
            a = None
    return out


def residu(db: Session, gedung_id: str, mulai: datetime, selesai: datetime) -> pd.DataFrame:
    q = (select(AgregatJam.waktu, AgregatJam.beban_kw, AgregatJam.ruang_terjadwal, Prediksi.nilai_kw,
                Prediksi.batas_atas)
         .join(Prediksi, (Prediksi.gedung_id == AgregatJam.gedung_id) & (Prediksi.waktu_target == AgregatJam.waktu))
         .where(AgregatJam.gedung_id == gedung_id, AgregatJam.waktu >= mulai, AgregatJam.waktu < selesai)
         .order_by(AgregatJam.waktu))
    df = pd.DataFrame(db.execute(q).all(), columns=["waktu", "aktual", "ruang", "prediksi", "atas"])
    if not df.empty:
        df["residu"] = df["aktual"] - df["prediksi"]
    return df


def hitung_ambang(db: Session, gedung_id: str, sampai: datetime) -> Ambang:
    """MAD residu bergulir 28 hari, di luar jam yang sudah ditandai anomali."""
    df = residu(db, gedung_id, sampai - timedelta(days=28), sampai)
    anom = {a.waktu for a in db.scalars(select(AgregatJam).where(
        AgregatJam.gedung_id == gedung_id, AgregatJam.anomali.is_(True),
        AgregatJam.waktu >= sampai - timedelta(days=28)))}
    if not df.empty:
        df = df[~df["waktu"].isin(anom)].dropna(subset=["residu"])
    r = df["residu"].to_numpy(float) if not df.empty else np.array([0.0])
    mad = float(np.median(np.abs(r - np.median(r))))
    return Ambang(settings_store.get(db, "ambang_kw"), settings_store.get(db, "ambang_mad_kali"),
                  settings_store.get(db, "ambang_jam"), mad)


def panel_dicurigai(db: Session, gedung_id: str, a: datetime, b: datetime) -> tuple[Perangkat | None, float]:
    """Panel dengan kelebihan terbesar dibanding median panel itu pada jam dan jenis hari yang sama (28 hari)."""
    meters = list(db.scalars(select(Perangkat).where(Perangkat.gedung_id == gedung_id, Perangkat.jenis == "meter")))
    if len(meters) <= 1:
        return (meters[0] if meters else None), 0.0
    awal = a - timedelta(days=28)
    rows = db.execute(select(Pengukuran.waktu, Pengukuran.perangkat_id, Pengukuran.beban_kw).where(
        Pengukuran.perangkat_id.in_([m.id for m in meters]), Pengukuran.waktu >= awal, Pengukuran.waktu < b,
        Pengukuran.kualitas == 0)).all()
    df = pd.DataFrame(rows, columns=["waktu", "pid", "beban"])
    if df.empty:
        return None, 0.0
    df["waktu"] = pd.to_datetime(df["waktu"])
    df["jam"] = df["waktu"].dt.hour
    df["hari"] = df["waktu"].dt.weekday
    jendela = (df["waktu"] >= a) & (df["waktu"] < b)
    # jadwal kuliah berulang tiap pekan, jadi acuan dibandingkan per hari dan jam yang sama
    acuan = df[~jendela].groupby(["pid", "jam", "hari"])["beban"].median()
    kini = df[jendela]
    terbaik, nilai = None, -1e9
    for m in meters:
        k = kini[kini["pid"] == m.id]
        if k.empty:
            continue
        exp = [acuan.get((m.id, r.jam, r.hari), np.nan) for r in k.itertuples()]
        lebih = float(np.nansum(k["beban"].to_numpy() - np.array(exp, float)))
        if lebih > nilai:
            terbaik, nilai = m, lebih
    return terbaik, max(0.0, nilai)


def deteksi(db: Session, gedung: Gedung, mulai: datetime, selesai: datetime,
            sekarang: datetime | None = None) -> list[Anomali]:
    """F09: residu > max(ambang kW, k x MAD) selama >= N jam. F10: beban tinggi tanpa kelas terjadwal."""
    sekarang = sekarang or datetime.now()
    amb = hitung_ambang(db, gedung.id, mulai)
    df = residu(db, gedung.id, mulai, selesai)
    baru: list[Anomali] = []
    if df.empty:
        return baru
    df = df.dropna(subset=["residu"]).reset_index(drop=True)
    batas = amb.nilai
    mask = (df["residu"] > batas).to_numpy()
    for a, b in runs(mask, amb.jam):
        baru += _buat(db, gedung, df.iloc[a:b], "residu", sekarang)

    if settings_store.get(db, "aturan_jadwal_aktif"):
        batas_kw = settings_store.get(db, "aturan_jadwal_kw")
        mask2 = ((df["ruang"] == 0) & (df["aktual"] > batas_kw)).to_numpy()
        for a, b in runs(mask2, amb.jam):
            baru += _buat(db, gedung, df.iloc[a:b], "jadwal", sekarang)
    return baru


def _buat(db: Session, gedung: Gedung, seg: pd.DataFrame, aturan: str, sekarang: datetime) -> list[Anomali]:
    a = pd.Timestamp(seg["waktu"].iloc[0]).to_pydatetime()
    b = pd.Timestamp(seg["waktu"].iloc[-1]).to_pydatetime() + timedelta(hours=1)
    lebih = float(seg["residu"].clip(lower=0).sum())
    lama = db.scalar(select(Anomali).where(Anomali.gedung_id == gedung.id, Anomali.mulai < b,
                                           Anomali.selesai > a).order_by(Anomali.mulai).limit(1))
    if lama is not None:
        # anomali yang masih berlangsung: perpanjang, jangan buat baru
        if b > lama.selesai and lama.mulai <= a + timedelta(hours=1) and lama.aturan == aturan:
            lama.selesai = b
            lama.kelebihan_kwh = round(max(lama.kelebihan_kwh, lebih), 2)
            lama.puncak_residu_kw = round(max(lama.puncak_residu_kw, float(seg["residu"].max())), 2)
            db.execute(update(AgregatJam).where(AgregatJam.gedung_id == gedung.id, AgregatJam.waktu >= a,
                                                AgregatJam.waktu < b).values(anomali=True))
        return []
    if lebih <= 0:
        return []
    panel, _ = panel_dicurigai(db, gedung.id, a, b)
    an = Anomali(gedung_id=gedung.id, mulai=a, selesai=b, kelebihan_kwh=round(lebih, 2),
                 puncak_residu_kw=round(float(seg["residu"].max()), 2),
                 ruang_terjadwal=int(seg["ruang"].max()), perangkat_id=panel.id if panel else None,
                 aturan=aturan, status="baru", dibuat_pada=sekarang)
    db.add(an)
    db.execute(update(AgregatJam).where(AgregatJam.gedung_id == gedung.id, AgregatJam.waktu >= a,
                                        AgregatJam.waktu < b).values(anomali=True))
    db.flush()
    return [an]
