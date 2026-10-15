"""Status simulasi (epoch dan kebiasaan yang sudah diperbaiki), disimpan di tabel pengaturan."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Pengaturan

KUNCI = "_sim_state"


def get(db: Session) -> dict | None:
    row = db.get(Pengaturan, KUNCI)
    return json.loads(row.nilai) if row else None


def save(db: Session, state: dict) -> None:
    row = db.get(Pengaturan, KUNCI)
    if row is None:
        db.add(Pengaturan(kunci=KUNCI, nilai=json.dumps(state), diubah_pada=datetime.now()))
    else:
        row.nilai = json.dumps(state)
        row.diubah_pada = datetime.now()
