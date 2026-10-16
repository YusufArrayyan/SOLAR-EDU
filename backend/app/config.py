"""Konfigurasi aplikasi dari variabel lingkungan."""
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

VERSI = "1.1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = Path(os.getenv("SOLAR_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite untuk pengembangan; produksi memakai PostgreSQL + TimescaleDB lewat DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'solar_edu.db').as_posix()}")

TZ = ZoneInfo("Asia/Jakarta")  # WIB
# Semua stempel waktu disimpan naif dalam WIB, jadi jam proses harus WIB juga (kontainer Docker bawaannya UTC).
# Hanya di POSIX: runtime C Windows tidak mengenal nama zona IANA dan akan menganggapnya UTC.
if hasattr(time, "tzset"):
    os.environ.setdefault("TZ", "Asia/Jakarta")
    time.tzset()

SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"  # set 1 di belakang HTTPS (Nginx)

# Bawaan: PRODUKSI (data nyata dari gateway meter). Mode simulasi hanya untuk pengembangan dan pengujian:
# basis data diisi data rekaan dan worker membangkitkan pembacaan tiap jam. Nyalakan dengan SOLAR_SIMULATION=1.
SIMULATION = os.getenv("SOLAR_SIMULATION", "0") == "1"
SEED_DAYS = int(os.getenv("SOLAR_SEED_DAYS", "150"))

# Prakiraan cuaca nyata (Open-Meteo). Bawaan aktif di produksi, mati di mode simulasi.
WEATHER_LIVE = os.getenv("WEATHER_LIVE", "0" if SIMULATION else "1") == "1"
SITE_LAT = float(os.getenv("SITE_LAT", "-3.7590"))   # Universitas Bengkulu
SITE_LON = float(os.getenv("SITE_LON", "102.2722"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "solar-edu@unib.ac.id")

INGEST_TOKEN_BAWAAN = "dev-ingest-token"
INGEST_TOKEN = os.getenv("INGEST_TOKEN", INGEST_TOKEN_BAWAAN)  # dipakai jembatan MQTT


def periksa_produksi() -> None:
    """Tolak berjalan di mode produksi dengan rahasia bawaan."""
    if SIMULATION:
        return
    if INGEST_TOKEN == INGEST_TOKEN_BAWAAN or len(INGEST_TOKEN) < 24:
        raise RuntimeError("Mode produksi: isi INGEST_TOKEN dengan token acak minimal 24 karakter.")
