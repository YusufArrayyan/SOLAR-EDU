FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Jakarta
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
COPY scripts scripts
RUN useradd -r -u 1001 solar && mkdir -p /srv/backend/data && chown -R solar /srv/backend/data
USER solar
EXPOSE 8080
CMD ["python", "backend/run.py"]
