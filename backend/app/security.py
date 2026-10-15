"""Autentikasi, sesi, dan otorisasi berbasis peran (matriks hak akses PRD)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import SESSION_IDLE_MINUTES
from .db import get_db
from .models import LogAudit, Pengguna, Sesi

PERAN = {
    "pengelola": "Pengelola gedung",
    "piket": "Mahasiswa piket",
    "tim": "Tim pengelola",
    "pimpinan": "Pimpinan kampus",
    "akademik": "Mahasiswa dan dosen",
}

# Matriks hak akses. L = melihat, U = mengubah atau melakukan aksi.
IZIN: dict[str, set[str]] = {
    "ringkasan.lihat": {"pengelola", "piket", "tim", "pimpinan"},
    "rekomendasi.lihat": {"pengelola", "piket", "tim", "pimpinan"},  # piket: hanya tugasnya
    "rekomendasi.verifikasi": {"pengelola", "tim"},
    "tugas.tandai": {"pengelola", "piket", "tim"},
    "evaluasi.catat": {"pengelola", "tim"},
    "dampak.lihat": {"pengelola", "tim", "pimpinan"},
    "belajar.lihat": {"pengelola", "piket", "tim", "pimpinan", "akademik"},
    "pengaturan.ubah": {"tim"},
    "pengguna.kelola": {"tim"},
    "audit.lihat": {"tim"},
}

COOKIE = "solar_sesi"
_ITER = 260_000


def hash_sandi(sandi: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", sandi.encode(), bytes.fromhex(salt), _ITER)
    return f"pbkdf2_sha256${_ITER}${salt}${dk.hex()}"


def cek_sandi(sandi: str, tersimpan: str) -> bool:
    try:
        _, it, salt, h = tersimpan.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", sandi.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def buat_sesi(db: Session, pengguna: Pengguna) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Sesi(token_hash=hash_token(token), pengguna_id=pengguna.id))
    return token


def hapus_sesi(db: Session, token: str | None) -> None:
    if token:
        s = db.get(Sesi, hash_token(token))
        if s:
            db.delete(s)


def izin_peran(peran: str) -> list[str]:
    return sorted(k for k, v in IZIN.items() if peran in v)


def audit(db: Session, pengguna_id: str | None, aksi: str, detail: str = "") -> None:
    db.add(LogAudit(pengguna_id=pengguna_id, aksi=aksi, detail=detail, waktu=datetime.now()))


def current_user(request: Request, db: Session = Depends(get_db)) -> Pengguna:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sesi berakhir. Silakan masuk lagi.")
    sesi = db.get(Sesi, hash_token(token))
    now = datetime.now()
    if not sesi or now - sesi.terakhir_aktif > timedelta(minutes=SESSION_IDLE_MINUTES):
        if sesi:
            db.delete(sesi)
            db.commit()
        raise HTTPException(401, "Sesi berakhir karena tidak aktif 30 menit. Silakan masuk lagi.")
    user = db.get(Pengguna, sesi.pengguna_id)
    if not user or not user.aktif:
        raise HTTPException(401, "Akun tidak aktif. Hubungi tim pengelola.")
    if (now - sesi.terakhir_aktif).total_seconds() > 30:
        sesi.terakhir_aktif = now
        db.commit()
    return user


def require(izin: str):
    def dep(user: Pengguna = Depends(current_user)) -> Pengguna:
        if user.peran not in IZIN[izin]:
            raise HTTPException(403, "Peran akun ini tidak memiliki akses ke fungsi tersebut.")
        return user
    return dep
