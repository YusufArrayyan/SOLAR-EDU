import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..models import Pengguna
from ..security import (COOKIE, PERAN, audit, buat_sesi, cek_sandi, current_user, hapus_sesi, izin_peran)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_gagal: dict[str, list[float]] = defaultdict(list)
BATAS_GAGAL, BATAS_IP, JENDELA = 5, 30, 600


def _bersihkan(kunci: str, now: float) -> list[float]:
    _gagal[kunci] = [t for t in _gagal[kunci] if now - t < JENDELA]
    if not _gagal[kunci]:
        _gagal.pop(kunci, None)
        return []
    return _gagal[kunci]


class MasukIn(BaseModel):
    email: str
    sandi: str


def profil(u: Pengguna) -> dict:
    return {"id": u.id, "nama": u.nama, "email": u.email, "peran": u.peran, "peran_label": PERAN[u.peran],
            "izin": izin_peran(u.peran), "email_mingguan": u.email_mingguan, "notif_aplikasi": u.notif_aplikasi,
            "demo": u.demo}


@router.post("/masuk")
def masuk(data: MasukIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = data.email.strip().lower()[:160]
    ip = request.client.host if request.client else "?"
    now = time.time()
    # dikunci per pasangan email + alamat IP, supaya orang lain tidak bisa mengunci akun dari jaringan lain
    k_akun, k_ip = f"{email}|{ip}", f"ip|{ip}"
    if len(_bersihkan(k_akun, now)) >= BATAS_GAGAL or len(_bersihkan(k_ip, now)) >= BATAS_IP:
        raise HTTPException(429, "Terlalu banyak percobaan. Coba lagi dalam 10 menit.")
    u = db.scalar(select(Pengguna).where(func.lower(Pengguna.email) == email))
    if not u or not cek_sandi(data.sandi, u.hash_sandi):
        _gagal[k_akun].append(now)
        _gagal[k_ip].append(now)
        audit(db, u.id if u else None, "masuk.gagal", email)
        db.commit()
        raise HTTPException(401, "Email atau kata sandi salah. Periksa lagi, lalu coba masuk.")
    if not u.aktif:
        raise HTTPException(403, "Akun ini dinonaktifkan. Hubungi tim pengelola.")
    _gagal.pop(k_akun, None)
    token = buat_sesi(db, u)
    audit(db, u.id, "masuk", request.client.host if request.client else "")
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=config.COOKIE_SECURE,
                        max_age=60 * 60 * 12, path="/")
    return profil(u)


@router.post("/keluar")
def keluar(request: Request, response: Response, db: Session = Depends(get_db)):
    hapus_sesi(db, request.cookies.get(COOKIE))
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/saya")
def saya(user: Pengguna = Depends(current_user)):
    return profil(user)
