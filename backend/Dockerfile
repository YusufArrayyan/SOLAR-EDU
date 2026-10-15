FROM python:3.12-slim

# Thread dibatasi agar memori muat di server 512 MB; cpu_count di kontainer sering melaporkan inti host.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Jakarta HOST=0.0.0.0 PORT=8080 \
    SOLAR_DATA_DIR=/srv/backend/data \
    SOLAR_JOBS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2

RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
COPY scripts scripts
RUN useradd -r -u 1001 solar && rm -rf /srv/backend/data && chmod +x scripts/entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["python", "backend/run.py"]
