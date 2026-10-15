"""Jalankan server pengembangan: python backend/run.py (port dari variabel PORT, bawaan 8080)."""
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")
