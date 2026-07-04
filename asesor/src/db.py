"""Persistencia en SQLite: esquema y CRUD de tareas, diario y decisiones.

QUÉ: una base de datos en un único fichero (data/asesor.db) con tres tablas.
POR QUÉ SQLite: no necesita servidor, un fichero = backup trivial, y el
volumen de datos de un asistente personal es mínimo. Cada función abre su
propia conexión (con WAL activado), así se puede llamar sin cuidado desde
hilos distintos (handlers del bot y jobs del scheduler).
"""

import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TZ)

ESTADOS = ("pendiente", "en_curso", "hecha", "cancelada")
ESTADOS_ACTIVOS = ("pendiente", "en_curso")
PRIORIDADES = ("alta", "media", "baja")

_CAMPOS_TAREA = ("titulo", "descripcion", "estado", "prioridad", "deadline")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo         TEXT NOT NULL,
    descripcion    TEXT NOT NULL DEFAULT '',
    estado         TEXT NOT NULL DEFAULT 'pendiente',
    prioridad      TEXT NOT NULL DEFAULT 'media',
    deadline       TEXT,
    creada_en      TEXT NOT NULL,
    actualizada_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diario (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha     TEXT NOT NULL,
    texto     TEXT NOT NULL,
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisiones (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    decision  TEXT NOT NULL,
    contexto  TEXT NOT NULL DEFAULT '',
    fecha     TEXT NOT NULL,
    creado_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tareas_estado   ON tareas (estado);
CREATE INDEX IF NOT EXISTS idx_tareas_deadline ON tareas (deadline);
CREATE INDEX IF NOT EXISTS idx_diario_fecha    ON diario (fecha);
"""


def _ahora() -> datetime:
    return datetime.now(TZ)


def hoy() -> str:
    return _ahora().date().isoformat()


def ayer() -> str:
    return (_ahora() - timedelta(days=1)).date().isoformat()


def _conectar() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with _conectar() as con:
        con.executescript(_ESQUEMA)


def _normalizar_fecha(fecha) -> str | None:
    """Valida YYYY-MM-DD. '' o None → None (sin fecha)."""
    if fecha in (None, ""):
        return None
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError(f"Fecha no válida: {fecha!r} (formato YYYY-MM-DD)") from None
    return fecha


# ------------------------------------------------------------------ tareas

def crear_tarea(titulo: str, descripcion: str = "", prioridad: str = "media",
                deadline: str | None = None) -> dict:
    if not titulo or not titulo.strip():
        raise ValueError("titulo no puede estar vacío")
    if prioridad not in PRIORIDADES:
        raise ValueError(f"prioridad debe ser una de {PRIORIDADES}")
    deadline = _normalizar_fecha(deadline)
    ahora = _ahora().isoformat(timespec="seconds")
    with _conectar() as con:
        cur = con.execute(
            "INSERT INTO tareas (titulo, descripcion, prioridad, deadline, creada_en, actualizada_en)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (titulo.strip(), descripcion, prioridad, deadline, ahora, ahora),
        )
        fila = con.execute("SELECT * FROM tareas WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(fila)


def actualizar_tarea(tarea_id: int, **campos) -> dict:
    """Actualiza los campos indicados. deadline='' borra la fecha límite."""
    campos = {k: v for k, v in campos.items() if v is not None}
    desconocidos = set(campos) - set(_CAMPOS_TAREA)
    if desconocidos:
        raise ValueError(f"Campos no válidos: {sorted(desconocidos)}; permitidos: {_CAMPOS_TAREA}")
    if not campos:
        raise ValueError("No se ha indicado ningún campo a actualizar")
    if "estado" in campos and campos["estado"] not in ESTADOS:
        raise ValueError(f"estado debe ser uno de {ESTADOS}")
    if "prioridad" in campos and campos["prioridad"] not in PRIORIDADES:
        raise ValueError(f"prioridad debe ser una de {PRIORIDADES}")
    if "deadline" in campos:
        campos["deadline"] = _normalizar_fecha(campos["deadline"])

    # Las claves están validadas contra _CAMPOS_TAREA: no hay inyección posible
    asignaciones = ", ".join(f"{campo} = ?" for campo in campos)
    valores = [*campos.values(), _ahora().isoformat(timespec="seconds"), tarea_id]
    with _conectar() as con:
        cur = con.execute(f"UPDATE tareas SET {asignaciones}, actualizada_en = ? WHERE id = ?", valores)
        if cur.rowcount == 0:
            raise ValueError(f"No existe ninguna tarea con id {tarea_id}")
        fila = con.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
    return dict(fila)


def listar_tareas(estado: str | None = None) -> list[dict]:
    """Sin estado (o 'activas') → pendientes + en curso, ordenadas por prioridad."""
    orden = ("ORDER BY CASE prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,"
             " deadline IS NULL, deadline, id")
    with _conectar() as con:
        if estado in (None, "", "activas"):
            filas = con.execute(f"SELECT * FROM tareas WHERE estado IN (?, ?) {orden}",
                                ESTADOS_ACTIVOS).fetchall()
        elif estado == "todas":
            filas = con.execute("SELECT * FROM tareas ORDER BY actualizada_en DESC").fetchall()
        elif estado in ESTADOS:
            filas = con.execute(f"SELECT * FROM tareas WHERE estado = ? {orden}", (estado,)).fetchall()
        else:
            raise ValueError(f"estado debe ser uno de {ESTADOS + ('activas', 'todas')}")
    return [dict(f) for f in filas]


def listar_deadlines(dias: int = 7) -> list[dict]:
    """Tareas activas con deadline dentro de N días (incluye las ya vencidas)."""
    limite = (_ahora().date() + timedelta(days=int(dias))).isoformat()
    with _conectar() as con:
        filas = con.execute(
            "SELECT * FROM tareas WHERE deadline IS NOT NULL AND deadline <= ?"
            " AND estado IN (?, ?) ORDER BY deadline, id",
            (limite, *ESTADOS_ACTIVOS),
        ).fetchall()
    return [dict(f) for f in filas]


def tareas_envejecidas(dias: int = 3) -> list[dict]:
    """Tareas activas sin ninguna actualización desde hace más de N días."""
    corte = (_ahora() - timedelta(days=int(dias))).isoformat(timespec="seconds")
    with _conectar() as con:
        filas = con.execute(
            "SELECT * FROM tareas WHERE estado IN (?, ?) AND actualizada_en < ?"
            " ORDER BY actualizada_en, id",
            (*ESTADOS_ACTIVOS, corte),
        ).fetchall()
    return [dict(f) for f in filas]


# ------------------------------------------------------------------ diario

def log_dia(texto: str, fecha: str | None = None) -> dict:
    if not texto or not texto.strip():
        raise ValueError("texto no puede estar vacío")
    fecha = _normalizar_fecha(fecha) or hoy()
    with _conectar() as con:
        cur = con.execute(
            "INSERT INTO diario (fecha, texto, creado_en) VALUES (?, ?, ?)",
            (fecha, texto.strip(), _ahora().isoformat(timespec="seconds")),
        )
        fila = con.execute("SELECT * FROM diario WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(fila)


def diario_de(fecha: str) -> list[dict]:
    with _conectar() as con:
        filas = con.execute("SELECT * FROM diario WHERE fecha = ? ORDER BY id", (fecha,)).fetchall()
    return [dict(f) for f in filas]


# -------------------------------------------------------------- decisiones

def registrar_decision(decision: str, contexto: str = "") -> dict:
    if not decision or not decision.strip():
        raise ValueError("decision no puede estar vacía")
    with _conectar() as con:
        cur = con.execute(
            "INSERT INTO decisiones (decision, contexto, fecha, creado_en) VALUES (?, ?, ?, ?)",
            (decision.strip(), contexto, hoy(), _ahora().isoformat(timespec="seconds")),
        )
        fila = con.execute("SELECT * FROM decisiones WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(fila)


# ---------------------------------------------------------------- consultas

def buscar_historial(texto: str, limite: int = 20) -> dict:
    """Búsqueda LIKE en las tres tablas. Devuelve resultados agrupados."""
    if not texto or not texto.strip():
        raise ValueError("texto de búsqueda vacío")
    patron = f"%{texto.strip()}%"
    limite = max(1, min(int(limite), 100))
    with _conectar() as con:
        tareas = con.execute(
            "SELECT * FROM tareas WHERE titulo LIKE ? OR descripcion LIKE ?"
            " ORDER BY actualizada_en DESC LIMIT ?",
            (patron, patron, limite),
        ).fetchall()
        diario = con.execute(
            "SELECT * FROM diario WHERE texto LIKE ? ORDER BY fecha DESC LIMIT ?",
            (patron, limite),
        ).fetchall()
        decisiones = con.execute(
            "SELECT * FROM decisiones WHERE decision LIKE ? OR contexto LIKE ?"
            " ORDER BY fecha DESC LIMIT ?",
            (patron, patron, limite),
        ).fetchall()
    return {
        "tareas": [dict(f) for f in tareas],
        "diario": [dict(f) for f in diario],
        "decisiones": [dict(f) for f in decisiones],
    }


def resumen_semana() -> dict:
    """Datos crudos de los últimos 7 días para la retro semanal."""
    desde = _ahora() - timedelta(days=7)
    desde_ts = desde.isoformat(timespec="seconds")
    desde_fecha = desde.date().isoformat()
    with _conectar() as con:
        completadas = con.execute(
            "SELECT * FROM tareas WHERE estado = 'hecha' AND actualizada_en >= ?"
            " ORDER BY actualizada_en",
            (desde_ts,),
        ).fetchall()
        activas = con.execute(
            "SELECT * FROM tareas WHERE estado IN (?, ?) ORDER BY actualizada_en",
            ESTADOS_ACTIVOS,
        ).fetchall()
        entradas = con.execute(
            "SELECT * FROM diario WHERE fecha >= ? ORDER BY fecha, id", (desde_fecha,)
        ).fetchall()
        decisiones = con.execute(
            "SELECT * FROM decisiones WHERE fecha >= ? ORDER BY fecha, id", (desde_fecha,)
        ).fetchall()
    return {
        "completadas_esta_semana": [dict(f) for f in completadas],
        "tareas_activas": [dict(f) for f in activas],
        "diario_semana": [dict(f) for f in entradas],
        "decisiones_semana": [dict(f) for f in decisiones],
    }
