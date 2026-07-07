"""
Planner: genera el plan de publicaciones para la semana actual.
Consulta pautas.yaml y calendar.yaml, y usa Ollama para enriquecer
la descripción de cada día con contexto creativo.
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import ollama
import yaml

# Configuración del logger
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("planner")

# Rutas base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STATE_DIR = BASE_DIR / "state"
STATE_FILE = STATE_DIR / "weekly_plan.json"


def _cargar_config() -> tuple[dict, dict]:
    """Carga pautas.yaml y calendar.yaml."""
    with open(CONFIG_DIR / "pautas.yaml", encoding="utf-8") as f:
        pautas = yaml.safe_load(f)
    with open(CONFIG_DIR / "calendar.yaml", encoding="utf-8") as f:
        calendar = yaml.safe_load(f)
    return pautas, calendar


def _temporada_actual(mes: int, calendar: dict) -> dict | None:
    """Devuelve la temporada correspondiente al mes dado."""
    for temporada in calendar.get("temporadas", []):
        if mes in temporada["meses"]:
            return temporada
    return None


def _evento_especial_semana(lunes: date, calendar: dict) -> dict | None:
    """Comprueba si hay algún evento especial esta semana."""
    for evento in calendar.get("especiales", []):
        mes = evento.get("mes")
        dia = evento.get("dia")
        if dia:
            fecha_evento = date(lunes.year, mes, dia)
            # Comprobar si el evento cae dentro de la semana lunes–domingo
            if lunes <= fecha_evento <= lunes + timedelta(days=6):
                return evento
    return None


def _generar_idea_ollama(
    dia_nombre: str,
    tema: str,
    enfoque: str,
    temporada: str,
    evento_especial: str | None,
    modelo: str,
    max_reintentos: int = 3,
) -> str:
    """
    Pide a Ollama una idea creativa breve para el día.
    Reintenta hasta max_reintentos veces con 10s de pausa.
    """
    evento_txt = f"Hay un evento especial esta semana: {evento_especial}." if evento_especial else ""

    prompt = f"""Eres el community manager de Meraki Bar & Cocktails, un bar de cócteles
en Santutxu, Bilbao. Necesitas una idea creativa y concreta para la publicación
del {dia_nombre}.

Tema del día: {tema}
Enfoque: {enfoque}
Temporada actual: {temporada}
{evento_txt}

