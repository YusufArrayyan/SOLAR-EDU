from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def siapkan_timescale() -> bool:
    """Ubah tabel deret waktu menjadi hypertable TimescaleDB bila basis datanya PostgreSQL + TimescaleDB."""
    if _is_sqlite:
        return False
    from sqlalchemy import text
    import logging
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            for tabel in ("pengukuran", "agregat_jam"):
                conn.execute(text(f"SELECT create_hypertable('{tabel}', 'waktu', if_not_exists => TRUE, "
                                  "migrate_data => TRUE, chunk_time_interval => INTERVAL '7 days')"))
        return True
    except Exception as e:  # noqa: BLE001 - PostgreSQL biasa tetap berjalan tanpa TimescaleDB
        logging.getLogger("solar").warning("TimescaleDB tidak tersedia, memakai tabel biasa: %s", e)
        return False
