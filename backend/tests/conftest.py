import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="solar-test-")
os.environ["SOLAR_DATA_DIR"] = _tmp
os.environ["SOLAR_SIMULATION"] = "1"  # tes memakai data simulasi; bawaan aplikasi adalah produksi
os.environ["SOLAR_SEED_DAYS"] = "110"
os.environ["ADMIN_EMAIL"] = "admin.asli@unib.ac.id"
os.environ["ADMIN_PASSWORD"] = ADMIN_SANDI = "Asli-Uji-12345"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SANDI = "SolarEdu#2026"  # sama dengan DEMO_PASSWORD di app/seed.py
H = {"X-Solar-Edu": "1"}


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def masuk(client):
    def _masuk(email):
        client.post("/api/auth/keluar", headers=H)
        r = client.post("/api/auth/masuk", json={"email": email, "sandi": SANDI}, headers=H)
        assert r.status_code == 200, r.text
        return client
    return _masuk
