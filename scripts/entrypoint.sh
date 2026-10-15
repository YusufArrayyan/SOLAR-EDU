#!/bin/sh
# Jalankan aplikasi sebagai pengguna non-root. Disk permanen (Render, Docker volume) sering dipasang milik root,
# jadi kepemilikannya diatur dulu sebelum hak akses diturunkan.
set -e
DATA="${SOLAR_DATA_DIR:-/srv/backend/data}"
mkdir -p "$DATA"
if [ "$(id -u)" = "0" ]; then
  chown -R solar:solar "$DATA"
  exec setpriv --reuid=solar --regid=solar --init-groups "$@"
fi
exec "$@"
