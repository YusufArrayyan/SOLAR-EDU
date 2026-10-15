"""Uji unit aturan inti (PRD: Rencana pengujian, baris Unit)."""
from datetime import datetime

import numpy as np
import pytest

from app import settings_store
from app.services import anomaly, impact, simulate
from app.services.recommend import TRANSISI


def test_runs_minimal_dua_jam():
    m = np.array([0, 1, 1, 0, 1, 0, 1, 1, 1], bool)
    assert anomaly.runs(m, 2) == [(1, 3), (6, 9)]


def test_runs_tepat_di_ambang_durasi_dan_ujung():
    assert anomaly.runs(np.array([1, 1], bool), 2) == [(0, 2)]
    assert anomaly.runs(np.array([1], bool), 2) == []
    assert anomaly.runs(np.array([], bool), 2) == []


def test_ambang_maksimum_kw_dan_mad():
    assert anomaly.Ambang(kw=4, mad_kali=3, jam=2, mad=1.0).nilai == 4
    assert anomaly.Ambang(kw=4, mad_kali=3, jam=2, mad=2.0).nilai == 6


def test_indeks_efisiensi():
    assert impact.indeks_efisiensi(12, 12) == 100
    assert impact.indeks_efisiensi(12, 15) == 80
    assert impact.indeks_efisiensi(12, 0) == 0


def test_intensitas_emisi_rupiah():
    assert impact.intensitas_wh_m2_jam(1000, 100, 10) == pytest.approx(1000)
    assert impact.emisi_kg(100, 0.8) == pytest.approx(80)
    assert impact.rupiah(10, 1444.7) == pytest.approx(14447)


def test_status_tidak_bisa_melompat():
    assert "Dilaksanakan" not in TRANSISI["Diusulkan"]
    assert "Dievaluasi" not in TRANSISI["Diverifikasi"]
    assert TRANSISI["Dievaluasi"] == TRANSISI["Ditolak"] == TRANSISI["Kedaluwarsa"] == set()


def test_validasi_pengaturan():
    ok, err = settings_store.validate({"ambang_kw": "4,5", "ambang_jam": "3", "faktor_emisi": "9"})
    assert ok == {"ambang_kw": 4.5, "ambang_jam": 3}
    assert "faktor_emisi" in err
    _, err = settings_store.validate({"ambang_jam": "2.5", "tidak_ada": 1})
    assert set(err) == {"ambang_jam", "tidak_ada"}


def test_bucket_waktu():
    assert simulate.bucket(datetime(2026, 10, 17, 10)) == "akhir_pekan"  # Sabtu
    assert simulate.bucket(datetime(2026, 10, 15, 12)) == "siang"
    assert simulate.bucket(datetime(2026, 10, 15, 17)) == "sore"
    assert simulate.bucket(datetime(2026, 10, 15, 2)) == "malam"


def test_validasi_pembacaan():
    from app.services.data_pipeline import validasi
    assert validasi({"beban_kw": 10}, 60) == 0
    assert validasi({"beban_kw": -1}, 60) == 2
    assert validasi({"beban_kw": 61}, 60) == 2
    assert validasi({"produksi_pv_kw": None, "beban_kw": None}, 60) == 0


def test_csv_aman_dari_injeksi_rumus():
    from app.services.impact import aman_csv
    assert aman_csv("=HYPERLINK(\"x\")").startswith("'=")
    assert aman_csv("+1") == "'+1" and aman_csv("@SUM(A1)") == "'@SUM(A1)"
    assert aman_csv("Catatan biasa") == "Catatan biasa"
    assert aman_csv(12.345) == "12,3" and aman_csv(-3.0) == "-3,0" and aman_csv(None) == ""


def test_mode_produksi_tolak_token_bawaan(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SIMULATION", False)
    monkeypatch.setattr(config, "INGEST_TOKEN", config.INGEST_TOKEN_BAWAAN)
    with pytest.raises(RuntimeError):
        config.periksa_produksi()
    monkeypatch.setattr(config, "INGEST_TOKEN", "x" * 32)
    config.periksa_produksi()


def test_agregasi_per_jam_dalam_toleransi_05_persen():
    """F05: agregat per jam konsisten dengan data mentah dalam toleransi 0,5 %."""
    from datetime import timedelta
    from sqlalchemy import func, select
    from app.db import SessionLocal
    from app.models import AgregatJam, Gedung, Pengukuran, Perangkat
    with SessionLocal() as db:
        g = db.scalar(select(Gedung).where(Gedung.peran == "percontohan"))
        if g is None:
            pytest.skip("Basis data uji belum diisi.")
        meter = [p.id for p in db.scalars(select(Perangkat).where(Perangkat.gedung_id == g.id, Perangkat.jenis == "meter"))]
        diperiksa = 0
        for a in db.scalars(select(AgregatJam).where(AgregatJam.gedung_id == g.id, AgregatJam.beban_kw.is_not(None),
                                                     AgregatJam.kelengkapan >= 0.99).limit(200)):
            mentah = sum(db.scalar(select(func.avg(Pengukuran.beban_kw)).where(
                Pengukuran.perangkat_id == m, Pengukuran.kualitas == 0, Pengukuran.waktu >= a.waktu,
                Pengukuran.waktu < a.waktu + timedelta(hours=1))) or 0 for m in meter)
            assert abs(mentah - a.beban_kw) <= 0.005 * max(mentah, 1e-6) + 1e-3
            diperiksa += 1
        assert diperiksa > 50
