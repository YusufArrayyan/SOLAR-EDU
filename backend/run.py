"""Jalankan server.

    python backend/run.py              # produksi: butuh ADMIN_EMAIL, ADMIN_PASSWORD, INGEST_TOKEN
    python backend/run.py --simulasi   # pengembangan: data simulasi dan akun uji

Port dari variabel PORT (bawaan 8080), alamat dari HOST (bawaan 127.0.0.1).
"""
import os
import sys
from pathlib import Path

if "--simulasi" in sys.argv:
    os.environ["SOLAR_SIMULATION"] = "1"

import uvicorn  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")
