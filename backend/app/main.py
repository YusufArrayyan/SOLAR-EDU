"""SOLAR-EDU AI: aplikasi web pemantauan, prediksi, dan rekomendasi energi gedung kampus."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import Base, engine, migrasi_ringan, siapkan_timescale
from .routers import admin, auth, core, kelola, report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("solar")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.periksa_produksi()
    Base.metadata.create_all(engine)
    migrasi_ringan()
    siapkan_timescale()
    from .seed import pastikan_admin, seed, siapkan_produksi
    if config.SIMULATION:
        seed()
        pastikan_admin()
    else:
        siapkan_produksi()
    from .services.jobs import Worker
    worker = Worker()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="SOLAR-EDU AI", version=config.VERSI, lifespan=lifespan,
              docs_url="/api/docs" if config.SIMULATION else None, redoc_url=None,
              openapi_url="/api/openapi.json" if config.SIMULATION else None)

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def keamanan(request: Request, call_next):
    # Perlindungan CSRF: permintaan yang mengubah data wajib membawa header khusus aplikasi.
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/")
            and request.url.path != "/api/ingest" and request.headers.get("x-solar-edu") != "1"):
        return JSONResponse({"detail": "Permintaan ditolak."}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if config.COOKIE_SECURE:  # hanya di balik HTTPS (Render, Nginx)
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if not request.url.path.startswith("/api/docs"):
        resp.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(RequestValidationError)
async def galat_validasi(_: Request, exc: RequestValidationError):
    kolom = {".".join(str(x) for x in e["loc"][1:]): e["msg"] for e in exc.errors()}
    return JSONResponse({"detail": {"pesan": "Data yang dikirim tidak lengkap atau formatnya salah.",
                                    "kolom": kolom}}, status_code=422)


app.include_router(auth.router)
app.include_router(core.router)
app.include_router(report.router)
app.include_router(admin.router)
app.include_router(kelola.router)


@app.get("/api/sehat")
def sehat():
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import Gedung
    from .services.jobs import STATUS
    with SessionLocal() as db:
        g = db.scalar(select(Gedung.nama).where(Gedung.peran == "percontohan"))
    hasil = {"status": "ok", "versi": config.VERSI, "simulasi": config.SIMULATION, "gedung": g, "pekerja": STATUS}
    if config.SIMULATION:
        from .seed import DEMO_PASSWORD
        hasil["demo_sandi"] = DEMO_PASSWORD  # akun demo memang publik; akun asli tidak terpengaruh
    return hasil


app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIR / "assets"), name="assets")
app.mount("/js", StaticFiles(directory=config.FRONTEND_DIR / "js"), name="js")
app.mount("/css", StaticFiles(directory=config.FRONTEND_DIR / "css"), name="css")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(config.FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(config.FRONTEND_DIR / "assets" / "favicon.ico")


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})
