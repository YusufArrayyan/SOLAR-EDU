"""Uji integrasi dan matriks hak akses (setiap sel diuji dengan akun tiap peran)."""
import pytest

from conftest import H

AKUN = {
    "pengelola": "pengelola@solar-edu.test",
    "piket": "bima.piket@solar-edu.test",
    "tim": "tim@solar-edu.test",
    "pimpinan": "pimpinan@solar-edu.test",
    "akademik": "mahasiswa@solar-edu.test",
}

# (metode, path, peran yang boleh)
MATRIKS = [
    ("GET", "/api/ringkasan", {"pengelola", "piket", "tim", "pimpinan"}),
    ("GET", "/api/rekomendasi", {"pengelola", "piket", "tim", "pimpinan"}),
    ("GET", "/api/pelaksana", {"pengelola", "tim"}),
    ("GET", "/api/peringkat", {"pengelola", "tim", "pimpinan"}),
    ("GET", "/api/dampak", {"pengelola", "tim", "pimpinan"}),
    ("GET", "/api/belajar", {"pengelola", "piket", "tim", "pimpinan", "akademik"}),
    ("GET", "/api/dataset.csv?hari=7", {"pengelola", "piket", "tim", "pimpinan", "akademik"}),
    ("GET", "/api/pengaturan", {"tim"}),
    ("GET", "/api/pengguna", {"tim"}),
    ("GET", "/api/audit", {"tim"}),
    ("GET", "/api/gedung", {"tim"}),
]


@pytest.mark.parametrize("peran", list(AKUN))
def test_matriks_hak_akses(masuk, peran):
    c = masuk(AKUN[peran])
    for metode, path, boleh in MATRIKS:
        r = c.request(metode, path)
        harap = 200 if peran in boleh else 403
        assert r.status_code == harap, f"{peran} {path}: {r.status_code}"


def test_tanpa_sesi_ditolak(client):
    client.post("/api/auth/keluar", headers=H)
    assert client.get("/api/ringkasan").status_code == 401


def test_csrf_header_wajib(masuk):
    c = masuk(AKUN["tim"])
    assert c.put("/api/pengaturan", json={"ambang_kw": 4}).status_code == 403
    assert c.put("/api/pengaturan", json={"ambang_kw": 4}, headers=H).status_code == 200


def test_sandi_salah(client):
    r = client.post("/api/auth/masuk", json={"email": AKUN["tim"], "sandi": "salah"}, headers=H)
    assert r.status_code == 401


def test_ringkasan_berisi_prediksi_dan_model(masuk):
    d = masuk(AKUN["pengelola"]).get("/api/ringkasan").json()
    assert len(d["seri"]) == 72
    assert d["model"] and d["model"]["mape"] < 15
    assert any(r["prediksi"] is not None for r in d["seri"])


