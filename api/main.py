import logging
import sqlite3
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent

logging.basicConfig(
    filename=str(BASE_DIR / "app.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# --- db ---

def _get_conn():
    conn = sqlite3.connect(str(BASE_DIR / "events.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            alert BOOLEAN NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# --- schemas ---

class EventType(str, Enum):
    movimento = "movimento"
    parado = "parado"
    queda = "queda"
    inatividade_prolongada = "inatividade_prolongada"
    invasao_perimetro = "invasão_perimetro"


# tipos que disparam alerta
ALERT_TYPES = {EventType.queda, EventType.inatividade_prolongada}


class EventIn(BaseModel):
    camera_id: str
    event_type: EventType
    timestamp: int


class EventOut(BaseModel):
    camera_id: str
    event_type: str
    timestamp: int
    alert: bool


# --- app ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    log.info("db ok")
    yield


app = FastAPI(title="Monitoramento Inteligente", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/event", response_model=EventOut)
async def create_event(body: EventIn):
    # TODO: mover logica de alerta pra um service layer separado
    # pra facilitar testes unitários quando as regras do Projeto crescerem
    alert = body.event_type in ALERT_TYPES

    conn = _get_conn()
    conn.execute(
        "INSERT INTO events (camera_id, event_type, timestamp, alert) VALUES (?, ?, ?, ?)",
        (body.camera_id, body.event_type.value, body.timestamp, alert),
    )
    conn.commit()
    conn.close()

    tag = "ALERTA" if alert else "ok"
    log.info("event saved: [%s] %s (%s)", body.event_type.value, body.camera_id, tag)

    return EventOut(
        camera_id=body.camera_id,
        event_type=body.event_type.value,
        timestamp=body.timestamp,
        alert=alert,
    )
