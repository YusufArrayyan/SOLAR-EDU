#!/usr/bin/env sh
# Pemasangan SOLAR-EDU AI di server kampus dengan satu perintah:  sh scripts/pasang.sh
# Membuat .env berisi rahasia acak, sertifikat TLS swa-tanda (ganti dengan sertifikat kampus bila ada),
# akun broker MQTT, lalu menjalankan seluruh layanan Docker Compose.
set -eu
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker belum terpasang. Pasang Docker Engine terlebih dahulu."; exit 1; }
command -v openssl >/dev/null || { echo "openssl belum terpasang."; exit 1; }
acak() { openssl rand -hex 24; }

if [ ! -f .env ]; then
  printf "Email admin tim pengelola: "; read -r ADMIN_EMAIL
  printf "Nama host server (mis. solar.unib.ac.id): "; read -r HOST
  ADMIN_PASSWORD=$(acak)
  cat > .env <<ENV
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
SERVER_HOST=$HOST
DB_PASSWORD=$(acak)
INGEST_TOKEN=$(acak)
MQTT_USER=jembatan
MQTT_PASSWORD=$(acak)
GATEWAY_USER=gateway
GATEWAY_PASSWORD=$(acak)
BACKUP_PASSPHRASE=$(acak)
SOLAR_SIMULATION=0
WEATHER_LIVE=1
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=
ENV
  chmod 600 .env
  echo "Berkas .env dibuat. Kata sandi awal admin ada di .env (ADMIN_PASSWORD); ganti setelah masuk pertama."
  echo "Simpan BACKUP_PASSPHRASE di tempat aman terpisah: tanpa itu cadangan tidak bisa dipulihkan."
fi
set -a; . ./.env; set +a

mkdir -p deploy/certs deploy/mosquitto/certs backups
if [ ! -f deploy/certs/fullchain.pem ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=${SERVER_HOST:-localhost}" \
    -keyout deploy/certs/privkey.pem -out deploy/certs/fullchain.pem 2>/dev/null
  echo "Sertifikat HTTPS swa-tanda dibuat di deploy/certs/."
fi
if [ ! -f deploy/mosquitto/certs/ca.crt ]; then
  d=deploy/mosquitto/certs
  openssl req -x509 -newkey rsa:2048 -nodes -days 1825 -subj "/CN=SOLAR-EDU MQTT CA" -keyout $d/ca.key -out $d/ca.crt 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=${SERVER_HOST:-localhost}" -keyout $d/server.key -out $d/server.csr 2>/dev/null
  openssl x509 -req -in $d/server.csr -CA $d/ca.crt -CAkey $d/ca.key -CAcreateserial -days 825 -out $d/server.crt 2>/dev/null
  chmod 644 $d/server.key
  echo "Sertifikat TLS broker dibuat. Salin $d/ca.crt ke gateway gedung."
fi
if [ ! -f deploy/mosquitto/passwd ]; then
  touch deploy/mosquitto/passwd
  docker compose run --rm --no-deps -T mqtt sh -c \
    "mosquitto_passwd -b /mosquitto/data/passwd '$MQTT_USER' '$MQTT_PASSWORD' && \
     mosquitto_passwd -b /mosquitto/data/passwd '$GATEWAY_USER' '$GATEWAY_PASSWORD' && \
     chmod 0700 /mosquitto/data/passwd"
  echo "Akun broker dibuat: $MQTT_USER (jembatan) dan $GATEWAY_USER (gateway gedung)."
fi

docker compose up -d --build
echo "Selesai. Buka https://${SERVER_HOST:-localhost} dan masuk dengan $ADMIN_EMAIL."
