@echo off
REM Jalankan SOLAR-EDU AI mode simulasi di Windows: http://localhost:8080
cd /d "%~dp0\.."
python -m pip install -q -r backend\requirements.txt
python backend\run.py
