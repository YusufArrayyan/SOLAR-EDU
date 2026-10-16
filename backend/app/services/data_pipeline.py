"""M1 akuisisi dan M2 penyimpanan, validasi, agregasi per jam."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import AgregatJam, Cuaca, Gedung, JadwalKuliah, Pengukuran, Perangkat, PeristiwaData, Ruang
from . import simulate

KUALITAS_VALID, KUALITAS_DIPERBAIKI, KUALITAS_DIBUANG = 0, 1, 2


def validasi(row: dict, batas_fisik_kw: float) -> int:
    """F04: nilai negatif dan lonjakan di atas batas fisik diberi bendera kualitas 2 (dibuang)."""
    for k in ("beban_kw", "produksi_pv_kw"):
        v = row.get(k)
        if v is None:
            continue
        if v < 0 or v > batas_fisik_kw:
            return KUALITAS_DIBUANG
    return KUALITAS_VALID


def simpan_pembacaan(db: Session, rows: list[dict]) -> int:
    """Simpan pembacaan mentah dengan bendera kualitas. Duplikat (waktu, perangkat) diabaikan."""
    if not rows:
        return 0
    batas = {p.id: p.batas_fisik_kw for p in db.scalars(select(Perangkat))}
    terakhir: dict[str, datetime] = {}
    for r in rows:
        r["kualitas"] = validasi(r, batas.get(r["perangkat_id"], 1000))
        if r["perangkat_id"] not in terakhir or r["waktu"] > terakhir[r["perangkat_id"]]:
            terakhir[r["perangkat_id"]] = r["waktu"]
    tabel = Pengukuran.__table__
    for i in range(0, len(rows), 5000):
        chunk = rows[i:i + 5000]
        if db.bind.dialect.name == "sqlite":
            db.execute(sqlite_insert(tabel).values(chunk).on_conflict_do_nothing())
        else:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            db.execute(pg_insert(tabel).values(chunk).on_conflict_do_nothing())
    for pid, t in terakhir.items():
        p = db.get(Perangkat, pid)
        if p and (p.terakhir_lapor is None or t > p.terakhir_lapor):
            p.terakhir_lapor = t
            p.status_terakhir = "aktif"
    return len(rows)


def jadwal_dict(db: Session, gedung_id: str | None = None) -> list[dict]:
    q = select(JadwalKuliah, Ruang).join(Ruang, JadwalKuliah.ruang_id == Ruang.id)
    if gedung_id:
        q = q.where(Ruang.gedung_id == gedung_id)
    return [{"ruang": r.nama, "hari": j.hari, "mulai": j.mulai, "selesai": j.selesai, "mata_kuliah": j.mata_kuliah}
            for j, r in db.execute(q)]


def agregasi(db: Session, gedung: Gedung, mulai: datetime, selesai: datetime, expected_per_jam: int,
             catat_jam: datetime | None = None) -> int:
    """F05: agregasi pembacaan valid per jam. Beban gedung = jumlah rerata panel meter."""
    perangkat = list(db.scalars(select(Perangkat).where(Perangkat.gedung_id == gedung.id)))
    meter_ids = [p.id for p in perangkat if p.jenis == "meter"]
    inv_ids = [p.id for p in perangkat if p.jenis == "inverter"]
    q = select(Pengukuran.waktu, Pengukuran.perangkat_id, Pengukuran.beban_kw, Pengukuran.produksi_pv_kw,
               Pengukuran.kualitas).where(
        Pengukuran.perangkat_id.in_(meter_ids + inv_ids), Pengukuran.waktu >= mulai, Pengukuran.waktu < selesai)
    df = pd.DataFrame(db.execute(q).all(), columns=["waktu", "pid", "beban", "pv", "kualitas"])
    jam_list = pd.date_range(mulai, selesai - timedelta(hours=1), freq="h")
    if len(jam_list) == 0:
        return 0
    jadwal = jadwal_dict(db, gedung.id) if gedung.peran == "percontohan" else jadwal_dict(db)
    cuaca = {c.waktu: c for c in db.scalars(select(Cuaca).where(Cuaca.waktu >= mulai, Cuaca.waktu < selesai))}

    if not df.empty:
        df["jam"] = pd.to_datetime(df["waktu"]).dt.floor("h")
        valid = df[df["kualitas"] == KUALITAS_VALID]
        mean_dev = valid.groupby(["jam", "pid"]).agg(beban=("beban", "mean"), pv=("pv", "mean"),
                                                     n=("kualitas", "size")).reset_index()
    else:
        mean_dev = pd.DataFrame(columns=["jam", "pid", "beban", "pv", "n"])

    n_dev = len(meter_ids) + len(inv_ids)
    m = mean_dev[mean_dev["pid"].isin(meter_ids)]
    v = mean_dev[mean_dev["pid"].isin(inv_ids)]
    beban_jam = m.groupby("jam")["beban"].agg(["sum", "count"])
    pv_jam = v.groupby("jam")["pv"].agg(["sum", "count"])
    n_jam = mean_dev.groupby("jam")["n"].sum()
    rows = []
    for jam in jam_list:
        jam_py = jam.to_pydatetime()
        beban = None
        if meter_ids and jam in beban_jam.index and beban_jam.at[jam, "count"] == len(meter_ids):
            beban = float(beban_jam.at[jam, "sum"])
        if not inv_ids:
            # tanpa inverter terdaftar: 0 hanya untuk gedung tanpa panel surya, selain itu "tidak ada data"
            pv = 0.0 if not gedung.kapasitas_pv_kwp else None
        elif jam in pv_jam.index and pv_jam.at[jam, "count"] == len(inv_ids):
            pv = float(pv_jam.at[jam, "sum"])
        else:
            pv = None
        kelengkapan = float(n_jam.get(jam, 0)) / (expected_per_jam * n_dev) if n_dev else 0.0
        c = cuaca.get(jam_py)
        rows.append({
            "gedung_id": gedung.id, "waktu": jam_py,
            "beban_kw": round(beban, 3) if beban is not None else None,
            "produksi_pv_kw": round(pv, 3) if pv is not None else None,
            "suhu": c.suhu if c else None, "radiasi": c.radiasi if c else None,
            "ruang_terjadwal": simulate.ruang_terjadwal_jam(jadwal, jam_py),
            "kelengkapan": round(min(1.0, kelengkapan), 4), "anomali": False,
        })
    if catat_jam is not None and n_dev:
        # F01: paket hilang dicatat untuk jam yang sudah final (tidak akan menerima paket terlambat lagi)
        harap = expected_per_jam * n_dev
        diterima = int(n_jam.get(pd.Timestamp(catat_jam), 0))
        if diterima < harap:
            catat_peristiwa(db, "paket_hilang", f"{gedung.nama}, {catat_jam:%d-%m %H.00}: {harap - diterima} dari "
                                               f"{harap} pembacaan valid tidak diterima.")
    db.execute(delete(AgregatJam).where(AgregatJam.gedung_id == gedung.id, AgregatJam.waktu >= mulai,
                                        AgregatJam.waktu < selesai))
    for i in range(0, len(rows), 2000):
        db.execute(AgregatJam.__table__.insert(), rows[i:i + 2000])
    return len(rows)


def simpan_cuaca(db: Session, mulai: datetime, selesai: datetime, sumber: str = "simulasi",
                 data: list[tuple[datetime, float, float]] | None = None) -> None:
    """F02: simpan observasi/prakiraan suhu dan radiasi per jam."""
    now = datetime.now()
    if data is None:
        data = []
        t = mulai
        while t < selesai:
            suhu, rad = simulate.cuaca_jam(t + timedelta(minutes=30))
            data.append((t, suhu, rad))
            t += timedelta(hours=1)
    for t, suhu, rad in data:
        row = db.get(Cuaca, t)
        if row:
            row.suhu, row.radiasi, row.sumber, row.diambil_pada = suhu, rad, sumber, now
        else:
            db.add(Cuaca(waktu=t, suhu=suhu, radiasi=rad, sumber=sumber, diambil_pada=now))


def ambil_cuaca_open_meteo(lat: float, lon: float) -> list[tuple[datetime, float, float]]:
    """Prakiraan 48 jam dari Open-Meteo (penyedia terbuka). Dipakai bila WEATHER_LIVE=1."""
    import httpx
    r = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "hourly": "temperature_2m,shortwave_radiation",
        "timezone": "Asia/Jakarta", "forecast_days": 3}, timeout=15)
    r.raise_for_status()
    h = r.json()["hourly"]
    out = []
    for t, suhu, rad in zip(h["time"], h["temperature_2m"], h["shortwave_radiation"]):
        out.append((datetime.fromisoformat(t), float(suhu), float(rad)))
    return out[:72]


def catat_peristiwa(db: Session, jenis: str, detail: str) -> None:
    db.add(PeristiwaData(jenis=jenis, detail=detail, waktu=datetime.now()))


def kelengkapan_harian(db: Session, gedung_id: str, hari: int = 30) -> list[dict]:
    mulai = simulate.hour_floor(datetime.now()) - timedelta(days=hari)
    rows = db.execute(select(AgregatJam.waktu, AgregatJam.kelengkapan, AgregatJam.beban_kw).where(
        AgregatJam.gedung_id == gedung_id, AgregatJam.waktu >= mulai)).all()
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=["waktu", "kel", "beban"])
    df["tgl"] = pd.to_datetime(df["waktu"]).dt.date
    df["valid"] = (df["kel"] >= 0.75) & df["beban"].notna()
    g = df.groupby("tgl")["valid"].mean().reset_index()
    return [{"tanggal": str(r.tgl), "kelengkapan": round(float(r.valid), 4)} for r in g.itertuples()]


def cuaca_cadangan(db: Session, t: datetime) -> tuple[float, float] | None:
    """Prakiraan cadangan yang jujur bila penyedia cuaca gagal: nilai jam yang sama kemarin (persistensi),
    lalu rerata jam yang sama 7 hari terakhir. Tidak memakai cuaca rekaan."""
    for hari in (1, 2):
        c = db.get(Cuaca, t - timedelta(days=hari))
        if c is not None:
            return c.suhu, c.radiasi
    rows = [db.get(Cuaca, t - timedelta(days=h)) for h in range(1, 8)]
    rows = [r for r in rows if r is not None]
    if rows:
        return (round(sum(r.suhu for r in rows) / len(rows), 1), round(sum(r.radiasi for r in rows) / len(rows), 1))
    return None


def isi_cuaca_cadangan(db: Session, mulai: datetime, selesai: datetime) -> int:
    """Lengkapi jam yang belum punya prakiraan dengan cadangan persistensi."""
    n = 0
    t = mulai
    while t < selesai:
        if db.get(Cuaca, t) is None:
            nilai = cuaca_cadangan(db, t)
            if nilai is not None:
                db.add(Cuaca(waktu=t, suhu=nilai[0], radiasi=nilai[1], sumber="persistensi", diambil_pada=datetime.now()))
                db.flush()
                n += 1
        t += timedelta(hours=1)
    return n
