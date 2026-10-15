"""M7 peringkat dan dampak: indeks efisiensi, baseline, kWh, rupiah, emisi, indikator, laporan CSV."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..models import (AgregatJam, Anomali, Evaluasi, Gedung, Pengguna, Rekomendasi, RiwayatStatus,
                      SkorPeringkat, Tugas, VersiModel)
from . import data_pipeline


def indeks_efisiensi(pembanding: float, intensitas: float) -> float:
    """F18: indeks = pembanding fungsi / intensitas aktual x 100."""
    if intensitas <= 0:
        return 0.0
    return round(pembanding / intensitas * 100, 1)


def intensitas_wh_m2_jam(kwh: float, luas_m2: float, jam_operasional: float) -> float:
    if luas_m2 <= 0 or jam_operasional <= 0:
        return 0.0
    return kwh * 1000 / (luas_m2 * jam_operasional)


def emisi_kg(kwh: float, faktor: float) -> float:
    """F19: emisi = energi x faktor emisi."""
    return kwh * faktor


def rupiah(kwh: float, tarif: float) -> float:
    return kwh * tarif


def _hari_ke_jam_operasional(g: Gedung, hari: int) -> float:
    return g.jam_operasional_pekan * hari / 7


def hitung_skor_bulanan(db: Session, gedung: Gedung, periode: date) -> SkorPeringkat | None:
    awal = datetime(periode.year, periode.month, 1)
    akhir = datetime(periode.year + (periode.month == 12), periode.month % 12 + 1, 1)
    akhir = min(akhir, datetime.now().replace(minute=0, second=0, microsecond=0))
    kwh = db.scalar(select(func.sum(AgregatJam.beban_kw)).where(
        AgregatJam.gedung_id == gedung.id, AgregatJam.waktu >= awal, AgregatJam.waktu < akhir))
    n = db.scalar(select(func.count()).select_from(AgregatJam).where(
        AgregatJam.gedung_id == gedung.id, AgregatJam.waktu >= awal, AgregatJam.waktu < akhir,
        AgregatJam.beban_kw.is_not(None)))
    if not kwh or not n:
        return None
    jam_total = (akhir - awal).total_seconds() / 3600
    kwh = kwh * jam_total / n  # isi celah data dengan rerata
    inten = intensitas_wh_m2_jam(kwh, gedung.luas_m2, _hari_ke_jam_operasional(gedung, jam_total / 24))
    acuan = settings_store.get(db, "pembanding_fungsi").get(gedung.fungsi, 10.0)
    row = db.scalar(select(SkorPeringkat).where(SkorPeringkat.gedung_id == gedung.id,
                                                SkorPeringkat.periode == periode))
    if row is None:
        row = SkorPeringkat(gedung_id=gedung.id, periode=periode, intensitas_wh_m2_jam=0, indeks_efisiensi=0)
        db.add(row)
    row.intensitas_wh_m2_jam = round(inten, 2)
    row.indeks_efisiensi = indeks_efisiensi(acuan, inten)
    return row


def peringkat(db: Session, periode: date | None = None) -> dict:
    periodes = sorted({r for r in db.scalars(select(SkorPeringkat.periode).distinct())}, reverse=True)
    if not periodes:
        return {"periode": None, "daftar_periode": [], "baris": []}
    periode = periode if periode in periodes else periodes[0]
    acuan = settings_store.get(db, "pembanding_fungsi")
    rows = db.execute(select(SkorPeringkat, Gedung).join(Gedung).where(SkorPeringkat.periode == periode)).all()
    sebelumnya = {}
    idx = periodes.index(periode)
    if idx + 1 < len(periodes):
        for s, g in db.execute(select(SkorPeringkat, Gedung).join(Gedung).where(
                SkorPeringkat.periode == periodes[idx + 1])):
            sebelumnya[g.id] = s.indeks_efisiensi
    baris = []
    for s, g in rows:
        baris.append({"gedung_id": g.id, "nama": g.nama, "fungsi": g.fungsi, "peran": g.peran,
                      "luas_m2": g.luas_m2, "jam_operasional_pekan": g.jam_operasional_pekan,
                      "intensitas": s.intensitas_wh_m2_jam, "pembanding": acuan.get(g.fungsi, 10.0),
                      "indeks": s.indeks_efisiensi,
                      "perubahan": round(s.indeks_efisiensi - sebelumnya[g.id], 1) if g.id in sebelumnya else None})
    baris.sort(key=lambda r: -r["indeks"])
    for i, r in enumerate(baris, 1):
        r["peringkat"] = i
    return {"periode": periode.isoformat(), "daftar_periode": [p.isoformat() for p in periodes], "baris": baris}


def _harian(db: Session, gedung_id: str, mulai: datetime, selesai: datetime) -> pd.DataFrame:
    rows = db.execute(select(AgregatJam.waktu, AgregatJam.beban_kw, AgregatJam.produksi_pv_kw).where(
        AgregatJam.gedung_id == gedung_id, AgregatJam.waktu >= mulai, AgregatJam.waktu < selesai)).all()
    df = pd.DataFrame(rows, columns=["waktu", "beban", "pv"])
    if df.empty:
        return df
    df["waktu"] = pd.to_datetime(df["waktu"])
    df["tgl"] = df["waktu"].dt.normalize()
    df["swakonsumsi"] = np.minimum(df["pv"].fillna(0), df["beban"].fillna(0))
    g = df.groupby("tgl").agg(kwh=("beban", "mean"), pv=("pv", "mean"), swa=("swakonsumsi", "mean"),
                              n=("beban", "count"))
    g["kwh"] *= 24
    g["pv"] *= 24
    g["swa"] *= 24
    return g.reset_index()


def dampak(db: Session) -> dict:
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    awal_data = db.scalar(select(func.min(AgregatJam.waktu)).where(AgregatJam.gedung_id == g.id))
    if awal_data is None:
        return {}
    akhir_baseline = awal_data + timedelta(days=90)
    tarif = settings_store.get(db, "tarif_rp_kwh")
    faktor = settings_store.get(db, "faktor_emisi")

    df = _harian(db, g.id, awal_data, now)
    df = df[df["n"] >= 18]
    df["dow"] = df["tgl"].dt.weekday
    base = df[df["tgl"] < akhir_baseline]
    base_dow = base.groupby("dow")["kwh"].mean()
    df["baseline"] = df["dow"].map(base_dow)

    evals = list(db.scalars(select(Evaluasi)))
    hemat = sum(e.hemat_kwh for e in evals)
    pilot = df[df["tgl"] >= akhir_baseline]
    pv_total = float(df["pv"].sum())
    swa_total = float(df["swa"].sum())

    seri = [{"tanggal": r.tgl.date().isoformat(), "kwh": round(float(r.kwh), 1),
             "baseline": round(float(r.baseline), 1) if pd.notna(r.baseline) else None,
             "pv": round(float(r.pv), 1)} for r in df.tail(60).itertuples()]

    return {
        "gedung": g.nama,
        "baseline": {"mulai": awal_data.date().isoformat(), "selesai": akhir_baseline.date().isoformat(),
                     "rerata_harian_kwh": round(float(base["kwh"].mean()), 1) if not base.empty else None},
        "pilot": {"rerata_harian_kwh": round(float(pilot["kwh"].mean()), 1) if not pilot.empty else None,
                  "hari": int(len(pilot))},
        "hemat_terukur_kwh": round(hemat, 1),
        "hemat_rp": round(rupiah(hemat, tarif)),
        "emisi_terhindar_kg": round(emisi_kg(hemat, faktor), 1),
        "jumlah_evaluasi": len(evals),
        "pv_kwh": round(pv_total, 1),
        "pv_swakonsumsi_kwh": round(swa_total, 1),
        "pv_emisi_terhindar_kg": round(emisi_kg(swa_total, faktor), 1),
        "pv_rp": round(rupiah(swa_total, tarif)),
        "tarif": tarif, "faktor_emisi": faktor,
        "seri": seri,
        "evaluasi": [
            {"rekomendasi_id": e.rekomendasi_id, "nomor": e.rekomendasi.nomor, "judul": e.rekomendasi.judul,
             "sebelum": e.konsumsi_sebelum_kwh, "sesudah": e.konsumsi_sesudah_kwh,
             "pembanding_sebelum": e.pembanding_sebelum_kwh, "pembanding_sesudah": e.pembanding_sesudah_kwh,
             "hemat": e.hemat_kwh, "waktu": e.waktu.isoformat(), "catatan": e.catatan}
            for e in sorted(evals, key=lambda e: e.waktu, reverse=True)],
        "indikator": indikator(db, g),
    }


def indikator(db: Session, g: Gedung) -> list[dict]:
    """Indikator keberhasilan dan metrik tujuan (PRD bagian Tujuan dan Evaluasi)."""
    now = datetime.now()
    sebulan = now - timedelta(days=30)
    kel = data_pipeline.kelengkapan_harian(db, g.id, 30)
    kelengkapan = float(np.mean([k["kelengkapan"] for k in kel])) * 100 if kel else 0

    v = db.scalar(select(VersiModel).where(VersiModel.aktif.is_(True)))

    anom = list(db.scalars(select(Anomali).where(Anomali.status.in_(["valid", "tidak_valid"]))))
    presisi = (sum(a.status == "valid" for a in anom) / len(anom) * 100) if anom else None

    recs = list(db.scalars(select(Rekomendasi)))
    diputus = [r for r in recs if r.status != "Diusulkan"]
    diverif = [r for r in recs if r.diverifikasi_pada]
    pct_verif = (len(diverif) / len(diputus) * 100) if diputus else None

    jeda = []
    for r in recs:
        akhir = r.diverifikasi_pada
        if akhir is None and r.status == "Ditolak":
            akhir = next((h.waktu for h in r.riwayat if h.ke == "Ditolak"), None)
        if akhir:
            jeda.append((akhir - r.dibuat_pada).total_seconds() / 3600)
    median_verif = float(np.median(jeda)) if jeda else None

    tugas = list(db.scalars(select(Tugas)))
    jatuh = [t for t in tugas if t.batas_waktu <= now or t.selesai_pada]
    tepat = [t for t in jatuh if t.selesai_pada and t.selesai_pada <= t.batas_waktu]
    pct_tepat = (len(tepat) / len(jatuh) * 100) if jatuh else None
    tujuh = [t for t in tugas if t.selesai_pada and t.selesai_pada - t.rekomendasi.diverifikasi_pada
             <= timedelta(days=7)]
    pct_7 = (len(tujuh) / len(jatuh) * 100) if jatuh else None

    mahasiswa = db.scalar(select(func.count()).select_from(Pengguna).where(
        Pengguna.peran.in_(["piket", "akademik", "tim"]), Pengguna.aktif.is_(True))) or 0

    def item(kode, nama, nilai, satuan, target, lulus, cara):
        return {"kode": kode, "nama": nama, "nilai": None if nilai is None else round(nilai, 1), "satuan": satuan,
                "target": target, "status": None if nilai is None else ("tercapai" if lulus(nilai) else "belum"),
                "cara": cara}

    return [
        item("kelengkapan", "Kelengkapan data", kelengkapan, "%", "95 % atau lebih", lambda x: x >= 95,
             "Jam dengan data valid dari meter, inverter, dan cuaca, 30 hari terakhir"),
        item("mape", "Akurasi prediksi beban (MAPE)", v.mape if v else None, "%", "15 % atau kurang",
             lambda x: x <= 15, "Uji mundur 14 hari pada model aktif"),
        item("presisi", "Presisi anomali", presisi, "%", "80 % atau lebih", lambda x: x >= 80,
             "Anomali yang dinilai valid dibagi seluruh anomali yang sudah dinilai"),
        item("verifikasi", "Rekomendasi yang diverifikasi", pct_verif, "%", "60 % atau lebih",
             lambda x: x >= 60, "Diverifikasi dibagi seluruh rekomendasi yang sudah diputuskan"),
        item("waktu_verifikasi", "Median waktu verifikasi", median_verif, "jam", "24 jam atau kurang",
             lambda x: x <= 24, "Dari rekomendasi muncul sampai diverifikasi atau ditolak"),
        item("pelaksanaan", "Pelaksanaan tepat waktu", pct_tepat, "%", "70 % atau lebih", lambda x: x >= 70,
             "Tugas selesai sebelum batas waktu"),
        item("tugas_7_hari", "Tugas selesai dalam 7 hari", pct_7, "%", "80 % atau lebih", lambda x: x >= 80,
             "Log tugas"),
        item("mahasiswa", "Keterlibatan mahasiswa", mahasiswa, "orang", "20 orang atau lebih",
             lambda x: x >= 20, "Akun aktif peran piket, akademik, dan tim pengelola"),
    ]


def aman_csv(v) -> str:
    """Cegah injeksi rumus spreadsheet dan pakai koma desimal (Excel berbahasa Indonesia)."""
    if isinstance(v, float):
        return f"{v:.1f}".replace(".", ",")
    if v is None:
        return ""
    t = str(v)
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


def laporan_csv(db: Session, mulai: date, selesai: date) -> str:
    """F20: konsumsi, produksi, anomali, dan hasil evaluasi per periode (harian)."""
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    a, b = datetime.combine(mulai, datetime.min.time()), datetime.combine(selesai, datetime.min.time()) + timedelta(days=1)
    df = _harian(db, g.id, a, b)
    anom = list(db.scalars(select(Anomali).where(Anomali.gedung_id == g.id, Anomali.mulai >= a, Anomali.mulai < b)))
    evs = list(db.scalars(select(Evaluasi).join(Rekomendasi).where(Evaluasi.waktu >= a, Evaluasi.waktu < b)))
    buf = io.StringIO()
    w0 = csv.writer(buf, delimiter=";")

    class _W:
        @staticmethod
        def writerow(row):
            w0.writerow([aman_csv(x) for x in row])
    w = _W()
    w.writerow(["# SOLAR-EDU AI laporan", g.nama, f"{mulai.isoformat()} s.d. {selesai.isoformat()}"])
    w.writerow(["# Data simulasi pada prototipe. Angka bukan hasil pengukuran."])
    w.writerow([])
    w.writerow(["tanggal", "konsumsi_kwh", "produksi_pv_kwh", "pv_terpakai_kwh", "jumlah_anomali",
                "kelebihan_anomali_kwh"])
    per_hari: dict[date, list[Anomali]] = {}
    for an in anom:
        per_hari.setdefault(an.mulai.date(), []).append(an)
    for r in df.itertuples():
        d = r.tgl.date()
        lst = per_hari.get(d, [])
        w.writerow([d.isoformat(), float(r.kwh), float(r.pv), float(r.swa), len(lst),
                    float(sum(x.kelebihan_kwh for x in lst))])
    w.writerow([])
    w.writerow(["rekomendasi", "judul", "konsumsi_sebelum_kwh", "konsumsi_sesudah_kwh", "pembanding_sebelum_kwh",
                "pembanding_sesudah_kwh", "hemat_kwh", "catatan"])
    for e in evs:
        w.writerow([f"R-{e.rekomendasi.nomor:03d}", e.rekomendasi.judul, e.konsumsi_sebelum_kwh,
                    e.konsumsi_sesudah_kwh, e.pembanding_sebelum_kwh, e.pembanding_sesudah_kwh, e.hemat_kwh,
                    e.catatan])
    return "\ufeff" + buf.getvalue()  # BOM agar Excel membaca UTF-8


def dataset_csv(db: Session, hari: int = 90) -> str:
    """F21: dataset agregat per jam tanpa data identitas."""
    g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
    mulai = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=hari)
    q = select(AgregatJam).where(AgregatJam.gedung_id == g.id, AgregatJam.waktu >= mulai).order_by(AgregatJam.waktu)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["waktu_wib", "beban_kw", "produksi_pv_kw", "suhu_c", "radiasi_w_m2", "ruang_terjadwal",
                "kelengkapan", "anomali"])
    for a in db.scalars(q):
        w.writerow([a.waktu.strftime("%Y-%m-%d %H:%M"), a.beban_kw, a.produksi_pv_kw, a.suhu, a.radiasi,
                    a.ruang_terjadwal, a.kelengkapan, int(a.anomali)])
    return buf.getvalue()
