"""Tools del agente: schemas para la API + despachador hacia db.py.

QUÉ: dos piezas. TOOLS es la lista de JSON Schema que se manda a Anthropic
para que el modelo sepa qué puede hacer y con qué parámetros. ejecutar()
recibe cada tool_use del modelo y lo traduce a una llamada a db.py.
POR QUÉ separado de agente.py: añadir una tool = añadir su schema aquí y una
entrada en _EJECUTORES, sin tocar el bucle del agente.

Nota: las descripciones dicen CUÁNDO usar cada tool, no solo qué hace —
los modelos recientes deciden mejor con condiciones de disparo explícitas.
"""

import json
import logging

from . import db

log = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "crear_tarea",
        "description": (
            "Crea una tarea nueva. Llámala cuando el usuario mencione algo que hay "
            "que hacer, aunque no diga literalmente 'crea una tarea'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título corto y accionable"},
                "descripcion": {"type": "string", "description": "Detalle opcional"},
                "prioridad": {
                    "type": "string",
                    "enum": ["alta", "media", "baja"],
                    "description": "Por defecto 'media'",
                },
                "deadline": {
                    "type": "string",
                    "description": "Fecha límite YYYY-MM-DD, solo si el usuario la menciona",
                },
            },
            "required": ["titulo"],
        },
    },
    {
        "name": "actualizar_tarea",
        "description": (
            "Modifica una tarea existente por su id: cambiar estado (p. ej. marcarla "
            "'hecha' cuando el usuario diga que la terminó), prioridad, deadline, "
            "título o descripción. Si no sabes el id, usa antes listar_tareas o "
            "buscar_historial."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tarea_id": {"type": "integer", "description": "Id de la tarea"},
                "titulo": {"type": "string"},
                "descripcion": {"type": "string"},
                "estado": {
                    "type": "string",
                    "enum": ["pendiente", "en_curso", "hecha", "cancelada"],
                },
                "prioridad": {"type": "string", "enum": ["alta", "media", "baja"]},
                "deadline": {
                    "type": "string",
                    "description": "YYYY-MM-DD; cadena vacía '' para quitar la fecha",
                },
            },
            "required": ["tarea_id"],
        },
    },
    {
        "name": "listar_tareas",
        "description": (
            "Lista tareas. Llámala cuando el usuario pregunte qué tiene pendiente o "
            "antes de actualizar una tarea cuyo id no conoces. Sin parámetros "
            "devuelve las activas (pendiente + en_curso) ordenadas por prioridad."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": ["activas", "pendiente", "en_curso", "hecha", "cancelada", "todas"],
                    "description": "Filtro opcional; por defecto 'activas'",
                },
            },
        },
    },
    {
        "name": "listar_deadlines",
        "description": (
            "Tareas activas con fecha límite dentro de N días, incluidas las ya "
            "vencidas. Llámala cuando el usuario pregunte por fechas, entregas o "
            "qué urge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Horizonte en días (por defecto 7)",
                },
            },
        },
    },
    {
        "name": "log_dia",
        "description": (
            "Guarda una entrada en el diario. Llámala cuando el usuario cuente cómo "
            "le ha ido el día, qué ha hecho, o comparta una reflexión personal que "
            "merezca quedar registrada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "La entrada, con las palabras del usuario"},
                "fecha": {
                    "type": "string",
                    "description": "YYYY-MM-DD; por defecto hoy. Úsalo si habla de otro día",
                },
            },
            "required": ["texto"],
        },
    },
    {
        "name": "registrar_decision",
        "description": (
            "Registra una decisión relevante que el usuario haya tomado (elegir una "
            "opción, descartar un camino, comprometerse a algo). Guarda también el "
            "porqué en 'contexto' para poder revisarla en el futuro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "description": "Qué se decidió, en una frase"},
                "contexto": {
                    "type": "string",
                    "description": "Motivo, alternativas descartadas, condiciones",
                },
            },
            "required": ["decision"],
        },
    },
    {
        "name": "buscar_historial",
        "description": (
            "Busca texto en tareas, diario y decisiones. Llámala cuando el usuario "
            "pregunte por algo del pasado ('¿qué decidí sobre X?', '¿cuándo hablé "
            "de Y?') o necesites contexto antes de responder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "Término o frase a buscar"},
                "limite": {
                    "type": "integer",
                    "description": "Máximo de resultados por tabla (por defecto 20)",
                },
            },
            "required": ["texto"],
        },
    },
]

_EJECUTORES = {
    "crear_tarea": db.crear_tarea,
    "actualizar_tarea": db.actualizar_tarea,
    "listar_tareas": db.listar_tareas,
    "listar_deadlines": db.listar_deadlines,
    "log_dia": db.log_dia,
    "registrar_decision": db.registrar_decision,
    "buscar_historial": db.buscar_historial,
}


def ejecutar(nombre: str, entrada: dict) -> tuple[str, bool]:
    """Ejecuta una tool y devuelve (resultado_como_texto, es_error).

    Los errores no se relanzan: se devuelven como texto con es_error=True
    para que el modelo los vea y pueda corregir (p. ej. un id que no existe).
    """
    funcion = _EJECUTORES.get(nombre)
    if funcion is None:
        return f"Tool desconocida: {nombre}", True
    try:
        resultado = funcion(**entrada)
    except (TypeError, ValueError) as e:
        # Error "esperable" (parámetros mal formados): se lo contamos al modelo
        log.warning("Tool %s%s → %s", nombre, entrada, e)
        return f"Error: {e}", True
    except Exception as e:
        log.exception("Fallo inesperado ejecutando la tool %s", nombre)
        return f"Error interno en {nombre}: {e}", True
    log.info("🔧 %s(%s) OK", nombre, entrada)
    return json.dumps(resultado, ensure_ascii=False, default=str), False
