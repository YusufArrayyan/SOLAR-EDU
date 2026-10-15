"""M5 rekomendasi dan verifikasi. Sistem hanya mengusulkan; manusia memverifikasi dan melaksanakan."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import settings_store
from ..models import (AgregatJam, Anomali, Evaluasi, Gedung, Pengguna, Pengukuran, Perangkat, Rekomendasi,
                      RiwayatStatus, Ruang, Tugas)
from ..security import audit
from .. import config
from . import forecast, notify, sim_state, simulate

TRANSISI: dict[str, set[str]] = {
    "Diusulkan": {"Diverifikasi", "Ditolak", "Kedaluwarsa"},
    "Diverifikasi": {"Dilaksanakan", "Kedaluwarsa"},
    "Dilaksanakan": {"Dievaluasi"},
    "Dievaluasi": set(),
    "Ditolak": set(),
    "Kedaluwarsa": set(),
}
STATUS_URUT = ["Diusulkan", "Diverifikasi", "Dilaksanakan", "Dievaluasi", "Ditolak", "Kedaluwarsa"]
PEMANTAUAN_HARI = 14


class TransisiTidakSah(ValueError):
    pass


def ubah_status(db: Session, rec: Rekomendasi, ke: str, oleh: Pengguna | None, catatan: str = "",
                waktu: datetime | None = None) -> None:
    """F13: perpindahan mengikuti diagram state; status tidak bisa melompat."""
    if ke not in TRANSISI.get(rec.status, set()):
        raise TransisiTidakSah(f"Status {rec.status} tidak bisa langsung berpindah ke {ke}.")
    db.add(RiwayatStatus(rekomendasi_id=rec.id, dari=rec.status, ke=ke, oleh_id=oleh.id if oleh else None,
                         waktu=waktu or datetime.now(), catatan=catatan))
    rec.status = ke


# ------------------------------------------------------------------ pembuatan
_bucket = simulate.bucket


def _judul(panel: Perangkat | None, t: datetime) -> str:
    b = _bucket(t)
    kode = panel.kode if panel else ""
    if kode.endswith("panel-lab"):
        return ("Matikan komputer laboratorium sebelum akhir pekan" if b == "akhir_pekan"
                else "Matikan komputer laboratorium setelah praktikum terakhir")
    if kode.endswith("panel-l1"):
        return {"malam": "Matikan lampu lobi dan pompa air di luar jam operasional",
                "akhir_pekan": "Periksa pemakaian aula lantai 1 pada akhir pekan"}.get(
            b, "Periksa peralatan lantai 1 yang menyala di luar pola biasa")
    for lantai in ("2", "3"):
        if kode.endswith(f"panel-l{lantai}"):
            return {"sore": f"Matikan AC ruang kuliah lantai {lantai} setelah kelas terakhir",
                    "siang": f"Matikan AC ruang kuliah lantai {lantai} saat jeda siang",
                    "malam": f"Matikan AC dan lampu lantai {lantai} di malam hari",
                    "akhir_pekan": f"Periksa AC lantai {lantai} yang menyala pada akhir pekan"}.get(
                b, f"Periksa AC dan lampu lantai {lantai}")
    return "Periksa beban gedung yang melebihi prediksi"


def peluang_berulang(db: Session, an: Anomali) -> float:
    """Porsi hari serupa dalam 28 hari terakhir yang memiliki anomali serupa pada panel yang sama."""
    awal = an.mulai - timedelta(days=28)
    sebelumnya = list(db.scalars(select(Anomali).where(
        Anomali.gedung_id == an.gedung_id, Anomali.perangkat_id == an.perangkat_id,
        Anomali.mulai >= awal, Anomali.mulai <= an.mulai, Anomali.status != "tidak_valid")))
    b = _bucket(an.mulai)
    serupa = {a.mulai.date() for a in sebelumnya if _bucket(a.mulai) == b}
    hari_serupa = 8 if b == "akhir_pekan" else 20
    if len(serupa) <= 1:
        return 0.25
    return round(min(0.95, max(0.1, len(serupa) / hari_serupa)), 2)


def _pelaksana(db: Session) -> Pengguna | None:
    piket = list(db.scalars(select(Pengguna).where(Pengguna.peran == "piket", Pengguna.aktif.is_(True))))
    if not piket:
        return None
    beban = {p.id: db.scalar(select(func.count()).select_from(Tugas).where(
        Tugas.pelaksana_id == p.id, Tugas.selesai_pada.is_(None))) or 0 for p in piket}
    return min(piket, key=lambda p: (beban[p.id], p.nama))


def _jam(t: datetime) -> str:
    return t.strftime("%H.%M")


def _num(x: float, d: int = 1) -> str:
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def rekomendasi_terbuka_serupa(db: Session, an: Anomali) -> Rekomendasi | None:
    """Rekomendasi yang masih berjalan untuk panel dan rentang waktu yang sama."""
    for r in db.scalars(select(Rekomendasi).join(Anomali).where(
            Rekomendasi.status.in_(["Diusulkan", "Diverifikasi", "Dilaksanakan"]),
            Anomali.perangkat_id == an.perangkat_id, Anomali.id != an.id)):
        if _bucket(r.anomali.mulai) == _bucket(an.mulai):
            return r
    return None


def buat_dari_anomali(db: Session, an: Anomali, waktu: datetime | None = None,
                      beri_tahu: bool = True) -> Rekomendasi | None:
    """F11: rekomendasi dengan alasan, lokasi, pelaksana disarankan, dan estimasi hemat.

    Bila rekomendasi serupa masih berjalan, anomali dicatat sebagai kejadian berulang tanpa membuat
    rekomendasi baru, supaya daftar pengelola tidak menumpuk.
    """
    waktu = waktu or datetime.now()
    serupa = rekomendasi_terbuka_serupa(db, an)
    if serupa is not None:
        an.status = "berulang"
        db.add(RiwayatStatus(rekomendasi_id=serupa.id, dari=serupa.status, ke=serupa.status, waktu=waktu,
                             catatan=f"kejadian_berulang:{an.mulai.isoformat()}"))
        if serupa.status == "Dilaksanakan":
            notify.ke_peran(db, ["pengelola"], "kambuh", f"Pola muncul lagi: {serupa.judul}",
                            f"Anomali serupa tercatat {an.mulai:%d-%m %H.%M} WIB selama pemantauan.",
                            f"#/rekomendasi/{serupa.id}", waktu=waktu)
        return None
    panel = db.get(Perangkat, an.perangkat_id) if an.perangkat_id else None
    ruang = list(db.scalars(select(Ruang).where(Ruang.perangkat_id == panel.id))) if panel else []
    lokasi = (panel.nama if panel else "Seluruh gedung") + (
        f" ({', '.join(r.nama for r in ruang)})" if ruang else "")
    peluang = peluang_berulang(db, an)
    durasi = int(round((an.selesai - an.mulai).total_seconds() / 3600))
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][an.mulai.weekday()]
    kalimat = [
        f"Beban gedung melebihi prediksi hingga {_num(an.puncak_residu_kw)} kW selama {durasi} jam "
        f"({hari}, {_jam(an.mulai)}–{_jam(an.selesai)} WIB), total kelebihan {_num(an.kelebihan_kwh)} kWh."
    ]
    if an.ruang_terjadwal == 0:
        kalimat.append("Pada jam itu beban tinggi saat tidak ada kelas terjadwal.")
    else:
        kalimat.append(f"Pada jam itu terjadwal {an.ruang_terjadwal} ruang, tetapi beban tetap di atas pola biasa.")
    if panel:
        kalimat.append(f"Kenaikan terbesar tercatat pada {panel.nama.lower()}.")
    if an.aturan == "jadwal":
        kalimat.append("Ditandai oleh aturan jadwal: beban tinggi tanpa kelas terjadwal.")
    if peluang > 0.25:
        kalimat.append(f"Pola serupa muncul pada {round(peluang * 100)} % hari sejenis dalam 28 hari terakhir.")

    aktif = forecast.model_aktif(db)
    fitur = forecast.penjelasan(aktif[0]) if aktif else []
    nilai_fitur = db.get(AgregatJam, (an.gedung_id, an.mulai))
    if nilai_fitur:
        nilai = {"jam": f"{an.mulai.hour:02d}.00", "hari": hari,
                 "ruang_terjadwal": str(nilai_fitur.ruang_terjadwal),
                 "suhu": f"{_num(nilai_fitur.suhu or 0)} °C", "radiasi": f"{round(nilai_fitur.radiasi or 0)} W/m²"}
        for f in fitur:
            f["nilai"] = nilai.get(f["fitur"], "")

    pelaksana = _pelaksana(db)
    no = (db.scalar(select(func.max(Rekomendasi.nomor))) or 0) + 1
    rec = Rekomendasi(nomor=no, anomali_id=an.id, judul=_judul(panel, an.mulai), alasan=" ".join(kalimat),
                      fitur_penting=fitur, lokasi=lokasi, estimasi_hemat_kwh=round(an.kelebihan_kwh * peluang, 2),
                      peluang_berulang=peluang, status="Diusulkan",
                      pelaksana_disarankan_id=pelaksana.id if pelaksana else None, dibuat_pada=waktu)
    db.add(rec)
    db.flush()
    db.add(RiwayatStatus(rekomendasi_id=rec.id, dari=None, ke="Diusulkan", waktu=waktu,
                         catatan="Dibuat otomatis dari anomali."))
    if beri_tahu:
        notify.ke_peran(db, ["pengelola", "tim"], "rekomendasi_baru", f"Rekomendasi baru: {rec.judul}",
                        f"Estimasi hemat {_num(rec.estimasi_hemat_kwh)} kWh. Perlu verifikasi.",
                        f"#/rekomendasi/{rec.id}", waktu=waktu)
    return rec


# ------------------------------------------------------------------ aksi manusia
def verifikasi(db: Session, rec: Rekomendasi, oleh: Pengguna, pelaksana_id: str | None = None,
               batas_jam: int | None = None, catatan: str = "", waktu: datetime | None = None) -> Tugas:
    """F12: verifikasi lalu tetapkan pelaksana; tugas dikirim ke mahasiswa piket."""
    waktu = waktu or datetime.now()
    pelaksana = db.get(Pengguna, pelaksana_id or rec.pelaksana_disarankan_id or "")
    if not pelaksana or pelaksana.peran not in ("piket", "pengelola", "tim") or not pelaksana.aktif:
        raise ValueError("Pilih pelaksana dari mahasiswa piket yang aktif.")
    ubah_status(db, rec, "Diverifikasi", oleh, catatan, waktu)
    rec.diverifikasi_oleh, rec.diverifikasi_pada = oleh.id, waktu
    rec.anomali.status = "valid"
    batas = waktu + timedelta(hours=batas_jam or settings_store.get(db, "batas_tugas_jam"))
    t = Tugas(rekomendasi_id=rec.id, pelaksana_id=pelaksana.id, batas_waktu=batas)
    db.add(t)
    audit(db, oleh.id, "rekomendasi.verifikasi", f"R-{rec.nomor:03d} {rec.judul}; pelaksana {pelaksana.nama}")
    notify.kirim(db, [pelaksana], "tugas_baru", f"Tugas baru: {rec.judul}",
                 f"Batas waktu {batas:%d-%m-%Y %H.%M} WIB. {rec.lokasi}", "#/rekomendasi", waktu=waktu)
    return t


def tolak(db: Session, rec: Rekomendasi, oleh: Pengguna, alasan: str, waktu: datetime | None = None) -> None:
    """F12: penolakan wajib beri alasan; alasan menjadi umpan balik model dan ambang."""
    alasan = (alasan or "").strip()
    if len(alasan) < 5:
        raise ValueError("Tulis alasan penolakan, minimal 5 karakter.")
    waktu = waktu or datetime.now()
    ubah_status(db, rec, "Ditolak", oleh, alasan, waktu)
    rec.alasan_tolak = alasan
    an = rec.anomali
    an.status = "tidak_valid"
    # umpan balik: jam ini dianggap normal lagi sehingga ikut dipelajari pada latih ulang berikutnya
    for a in db.scalars(select(AgregatJam).where(AgregatJam.gedung_id == an.gedung_id,
                                                 AgregatJam.waktu >= an.mulai, AgregatJam.waktu < an.selesai)):
        a.anomali = False
    audit(db, oleh.id, "rekomendasi.tolak", f"R-{rec.nomor:03d} {rec.judul}; alasan: {alasan}")


def tandai_selesai(db: Session, tugas: Tugas, oleh: Pengguna, catatan: str, waktu: datetime | None = None) -> None:
    """F17: bukti selesai berupa tanda dan catatan. Rekomendasi pindah ke Dilaksanakan."""
    if tugas.selesai_pada:
        raise ValueError("Tugas ini sudah ditandai selesai.")
    catatan = (catatan or "").strip()
    if len(catatan) < 3:
        raise ValueError("Tulis catatan singkat sebagai bukti, misalnya ruang yang sudah dicek.")
    waktu = waktu or datetime.now()
    tugas.selesai_pada, tugas.catatan_bukti = waktu, catatan
    rec = tugas.rekomendasi
    if all(t.selesai_pada for t in rec.tugas):
        ubah_status(db, rec, "Dilaksanakan", oleh, catatan, waktu)
        rec.dilaksanakan_pada = waktu
        notify.ke_peran(db, ["pengelola"], "tugas_selesai", f"Dilaksanakan: {rec.judul}",
                        f"Pemantauan {PEMANTAUAN_HARI} hari dimulai. Catatan: {catatan}",
                        f"#/rekomendasi/{rec.id}", waktu=waktu)
    audit(db, oleh.id, "tugas.selesai", f"R-{rec.nomor:03d}; {catatan}")
    if config.SIMULATION and rec.anomali.perangkat_id:
        # Mode simulasi: tindakan di lapangan menghentikan kebiasaan boros yang cocok.
        state = sim_state.get(db)
        panel = db.get(Perangkat, rec.anomali.perangkat_id)
        if state and panel:
            simulate.tandai_diperbaiki(state, panel.kode, rec.anomali.mulai, waktu)
            sim_state.save(db, state)


def _kwh(db: Session, perangkat_ids: list[str], a: datetime, b: datetime) -> float:
    """Energi (kWh) dari rerata pembacaan valid per jam pada [a, b)."""
    rows = db.execute(select(func.avg(Pengukuran.beban_kw)).where(
        Pengukuran.perangkat_id.in_(perangkat_ids), Pengukuran.waktu >= a, Pengukuran.waktu < b,
        Pengukuran.kualitas == 0).group_by(Pengukuran.perangkat_id)).all()
    jam = (b - a).total_seconds() / 3600
    return float(sum((r[0] or 0) for r in rows) * jam)


def hitung_evaluasi(db: Session, rec: Rekomendasi) -> dict:
    """F14: konsumsi 14 hari sebelum dan sesudah tindakan, dibanding gedung pembanding (selisih-dalam-selisih)."""
    t0 = rec.dilaksanakan_pada
    if t0 is None:
        raise ValueError("Rekomendasi belum dilaksanakan.")
    a, b = t0 - timedelta(days=PEMANTAUAN_HARI), t0 + timedelta(days=PEMANTAUAN_HARI)
    an = rec.anomali
    if an.perangkat_id:
        ids = [an.perangkat_id]
        cakupan = db.get(Perangkat, an.perangkat_id).nama
    else:
        ids = [p.id for p in db.scalars(select(Perangkat).where(Perangkat.gedung_id == an.gedung_id,
                                                                Perangkat.jenis == "meter"))]
        cakupan = "Seluruh gedung"
    sebelum, sesudah = _kwh(db, ids, a, t0), _kwh(db, ids, t0, b)
    banding = db.scalar(select(Gedung).where(Gedung.peran == "pembanding"))
    bs = bd = None
    if banding:
        bids = [p.id for p in db.scalars(select(Perangkat).where(Perangkat.gedung_id == banding.id,
                                                                 Perangkat.jenis == "meter"))]
        bs, bd = _kwh(db, bids, a, t0), _kwh(db, bids, t0, b)
    # konsumsi yang diharapkan tanpa tindakan = sebelum x perubahan relatif gedung pembanding
    harapan = sebelum * (bd / bs) if bs else sebelum
    return {"konsumsi_sebelum_kwh": round(sebelum, 1), "konsumsi_sesudah_kwh": round(sesudah, 1),
            "pembanding_sebelum_kwh": round(bs, 1) if bs is not None else None,
            "pembanding_sesudah_kwh": round(bd, 1) if bd is not None else None,
            "harapan_tanpa_tindakan_kwh": round(harapan, 1), "hemat_kwh": round(harapan - sesudah, 1),
            "cakupan": cakupan, "jendela_mulai": a.isoformat(), "jendela_selesai": b.isoformat(),
            "siap": datetime.now() >= b}


def catat_evaluasi(db: Session, rec: Rekomendasi, oleh: Pengguna, catatan: str = "",
                   waktu: datetime | None = None) -> Evaluasi:
    waktu = waktu or datetime.now()
    if rec.status != "Dilaksanakan":
        raise TransisiTidakSah("Evaluasi hanya untuk rekomendasi berstatus Dilaksanakan.")
    if waktu < rec.dilaksanakan_pada + timedelta(days=PEMANTAUAN_HARI):
        sisa = rec.dilaksanakan_pada + timedelta(days=PEMANTAUAN_HARI) - waktu
        raise ValueError(f"Pemantauan 14 hari belum selesai. Sisa {sisa.days + 1} hari.")
    h = hitung_evaluasi(db, rec)
    ev = Evaluasi(rekomendasi_id=rec.id, konsumsi_sebelum_kwh=h["konsumsi_sebelum_kwh"],
                  konsumsi_sesudah_kwh=h["konsumsi_sesudah_kwh"],
                  pembanding_sebelum_kwh=h["pembanding_sebelum_kwh"],
                  pembanding_sesudah_kwh=h["pembanding_sesudah_kwh"], hemat_kwh=h["hemat_kwh"],
                  catatan=(catatan or "").strip(), dicatat_oleh=oleh.id, waktu=waktu)
    db.add(ev)
    ubah_status(db, rec, "Dievaluasi", oleh, catatan, waktu)
    rec.dievaluasi_pada = waktu
    audit(db, oleh.id, "evaluasi.catat", f"R-{rec.nomor:03d}; hemat {h['hemat_kwh']} kWh")
    return ev


# ------------------------------------------------------------------ pekerjaan terjadwal
def proses_tenggat(db: Session, sekarang: datetime | None = None) -> dict:
    """Kedaluwarsa 7 hari, pengingat batas waktu, eskalasi ke pengelola."""
    sekarang = sekarang or datetime.now()
    hari = settings_store.get(db, "batas_respons_hari")
    hasil = {"kedaluwarsa": 0, "pengingat": 0, "eskalasi": 0, "pemantauan_selesai": 0}
    for rec in db.scalars(select(Rekomendasi).where(Rekomendasi.status == "Diusulkan",
                                                    Rekomendasi.dibuat_pada < sekarang - timedelta(days=hari))):
        ubah_status(db, rec, "Kedaluwarsa", None, f"Tanpa respons {hari} hari.", sekarang)
        hasil["kedaluwarsa"] += 1
    for t in db.scalars(select(Tugas).where(Tugas.selesai_pada.is_(None))):
        rec = t.rekomendasi
        if rec.status != "Diverifikasi":
            continue
        if t.pengingat_terkirim == 0 and sekarang >= t.batas_waktu - timedelta(hours=6):
            notify.kirim(db, [t.pelaksana], "pengingat", f"Batas waktu mendekat: {rec.judul}",
                         f"Tandai sudah dilaksanakan sebelum {t.batas_waktu:%d-%m %H.%M} WIB.", "#/rekomendasi",
                         waktu=sekarang)
            t.pengingat_terkirim = 1
            hasil["pengingat"] += 1
        if not t.dieskalasi and sekarang >= t.batas_waktu:
            notify.kirim(db, [t.pelaksana], "pengingat", f"Lewat batas waktu: {rec.judul}",
                         "Segera laksanakan dan tandai selesai.", "#/rekomendasi", waktu=sekarang)
            notify.ke_peran(db, ["pengelola"], "eskalasi", f"Tugas lewat batas waktu: {rec.judul}",
                            f"Pelaksana: {t.pelaksana.nama}. Tetapkan ulang atau hubungi pelaksana.",
                            f"#/rekomendasi/{rec.id}", waktu=sekarang)
            t.dieskalasi = True
            hasil["eskalasi"] += 1
        if sekarang >= t.batas_waktu + timedelta(days=hari):
            ubah_status(db, rec, "Kedaluwarsa", None, f"Tugas tidak dilaksanakan {hari} hari setelah batas waktu.",
                        sekarang)
            hasil["kedaluwarsa"] += 1
    for rec in db.scalars(select(Rekomendasi).where(Rekomendasi.status == "Dilaksanakan")):
        selesai = rec.dilaksanakan_pada + timedelta(days=PEMANTAUAN_HARI)
        if sekarang >= selesai and not any(r.catatan == "pemantauan_selesai" for r in rec.riwayat):
            db.add(RiwayatStatus(rekomendasi_id=rec.id, dari="Dilaksanakan", ke="Dilaksanakan", waktu=selesai,
                                 catatan="pemantauan_selesai"))
            notify.ke_peran(db, ["pengelola"], "evaluasi", f"Siap dievaluasi: {rec.judul}",
                            "Pemantauan 14 hari selesai. Konsumsi sebelum dan sesudah sudah terisi.",
                            f"#/rekomendasi/{rec.id}", waktu=selesai)
            hasil["pemantauan_selesai"] += 1
    return hasil