def test_alur_rekomendasi_penuh(masuk):
    c = masuk(AKUN["pengelola"])
    baris = c.get("/api/rekomendasi?status=Diusulkan").json()["baris"]
    if not baris:
        pytest.skip("Tidak ada rekomendasi berstatus Diusulkan pada data simulasi ini.")
    rid = baris[0]["id"]
    # tidak bisa melompat ke evaluasi
    assert c.post(f"/api/rekomendasi/{rid}/evaluasi", json={}, headers=H).status_code == 409
    # tolak tanpa alasan ditolak
    assert c.post(f"/api/rekomendasi/{rid}/tolak", json={"alasan": ""}, headers=H).status_code == 422
    piket = c.get("/api/pelaksana").json()
    bima = next(p for p in piket if p["nama"] == "Bima Saputra")
    r = c.post(f"/api/rekomendasi/{rid}/verifikasi", json={"pelaksana_id": bima["id"], "batas_jam": 24}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "Diverifikasi"
    tid = r.json()["tugas"][0]["id"]

    p = masuk(AKUN["piket"])
    assert any(x["id"] == rid for x in p.get("/api/rekomendasi").json()["baris"])
    assert p.post(f"/api/tugas/{tid}/selesai", json={"catatan": ""}, headers=H).status_code == 422
    r = p.post(f"/api/tugas/{tid}/selesai", json={"catatan": "AC sudah dimatikan."}, headers=H)
    assert r.status_code == 200

    c = masuk(AKUN["pengelola"])
    d = c.get(f"/api/rekomendasi/{rid}").json()
    assert d["status"] == "Dilaksanakan" and not d["siap_evaluasi"]
    assert [h["ke"] for h in d["riwayat"] if h["dari"] != h["ke"]][-2:] == ["Diverifikasi", "Dilaksanakan"]
    # pemantauan 14 hari belum selesai
    assert c.post(f"/api/rekomendasi/{rid}/evaluasi", json={}, headers=H).status_code == 422

    audit = masuk(AKUN["tim"]).get("/api/audit").json()["baris"]
    assert any(a["aksi"] == "rekomendasi.verifikasi" for a in audit)


def test_log_audit_tidak_bisa_diubah():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import LogAudit
    with SessionLocal() as db:
        row = db.scalar(select(LogAudit).limit(1))
        row.detail = "diubah"
        with pytest.raises(PermissionError):
            db.flush()
        db.rollback()


def test_impor_jadwal_tandai_baris_salah(masuk):
    c = masuk(AKUN["tim"])
    csv = "ruang,hari,mulai,selesai\nA2.01,Senin,07:30,09:10\nZZ,Senin,07:30,09:10\nA2.02,Senin,10:00,09:00\n"
    d = c.post("/api/jadwal/impor", json={"csv": csv, "simpan": False}, headers=H).json()
    assert d["valid"] == 1 and [s["baris"] for s in d["salah"]] == [3, 4]


def test_dataset_tanpa_identitas(masuk):
    teks = masuk(AKUN["akademik"]).get("/api/dataset.csv?hari=3").text
    kepala = teks.splitlines()[0]
    assert "email" not in kepala and "nama" not in kepala and "beban_kw" in kepala


def test_ganti_sandi_dan_reset(client, masuk):
    from conftest import ADMIN_SANDI, SANDI
    # akun demo tidak boleh mengganti kata sandinya sendiri
    d = masuk("dimas.ta@solar-edu.test")
    assert d.put("/api/saya/sandi", json={"lama": SANDI, "baru": "SandiBaru#2026"}, headers=H).status_code == 403
    # akun asli boleh
    client.post("/api/auth/keluar", headers=H)
    assert client.post("/api/auth/masuk", json={"email": "admin.asli@unib.ac.id", "sandi": ADMIN_SANDI},
                       headers=H).status_code == 200
    assert client.put("/api/saya/sandi", json={"lama": "salah", "baru": "SandiBaru#2026"}, headers=H).status_code == 422
    assert client.put("/api/saya/sandi", json={"lama": ADMIN_SANDI, "baru": "pendek"}, headers=H).status_code == 422
    assert client.put("/api/saya/sandi", json={"lama": ADMIN_SANDI, "baru": "SandiBaru#2026"}, headers=H).status_code == 200
    assert client.get("/api/auth/saya").json()["demo"] is False
    # admin asli mereset kata sandi akun demo
    pid = next(u["id"] for u in client.get("/api/pengguna").json()["baris"] if u["email"] == "dimas.ta@solar-edu.test")
    assert client.patch(f"/api/pengguna/{pid}", json={"sandi_baru": "pendek"}, headers=H).status_code == 422
    assert client.patch(f"/api/pengguna/{pid}", json={"sandi_baru": SANDI}, headers=H).status_code == 200
    audit = client.get("/api/audit").json()["baris"]
    assert any(a["aksi"] == "sandi.ganti" for a in audit)
    assert not any(SANDI in a["detail"] or "SandiBaru" in a["detail"] for a in audit)
    client.put("/api/saya/sandi", json={"lama": "SandiBaru#2026", "baru": ADMIN_SANDI}, headers=H)


def test_akun_demo_tidak_bisa_menyentuh_akun_asli(client, masuk):
    from conftest import ADMIN_SANDI
    t = masuk(AKUN["tim"])  # akun demo tim pengelola
    assert t.get("/api/auth/saya").json()["demo"] is True
    daftar = t.get("/api/pengguna").json()["baris"]
    assert all(u["demo"] for u in daftar) and not any(u["email"] == "admin.asli@unib.ac.id" for u in daftar)
    client.post("/api/auth/keluar", headers=H)
    client.post("/api/auth/masuk", json={"email": "admin.asli@unib.ac.id", "sandi": ADMIN_SANDI}, headers=H)
    semua = client.get("/api/pengguna").json()["baris"]
    admin_id = next(u["id"] for u in semua if u["email"] == "admin.asli@unib.ac.id")
    assert any(u["demo"] for u in semua)  # akun asli melihat semua
    t = masuk(AKUN["tim"])
    assert t.patch(f"/api/pengguna/{admin_id}", json={"aktif": False}, headers=H).status_code == 404
    assert t.patch(f"/api/pengguna/{admin_id}", json={"sandi_baru": "x" * 12}, headers=H).status_code == 404
    assert t.post("/api/pengguna", json={"nama": "Penyusup", "email": "a@b.id", "peran": "tim", "sandi": "x" * 12},
                  headers=H).status_code == 403
    demo_lain = next(u["id"] for u in daftar if u["email"] == "dimas.ta@solar-edu.test")
    assert t.patch(f"/api/pengguna/{demo_lain}", json={"sandi_baru": "x" * 12}, headers=H).status_code == 403
    assert all(a["pengguna"] != "Admin tim pengelola" for a in t.get("/api/audit").json()["baris"])
    # akun admin asli tetap bisa masuk
    client.post("/api/auth/keluar", headers=H)
    assert client.post("/api/auth/masuk", json={"email": "admin.asli@unib.ac.id", "sandi": ADMIN_SANDI},
                       headers=H).status_code == 200


def test_ubah_gedung(masuk):
    t = masuk(AKUN["tim"])
    g = t.get("/api/gedung").json()["baris"][0]
    assert g["peran"] == "percontohan"
    r = t.patch(f"/api/gedung/{g['id']}", json={"luas_m2": 10, "jam_operasional_pekan": 200}, headers=H)
    assert r.status_code == 422 and set(r.json()["detail"]["kolom"]) == {"luas_m2", "jam_operasional_pekan"}
    r = t.patch(f"/api/gedung/{g['id']}", json={"luas_m2": 3300}, headers=H)
    assert r.status_code == 200 and r.json()["luas_m2"] == 3300
    t.patch(f"/api/gedung/{g['id']}", json={"luas_m2": g["luas_m2"]}, headers=H)


def test_kunci_login_per_email_dan_ip(client):
    from app.routers import auth
    auth._gagal.clear()
    for _ in range(5):
        client.post("/api/auth/masuk", json={"email": "sari.piket@solar-edu.test", "sandi": "salah"}, headers=H)
    r = client.post("/api/auth/masuk", json={"email": "sari.piket@solar-edu.test", "sandi": "salah"}, headers=H)
    assert r.status_code == 429
    # akun lain dari IP yang sama tetap bisa masuk (batas per-IP lebih longgar)
    from conftest import SANDI
    assert client.post("/api/auth/masuk", json={"email": "nadia.piket@solar-edu.test", "sandi": SANDI},
                       headers=H).status_code == 200
    auth._gagal.clear()


def test_laporan_csv_aman(masuk):
    c = masuk(AKUN["pengelola"])
    r = c.get("/api/laporan.csv?mulai=2026-01-01&selesai=2026-12-31")
    assert r.status_code == 200 and r.text.startswith("﻿")
    assert ";" in r.text.splitlines()[4]