Responde SOLO con una frase corta en español (máximo 20 palabras) describiendo
la idea central del post. Sin emojis. Sin introducción. Solo la idea."""

    for intento in range(1, max_reintentos + 1):
        try:
            respuesta = ollama.generate(model=modelo, prompt=prompt)
            idea = respuesta["response"].strip()
            logger.info(f"  Ollama [{dia_nombre}]: {idea}")
            return idea
        except Exception as e:
            logger.warning(f"  Ollama intento {intento}/{max_reintentos} fallido: {e}")
            if intento < max_reintentos:
                time.sleep(10)

    # Fallback si Ollama no responde
    logger.error(f"  Ollama no disponible para {dia_nombre} — usando enfoque por defecto")
    return enfoque


def generar_plan_semanal(
    modelo: str = "llama3.1:8b",
    forzar: bool = False,
) -> dict:
    """
    Genera el plan de la semana actual.
    Si ya existe weekly_plan.json y no se fuerza, lo devuelve tal cual.

    Returns:
        dict con el plan completo indexado por fecha (YYYY-MM-DD)
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Reutilizar plan existente si ya está generado
    if STATE_FILE.exists() and not forzar:
        with open(STATE_FILE, encoding="utf-8") as f:
            plan = json.load(f)
        logger.info(f"Plan existente cargado desde {STATE_FILE}")
        return plan

    pautas, calendar = _cargar_config()
    bar = pautas["bar"]
    dias_config = pautas["dias"]

    # Calcular el lunes de la semana actual
    hoy = date.today()
    lunes = hoy - timedelta(days=hoy.weekday())

    temporada = _temporada_actual(hoy.month, calendar)
    temporada_nombre = temporada["nombre"] if temporada else "general"
    cocteles_temporada = temporada.get("cocteles_sugeridos", []) if temporada else []

    evento_especial = _evento_especial_semana(lunes, calendar)
    evento_nombre = evento_especial["nombre"] if evento_especial else None

    logger.info(f"Generando plan semana del {lunes} | Temporada: {temporada_nombre}")
    if evento_nombre:
        logger.info(f"Evento especial detectado: {evento_nombre}")

    # Determinar qué día rotativo le toca esta semana (miérc/juev/vier)
    config_rotacion = pautas.get("publicacion_rotatoria", {})
    rotacion_activa = config_rotacion.get("activa", False)
    eventos_rotativos = config_rotacion.get("eventos_rotativos", [])
    siempre_publicar = config_rotacion.get("siempre_publicar", [])
    numero_semana = hoy.isocalendar()[1]
    dia_rotativo = eventos_rotativos[numero_semana % len(eventos_rotativos)] if eventos_rotativos else None
    logger.info(f"Semana {numero_semana} — día rotativo: {dia_rotativo}")

    # Mapeo de índice a nombre de día en minúsculas (clave en pautas.yaml)
    nombres_dia = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

    plan = {}
    for i, nombre_dia in enumerate(nombres_dia):
        fecha = lunes + timedelta(days=i)
        config_dia = dias_config[nombre_dia]

        # Comprobar si se publica este día
        if not config_dia.get("publicar", True):
            logger.info(f"  Saltando {nombre_dia} — {config_dia.get('motivo', 'no publicar')}")
            plan[str(fecha)] = {
                "fecha": str(fecha),
                "dia_semana": nombre_dia,
                "estado": "no_publicar",
                "motivo": config_dia.get("motivo", "cerrado"),
            }
            continue

        # Si la rotación está activa y este día es rotativo, comprobar si le toca
        if rotacion_activa and nombre_dia in eventos_rotativos and nombre_dia not in siempre_publicar:
            if nombre_dia != dia_rotativo:
                logger.info(f"  Saltando {nombre_dia} — no le toca esta semana (toca {dia_rotativo})")
                plan[str(fecha)] = {
                    "fecha": str(fecha),
                    "dia_semana": nombre_dia,
                    "estado": "no_publicar",
                    "motivo": f"rotación — esta semana publica {dia_rotativo}",
                }
                continue

        logger.info(f"Planificando {nombre_dia} ({fecha})...")

        idea = _generar_idea_ollama(
            dia_nombre=nombre_dia,
            tema=config_dia["tema"],
            enfoque=config_dia["enfoque"],
            temporada=temporada_nombre,
            evento_especial=evento_nombre,
            modelo=modelo,
        )

        plan[str(fecha)] = {
            "fecha": str(fecha),
            "dia_semana": nombre_dia,
            "tema": config_dia["tema"],
            "enfoque": config_dia["enfoque"],
            "idea_creativa": idea,
            "titulo": config_dia["tema"].title(),
            "titulo_script": config_dia.get("titulo_script"),
            "titulo_grande": config_dia.get("titulo_grande"),
            "hashtag_variable": config_dia["hashtag_variable"],
            "prompt_imagen_extra": config_dia.get("prompt_imagen_extra", ""),
            "temporada": temporada_nombre,
            "cocteles_temporada": cocteles_temporada,
            "evento_especial": evento_nombre,
            # Campos de estado del pipeline
            "caption": None,
            "image_path": None,
            "estado": "pendiente",  # pendiente | aprobado | publicado | descartado
            "intentos_regeneracion": 0,
        }

    # Persistir el plan
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    logger.info(f"Plan guardado en {STATE_FILE}")
    return plan


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    modelo = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    print(f"\nGenerando plan semanal con modelo {modelo}...\n")
    plan = generar_plan_semanal(modelo=modelo, forzar=True)

    print("\n── Plan de la semana ──────────────────────────────────────")
    for fecha, dia in plan.items():
        estado = dia.get("estado", "pendiente")
        if estado == "no_publicar":
            print(f"\n{dia['dia_semana'].upper()} {fecha}  ✗ {dia.get('motivo', 'no publicar')}")
            continue
        print(f"\n{dia['dia_semana'].upper()} {fecha}  ✓ publicar")
        print(f"  Tema       : {dia['tema']}")
        print(f"  Idea       : {dia['idea_creativa']}")
        print(f"  Hashtag    : {dia['hashtag_variable']}")
        print(f"  Temporada  : {dia['temporada']}")
