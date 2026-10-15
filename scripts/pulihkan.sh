#!/usr/bin/env sh
# Pulihkan basis data dari cadangan terenkripsi:  sh scripts/pulihkan.sh backups/solar-20261015-0200.sql.gz.enc
# Target PRD: pemulihan penuh dalam 4 jam. Latihan pemulihan dilakukan tiap semester (lihat docs/SOP.md).
set -eu
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "Pakai: sh scripts/pulihkan.sh <berkas .sql.gz.enc>"; exit 1; }
set -a; . ./.env; set +a
printf "Pemulihan akan MENGGANTI seluruh isi basis data. Ketik PULIHKAN untuk lanjut: "; read -r ok
[ "$ok" = "PULIHKAN" ] || { echo "Dibatalkan."; exit 1; }
docker compose stop app bridge
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$1" | gunzip | \
  docker compose exec -T db sh -c 'dropdb -U solar --if-exists solar_edu && createdb -U solar solar_edu && psql -q -U solar -d solar_edu'
docker compose start app bridge
echo "Pemulihan selesai. Periksa halaman Pengaturan > Status sistem."
