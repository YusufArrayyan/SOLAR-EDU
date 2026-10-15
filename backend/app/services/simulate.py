"""Generator data simulasi untuk prototipe.

Pola beban mengikuti gedung pendidikan: beban dasar, AC dan lampu per ruang terjadwal, kepekaan suhu,
dan beberapa "kebiasaan boros" yang disisipkan supaya mesin anomali punya sesuatu untuk ditemukan.
Semua angka yang dihasilkan modul ini adalah DATA SIMULASI, bukan hasil pengukuran.
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

STEP_MIN = 15  # resolusi pembacaan simulasi (meter nyata mengirim tiap 1 menit)


def hour_floor(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


@dataclass
class Kebiasaan:
    """Pola pemborosan. Hari relatif terhadap epoch simulasi (0 = hari seeding).

    Pola berhenti ketika tugas piket untuk panel dan rentang waktu yang sama ditandai selesai
    (lihat tandai_diperbaiki), sehingga evaluasi 14 hari mengukur efek tindakan yang sungguh terjadi.
    """
    kode: str
    panel: str
    mulai_hari: int
    selesai_hari: int   # batas alami pola (999 = berlangsung sampai diperbaiki)
    jam_mulai: float
    durasi: tuple[float, float]
    tambahan_kw: tuple[float, float]
    hari_pekan: tuple[int, ...]
    peluang: float
    deskripsi: str
    bisa_diperbaiki: bool = True


KEBIASAAN: list[Kebiasaan] = [
    Kebiasaan("AC_L2_SORE", "fk-a/panel-l2", -150, 999, 17.5, (3, 5), (6.5, 8.5), (0, 1, 2, 3, 4), 0.45,
              "AC ruang kuliah lantai 2 tetap menyala setelah kelas terakhir"),
    Kebiasaan("LAB_AKHIR_PEKAN", "fk-a/panel-lab", -150, 999, 8.0, (9, 12), (5.0, 6.5), (5, 6), 0.6,
              "Komputer laboratorium menyala sepanjang akhir pekan"),
    Kebiasaan("L1_MALAM", "fk-a/panel-l1", -42, 999, 19.0, (6, 9), (5.0, 6.0), (0, 1, 2, 3, 4, 5, 6), 0.35,
              "Lampu lobi dan pompa air menyala sepanjang malam"),
    Kebiasaan("AC_L3_SIANG", "fk-a/panel-l3", -27, 999, 12.0, (2, 3), (6.0, 7.5), (0, 1, 2, 3, 4), 0.45,
              "AC ruang kuliah lantai 3 menyala saat jeda siang tanpa kelas"),
    Kebiasaan("SEMINAR_SABTU", "fk-a/panel-l1", -13, -6, 8.0, (8, 8), (8.0, 8.0), (5,), 1.0,
              "Seminar fakultas di aula (kegiatan sah di luar jadwal akademik)", bisa_diperbaiki=False),
    Kebiasaan("AC_L2_KAMBUH", "fk-a/panel-l2", -6, 999, 17.5, (3, 4), (6.5, 8.0), (0, 1, 2, 3, 4), 0.6,
              "AC lantai 2 kembali menyala setelah kelas (efek tindakan mulai memudar)"),
    Kebiasaan("LAB_MALAM", "fk-a/panel-lab", -3, 999, 19.0, (4, 6), (5.0, 6.0), (0, 1, 2, 3, 4), 0.9,
              "Komputer laboratorium menyala setelah praktikum terakhir"),
    Kebiasaan("AC_L3_MALAM", "fk-a/panel-l3", -1, 999, 19.0, (4, 5), (6.0, 7.0), (0, 1, 2, 3, 4), 1.0,
              "AC lantai 3 menyala sampai malam setelah kuliah sore"),
    Kebiasaan("POMPA_L1_DINIHARI", "fk-a/panel-l1", 0, 999, 2.0, (4, 4), (5.5, 6.0), (0, 1, 2, 3, 4, 5, 6), 1.0,
              "Pompa air lantai 1 menyala terus pada dini hari"),
    # Gedung pembanding tidak menerima rekomendasi, jadi polanya tidak pernah diperbaiki.
    Kebiasaan("BANDING_SORE", "fkip-v/utama", -150, 999, 17.5, (3, 5), (5.5, 7.5), (0, 1, 2, 3, 4), 0.42,
              "AC tetap menyala setelah kelas", bisa_diperbaiki=False),
    Kebiasaan("BANDING_MALAM", "fkip-v/utama", -150, 999, 19.0, (6, 9), (4.0, 5.0), (0, 1, 2, 3, 4, 5, 6), 0.3,
              "Lampu menyala malam", bisa_diperbaiki=False),
]


def bucket(t: datetime) -> str:
    """Rentang waktu yang dipakai untuk mencocokkan anomali serupa."""
    if t.weekday() >= 5:
        return "akhir_pekan"
    h = t.hour
    if 11 <= h < 14:
        return "siang"
    if 16 <= h < 19:
        return "sore"
    if h >= 19 or h < 6:
        return "malam"
    return "pagi"


def kebiasaan_cocok(panel_kode: str, mulai: datetime) -> list[Kebiasaan]:
    """Kebiasaan pada panel yang sama yang rentang waktunya memuat awal anomali."""
    out = []
    for k in KEBIASAAN:
        if k.panel != panel_kode:
            continue
        for geser in (0, 1):
            d0 = (mulai - timedelta(days=geser)).replace(hour=0, minute=0, second=0, microsecond=0)
            if d0.weekday() not in k.hari_pekan:
                continue
            a = d0 + timedelta(hours=k.jam_mulai - 1.5)
            b = d0 + timedelta(hours=k.jam_mulai + k.durasi[1])
            if a <= mulai < b:
                out.append(k)
                break
    return out


def tandai_diperbaiki(state: dict, panel_kode: str, anomali_mulai: datetime, waktu: datetime) -> list[str]:
    """Hentikan kebiasaan yang cocok dengan anomali yang ditindaklanjuti."""
    epoch = datetime.fromisoformat(state["epoch"])
    hari_ke = (waktu.date() - epoch.date()).days
    kena = []
    for k in kebiasaan_cocok(panel_kode, anomali_mulai):
        if k.bisa_diperbaiki and k.kode not in state["fixed"] and k.mulai_hari <= hari_ke:
            state["fixed"][k.kode] = waktu.isoformat()
            kena.append(k.kode)
    return kena


# ---------------------------------------------------------------- cuaca
def _day_rng(day: datetime, salt: int) -> np.random.Generator:
    return np.random.default_rng(int(day.strftime("%Y%m%d")) * 97 + salt)


def cuaca_jam(t: datetime) -> tuple[float, float]:
    """Suhu (°C) dan radiasi global horizontal (W/m²) simulasi untuk Bengkulu."""
    d = t.replace(hour=0, minute=0, second=0, microsecond=0)
    r = _day_rng(d, 1)
    awan = float(r.uniform(0.35, 1.0))          # kecerahan hari itu
    hujan_sore = r.random() < 0.45              # hujan sore khas tropis
    h = t.hour + t.minute / 60
    if 6.0 <= h <= 18.2:
        x = (h - 6.0) / 12.2
        cerah = 940 * math.sin(math.pi * x) ** 1.3
        f = awan
        if hujan_sore and h > 14:
            f *= 0.35
        rr = np.random.default_rng(int(t.timestamp()) // 900)
        rad = max(0.0, cerah * f * float(rr.uniform(0.85, 1.12)))
    else:
        rad = 0.0
    suhu = 25.0 + 6.5 * max(0.0, math.sin(math.pi * (h - 7) / 14)) * (0.6 + 0.4 * awan)
    if hujan_sore and h > 14:
        suhu -= 2.0
    return round(suhu, 1), round(rad, 1)


# ---------------------------------------------------------------- jadwal
RUANG_PILOT = {
    "fk-a/panel-l1": ["A1.01 Aula", "A1.02 Ruang dosen"],
    "fk-a/panel-l2": ["A2.01", "A2.02", "A2.03", "A2.04"],
    "fk-a/panel-l3": ["A3.01", "A3.02", "A3.03", "A3.04"],
    "fk-a/panel-lab": ["Lab Komputer 1", "Lab Komputer 2"],
}

_SLOT = [("07:30", "09:10"), ("09:20", "11:00"), ("11:10", "12:50"), ("13:30", "15:10"), ("15:20", "17:00")]
_MK = ["Algoritma dan Pemrograman", "Basis Data", "Sistem Tenaga Listrik", "Mekanika Teknik", "Kalkulus II",
       "Struktur Data", "Elektronika Dasar", "Statika", "Rekayasa Perangkat Lunak", "Kecerdasan Buatan",
       "Konversi Energi", "Analisis Struktur", "Jaringan Komputer", "Fisika Dasar", "Etika Profesi"]


def jadwal_bawaan() -> list[dict]:
    """Jadwal kuliah mingguan simulasi: list dict (ruang, hari, mulai, selesai, mata_kuliah)."""
    rng = np.random.default_rng(2026)
    out = []
    for panel, ruang_list in RUANG_PILOT.items():
        for ruang in ruang_list:
            if "Ruang dosen" in ruang:
                continue
            for hari in range(5):
                for i, (m, s) in enumerate(_SLOT):
                    p = 0.25 if "Aula" in ruang else (0.55 if i in (2,) else 0.72)
                    if "Lab" in ruang:
                        p = 0.5
                    # jeda siang lantai 3 sengaja kosong agar aturan "tanpa kelas" relevan
                    if panel.endswith("l3") and i == 2:
                        p = 0.08
                    if rng.random() < p:
                        out.append({"ruang": ruang, "hari": hari, "mulai": m, "selesai": s,
                                    "mata_kuliah": str(rng.choice(_MK))})
    return out


def _menit(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def ruang_aktif(jadwal: list[dict], t: datetime, ruang_filter: set[str] | None = None) -> int:
    """Jumlah ruang dengan kelas yang berlangsung pada waktu t."""
    hari = t.weekday()
    mnt = t.hour * 60 + t.minute
    n = 0
    for j in jadwal:
        if j["hari"] != hari or (ruang_filter is not None and j["ruang"] not in ruang_filter):
            continue
        if _menit(j["mulai"]) - 15 <= mnt < _menit(j["selesai"]):  # pra-pendinginan 15 menit
            n += 1
    return n


def ruang_terjadwal_jam(jadwal: list[dict], jam: datetime) -> int:
    """Ruang yang terjadwal sedikitnya 30 menit dalam jam tersebut (fitur model)."""
    hari = jam.weekday()
    a = jam.hour * 60
    b = a + 60
    n = 0
    for j in jadwal:
        if j["hari"] != hari:
            continue
        overlap = min(b, _menit(j["selesai"])) - max(a, _menit(j["mulai"]))
        if overlap >= 30:
            n += 1
    return n


# ---------------------------------------------------------------- beban
_BASE = {"fk-a/panel-l1": 2.2, "fk-a/panel-l2": 1.4, "fk-a/panel-l3": 1.4, "fk-a/panel-lab": 2.8,
         "fkip-v/utama": 6.5}


def _kebiasaan_aktif(panel: str, t: datetime, state: dict) -> float:
    epoch = datetime.fromisoformat(state["epoch"])
    extra = 0.0
    for k in KEBIASAAN:
        if k.panel != panel:
            continue
        if k.kode in state["fixed"] and t >= datetime.fromisoformat(state["fixed"][k.kode]):
            continue
        hari_ke = (t.date() - epoch.date()).days
        # pola yang berjalan melewati tengah malam ditinjau dari hari kemarin juga
        for geser in (0, 1):
            d0 = (t - timedelta(days=geser)).replace(hour=0, minute=0, second=0, microsecond=0)
            hk = hari_ke - geser
            if not (k.mulai_hari <= hk < k.selesai_hari):
                continue
            if d0.weekday() not in k.hari_pekan:
                continue
            r = _day_rng(d0, zlib.crc32(k.kode.encode()) % 10_000)
            if r.random() > k.peluang:
                continue
            dur = float(r.uniform(*k.durasi))
            kw = float(r.uniform(*k.tambahan_kw))
            mulai = d0 + timedelta(hours=k.jam_mulai)
            if mulai <= t < mulai + timedelta(hours=dur):
                extra += kw
    return extra


def beban_panel(panel: str, t: datetime, jadwal: list[dict], state: dict, rng: np.random.Generator) -> float:
    suhu, _ = cuaca_jam(t)
    hari = t.weekday()
    h = t.hour + t.minute / 60
    base = _BASE[panel]
    kw = base
    if panel == "fkip-v/utama":
        # gedung pembanding: profil serupa gedung A, satu meter utama
        n = ruang_aktif(jadwal, t)
        kw += n * 2.9 * (1 + 0.035 * (suhu - 27))
        if hari < 5 and 8 <= h < 16:
            kw += 3.6
    else:
        ruang = set(RUANG_PILOT[panel])
        n = ruang_aktif(jadwal, t, ruang)
        per_ruang = 6.2 if panel.endswith("lab") else 3.0
        kw += n * per_ruang * (1 + 0.035 * (suhu - 27))
        if panel.endswith("l1") and hari < 5 and 7.5 <= h < 16.5:
            kw += 4.2  # ruang dosen, administrasi
        if panel.endswith("l1") and (h >= 18 or h < 6):
            kw += 0.6  # lampu keamanan
    kw += _kebiasaan_aktif(panel, t, state)
    kw *= float(rng.normal(1.0, 0.045))
    return max(0.15, kw)


def produksi_pv(t: datetime, kwp: float, rng: np.random.Generator) -> float:
    suhu, rad = cuaca_jam(t)
    # derating suhu modul sederhana
    pr = 0.80 * (1 - 0.004 * max(0.0, suhu + rad / 40 - 25))
    return max(0.0, kwp * rad / 1000 * pr * float(rng.normal(1.0, 0.03)))


def bangkitkan_pembacaan(perangkat: list[dict], mulai: datetime, selesai: datetime, jadwal: list[dict],
                         state: dict, kwp: float) -> list[dict]:
    """Bangkitkan pembacaan tiap STEP_MIN menit pada [mulai, selesai).

    perangkat: list dict {id, kode, jenis}. Menyisipkan paket hilang (~1,2 %), lonjakan sensor, dan nilai negatif
    supaya validasi M2 punya sesuatu untuk ditandai.
    """
    rows = []
    t = mulai
    while t < selesai:
        for p in perangkat:
            r2 = np.random.default_rng((int(t.timestamp()) // 60) * 31 + zlib.crc32(p["kode"].encode()) % 997)
            if r2.random() < 0.012:
                continue  # paket hilang
            if p["jenis"] == "inverter":
                val = produksi_pv(t, kwp, r2)
                rows.append({"waktu": t, "perangkat_id": p["id"], "beban_kw": None,
                             "produksi_pv_kw": round(val, 3), "kualitas": 0})
            else:
                val = beban_panel(p["kode"], t, jadwal, state, r2)
                u = r2.random()
                if u < 0.0007:
                    val = val * 40  # lonjakan sensor
                elif u < 0.0011:
                    val = -val
                rows.append({"waktu": t, "perangkat_id": p["id"], "beban_kw": round(val, 3),
                             "produksi_pv_kw": None, "kualitas": 0})
        t += timedelta(minutes=STEP_MIN)
    return rows
