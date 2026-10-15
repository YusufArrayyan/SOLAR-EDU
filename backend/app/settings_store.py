"""Parameter sistem yang dapat diubah tim pengelola (F22), dengan validasi per kolom."""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from .models import Pengaturan


@dataclass(frozen=True)
class Spec:
    label: str
    tipe: str  # float | int | bool | json
    bawaan: Any
    satuan: str = ""
    min: float | None = None
    max: float | None = None
    bantuan: str = ""
    grup: str = "umum"


SPECS: dict[str, Spec] = {
    "faktor_emisi": Spec("Faktor emisi", "float", 0.80, "kg CO2e/kWh", 0.1, 1.5,
                         "Faktor emisi jaringan listrik. Perbarui sesuai data resmi terbaru.", "dampak"),
    "tarif_rp_kwh": Spec("Tarif listrik", "float", 1444.70, "Rp/kWh", 100, 10000,
                         "Dipakai untuk menghitung biaya terhindarkan, bukan penagihan resmi.", "dampak"),
    "ambang_kw": Spec("Ambang minimum residu", "float", 4.0, "kW", 0.5, 50,
                      "Residu harus melewati nilai terbesar antara ambang ini dan kelipatan MAD.", "anomali"),
    "ambang_mad_kali": Spec("Kelipatan MAD", "float", 3.0, "x MAD", 1, 10,
                            "Kelipatan median simpangan absolut residu.", "anomali"),
    "ambang_jam": Spec("Durasi minimum", "int", 2, "jam", 1, 12,
                       "Residu harus bertahan sekurang-kurangnya selama ini.", "anomali"),
    "aturan_jadwal_aktif": Spec("Aturan beban tinggi tanpa kelas", "bool", True, "", None, None,
                                "Tandai beban tinggi pada jam tanpa kelas terjadwal (F10).", "anomali"),
    "aturan_jadwal_kw": Spec("Batas beban tanpa kelas", "float", 14.0, "kW", 1, 200,
                             "Beban di atas nilai ini saat tidak ada kelas dianggap mencurigakan.", "anomali"),
    "faktor_kinerja_pv": Spec("Faktor kinerja PV", "float", 0.78, "", 0.3, 1.0,
                              "Rasio kinerja sistem panel surya untuk prediksi produksi.", "prediksi"),
    "batas_tugas_jam": Spec("Batas waktu tugas", "int", 48, "jam", 4, 336,
                            "Waktu yang diberikan kepada mahasiswa piket sejak verifikasi.", "notifikasi"),
    "batas_respons_hari": Spec("Batas respons rekomendasi", "int", 7, "hari", 1, 30,
                               "Rekomendasi tanpa respons selama ini menjadi Kedaluwarsa.", "notifikasi"),
    "ringkasan_mingguan_aktif": Spec("Email ringkasan mingguan", "bool", True, "", None, None,
                                     "Dikirim setiap Senin pukul 07.00 WIB.", "notifikasi"),
    "pembanding_fungsi": Spec("Intensitas pembanding per fungsi", "json",
                              {"kuliah": 12.0, "laboratorium": 16.0, "kantor": 12.5, "perpustakaan": 10.5},
                              "Wh/m²/jam", None, None,
                              "Nilai acuan intensitas tiap fungsi gedung untuk indeks efisiensi.", "dampak"),
}


def _parse(spec: Spec, raw: Any) -> Any:
    if spec.tipe == "bool":
        if isinstance(raw, bool):
            return raw
        if str(raw).lower() in ("1", "true", "ya"):
            return True
        if str(raw).lower() in ("0", "false", "tidak"):
            return False
        raise ValueError("harus ya atau tidak")
    if spec.tipe == "json":
        val = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(val, dict) or not val:
            raise ValueError("harus berisi pasangan fungsi dan angka")
        out = {}
        for k, v in val.items():
            v = float(v)
            if not 1 <= v <= 100:
                raise ValueError(f"nilai {k} harus antara 1 dan 100")
            out[str(k)] = v
        return out
    try:
        val = int(raw) if spec.tipe == "int" else float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("harus berupa angka")
    if spec.tipe == "int" and float(raw) != int(float(raw)):
        raise ValueError("harus bilangan bulat")
    if spec.min is not None and val < spec.min:
        raise ValueError(f"minimal {spec.min:g}")
    if spec.max is not None and val > spec.max:
        raise ValueError(f"maksimal {spec.max:g}")
    return val


def get(db: Session, kunci: str) -> Any:
    spec = SPECS[kunci]
    row = db.get(Pengaturan, kunci)
    if row is None:
        return spec.bawaan
    try:
        return _parse(spec, json.loads(row.nilai))
    except Exception:
        return spec.bawaan


def all_values(db: Session) -> dict[str, Any]:
    return {k: get(db, k) for k in SPECS}


def validate(changes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    ok, errors = {}, {}
    for k, raw in changes.items():
        if k not in SPECS:
            errors[k] = "Pengaturan tidak dikenal."
            continue
        try:
            ok[k] = _parse(SPECS[k], raw)
        except ValueError as e:
            errors[k] = f"{SPECS[k].label} {e}."
    return ok, errors


def save(db: Session, values: dict[str, Any]) -> None:
    now = datetime.now()
    for k, v in values.items():
        row = db.get(Pengaturan, k)
        if row is None:
            db.add(Pengaturan(kunci=k, nilai=json.dumps(v), diubah_pada=now))
        else:
            row.nilai = json.dumps(v)
            row.diubah_pada = now


def describe() -> list[dict]:
    return [
        {"kunci": k, "label": s.label, "tipe": s.tipe, "satuan": s.satuan, "min": s.min, "max": s.max,
         "bantuan": s.bantuan, "grup": s.grup}
        for k, s in SPECS.items()
    ]
