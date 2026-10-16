#!/usr/bin/env sh
# Jalankan SOLAR-EDU AI mode simulasi: http://localhost:8080
cd "$(dirname "$0")/.."
python3 -m pip install -q -r backend/requirements.txt
python3 backend/run.py --simulasi
