"""Mode produksi diuji di proses terpisah karena mode dibaca saat aplikasi dimuat."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

SKRIP = textwrap.dedent('''
    import json, logging, sys
    logging.disable(logging.WARNING)
    sys.path.insert(0, ".")
    from fastapi.testclient import TestClient
    from app.main import app
    H = {"X-Solar-Edu": "1"}
    out = {}
    with TestClient(app) as c:
        out["sehat"] = c.get("/api/sehat").json()
        out["docs"] = c.get("/api/docs").status_code
        out["demo_masuk"] = c.post("/api/auth/masuk", json={"email": "tim@solar-edu.test", "sandi": "SolarEdu#2026"},
                                   headers=H).status_code
        out["admin_masuk"] = c.post("/api/auth/masuk", json={"email": "admin@kampus.ac.id", "sandi": "Produksi-Uji-123"},
                                    headers=H).status_code
        out["pengguna"] = [u["email"] for u in c.get("/api/pengguna").json()["baris"]]
        out["gedung"] = [g["peran"] for g in c.get("/api/gedung").json()["baris"]]
        out["jadwal"] = len(c.get("/api/jadwal").json()["baris"])
        out["ringkasan"] = c.get("/api/ringkasan").status_code
        out["dampak"] = c.get("/api/dampak").status_code
        out["peringkat"] = c.get("/api/peringkat").json()["baris"]
        p = c.get("/api/persiapan").json()
        out["persiapan"] = {"siap": p["siap"], "selesai": p["selesai"], "total": p["total"]}
        g = c.get("/api/gedung").json()["baris"]
        pilot = next(x for x in g if x["peran"] == "percontohan")
        out["perangkat_salah"] = c.post("/api/perangkat", json={"gedung_id": pilot["id"], "kode": "SALAH KODE",
                                       "nama": "x", "jenis": "meter"}, headers=H).status_code
        r = c.post("/api/perangkat", json={"gedung_id": pilot["id"], "kode": "fk-a/panel-l4", "nama": "Panel lantai 4",
                                         "jenis": "meter", "batas_fisik_kw": 80}, headers=H)
        out["perangkat_baru"] = r.status_code
        pid = r.json()["id"]
        out["perangkat_ganda"] = c.post("/api/perangkat", json={"gedung_id": pilot["id"], "kode": "fk-a/panel-l4",
                                       "nama": "Ganda", "jenis": "meter"}, headers=H).status_code
        tok = __import__("os").environ["INGEST_TOKEN"]
        out["ingest"] = c.post("/api/ingest", json=[{"perangkat": "fk-a/panel-l4", "waktu": "2026-10-16T08:00:00+07:00",
                                                     "beban_kw": 5.0}], headers={"X-Ingest-Token": tok}).json()
        out["hapus_berdata"] = c.delete(f"/api/perangkat/{pid}", headers=H).status_code
        r = c.post("/api/ruang", json={"gedung_id": pilot["id"], "nama": "A4.01", "kapasitas": 50, "perangkat_id": pid},
                   headers=H)
        out["ruang_baru"] = r.status_code
        out["ruang_ganda"] = c.post("/api/ruang", json={"gedung_id": pilot["id"], "nama": "a4.01"}, headers=H).status_code
        csv = "ruang,hari,mulai,selesai\\nA4.01,Senin,07:30,09:10\\n"
        out["impor"] = c.post("/api/jadwal/impor", json={"csv": csv, "simpan": True}, headers=H).json()["valid"]
        out["hapus_ruang_terjadwal"] = c.delete(f"/api/ruang/{r.json()['id']}", headers=H).status_code
        r = c.post("/api/gedung", json={"nama": "Gedung Uji Produksi", "fungsi": "perpustakaan", "luas_m2": 4200,
                                      "jam_operasional_pekan": 66}, headers=H)
        out["gedung_baru"] = r.status_code
        gid = r.json()["id"]
        out["konsumsi_bulan_ini"] = c.put(f"/api/gedung/{gid}/konsumsi", json={"periode": "2099-01", "kwh": 1000},
                                          headers=H).status_code
        k = c.put(f"/api/gedung/{gid}/konsumsi", json={"periode": "2026-09", "kwh": 30000}, headers=H)
        out["konsumsi"] = k.status_code
        out["indeks"] = k.json().get("indeks")
        out["peringkat_setelah"] = [b["nama"] for b in c.get("/api/peringkat").json()["baris"]]
        out["hapus_pilot"] = c.delete(f"/api/gedung/{pilot['id']}", headers=H).status_code
    print("HASIL" + json.dumps(out))
''')


def _jalankan(data_dir: str, simulasi: str) -> dict:
    env = {**os.environ, "SOLAR_DATA_DIR": data_dir, "SOLAR_SIMULATION": simulasi, "SOLAR_SEED_DAYS": "100",
           "ADMIN_EMAIL": "admin@kampus.ac.id", "ADMIN_PASSWORD": "Produksi-Uji-123",
           "INGEST_TOKEN": "t" * 32, "WEATHER_LIVE": "0"}
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", SKRIP], cwd=BACKEND, env=env, capture_output=True,
                       text=True, timeout=600)
    baris = [b for b in r.stdout.splitlines() if b.startswith("HASIL")]
    assert baris, r.stderr[-3000:]
    return json.loads(baris[-1][5:])


def test_produksi_bersih_dan_reset_data_simulasi():
    d = tempfile.mkdtemp(prefix="solar-prod-")
    # 1) basis data simulasi lama (seperti deploy demo sebelumnya)
    sim = _jalankan(d, "1")
    assert sim["sehat"]["simulasi"] is True and sim["jadwal"] > 0
    # 2) server yang sama dinyalakan ulang dalam mode produksi
    o = _jalankan(d, "0")
    assert o["sehat"]["simulasi"] is False and "demo_sandi" not in o["sehat"]
    assert o["docs"] == 404
    assert o["demo_masuk"] == 401 and o["admin_masuk"] == 200
    assert o["pengguna"] == ["admin@kampus.ac.id"]
    assert sorted(o["gedung"]) == ["pembanding", "percontohan"]
    assert o["jadwal"] == 0 and o["peringkat"] == []
    assert o["ringkasan"] == 200 and o["dampak"] == 200
    assert o["persiapan"]["siap"] is False and o["persiapan"]["selesai"] == 0
    assert o["perangkat_salah"] == 422 and o["perangkat_baru"] == 201 and o["perangkat_ganda"] == 422
    assert o["ingest"] == {"diterima": 1, "ditolak": 0}
    assert o["hapus_berdata"] == 409
    assert o["ruang_baru"] == 201 and o["ruang_ganda"] == 422
    assert o["impor"] == 1 and o["hapus_ruang_terjadwal"] == 409
    assert o["gedung_baru"] == 201 and o["konsumsi_bulan_ini"] == 422 and o["konsumsi"] == 200
    assert o["indeks"] and o["peringkat_setelah"] == ["Gedung Uji Produksi"]
    assert o["hapus_pilot"] == 409
