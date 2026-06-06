"""
Scheduler: lanza el pipeline de publicación cada lunes a las 9:00.
Si el bot se reinicia, lee weekly_plan.json y continúa desde donde
se quedó sin regenerar los días ya procesados.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    filename=BASE_DIR / "logs" / "bot.log",
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
# También mostrar en consola
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
logger = logging.getLogger("scheduler")

STATE_FILE = BASE_DIR / "state" / "weekly_plan.json"


def ejecutar_pipeline_dia(dia: dict, modelo_ollama: str, modelo_sdxl: str) -> dict:
    """
    Ejecuta el pipeline completo para un día: copy → imagen → compositor.
    Devuelve el día actualizado con caption, image_path y estado.

    Ollama y SDXL no se ejecutan simultáneamente para respetar los 8GB de VRAM.
    """
    from agents.copy_agent import generar_caption
    from agents.compositor import montar_story
    from agents.image_agent import obtener_imagen_base

    nombre_dia = dia["dia_semana"]
    fecha = dia["fecha"]
    logger.info(f"── Procesando {nombre_dia} {fecha} ──")

    try:
        # 1. Generar caption con Ollama (VRAM de Ollama, independiente)
        logger.info(f"[{nombre_dia}] Generando caption...")
        resultado_copy = generar_caption(dia, modelo=modelo_ollama)
        dia["caption"] = resultado_copy["caption"]
        dia["hashtags"] = resultado_copy["hashtags"]
        logger.info(f"[{nombre_dia}] Caption: {dia['caption'][:60]}...")

        # 2. Generar imagen con SDXL-Turbo (Ollama ya terminó — VRAM libre)
        logger.info(f"[{nombre_dia}] Generando imagen base...")
        image_path = obtener_imagen_base(dia, modelo=modelo_sdxl)
        dia["image_path"] = str(image_path)
        logger.info(f"[{nombre_dia}] Imagen: {image_path}")

        # 3. Montar story con Pillow (solo CPU)
        logger.info(f"[{nombre_dia}] Montando story...")
        from agents.compositor import montar_ambos
        rutas = montar_ambos(
            image_path=image_path,
            caption=dia["caption"],
            hashtags=dia.get("hashtags", []),
            fecha=fecha,
            dia_semana=nombre_dia,
            titulo=dia.get("titulo"),
        )
        story_path = rutas["story"]
        dia["feed_path"] = str(rutas["feed"])
        dia["story_path"] = str(story_path)
        dia["estado"] = "pendiente_aprobacion"
        logger.info(f"[{nombre_dia}] Story lista: {story_path}")

    except Exception as e:
        logger.error(f"[{nombre_dia}] Error en pipeline: {e}", exc_info=True)
        dia["estado"] = "error"
        dia["error"] = str(e)

    return dia


def _guardar_plan(plan: dict) -> None:
    """Persiste el plan en disco."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def _cargar_plan() -> dict | None:
    """Carga el plan existente si lo hay."""
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def pipeline_semanal() -> None:
    """
    Pipeline principal: se ejecuta cada lunes a las 9:00.
    Genera o retoma el plan de la semana y procesa cada día.
    """
    from agents.planner import generar_plan_semanal
    from core.approval import enviar_para_aprobacion

    modelo_ollama = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    modelo_sdxl = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")

    logger.info("══ Inicio pipeline semanal ══")

    # Cargar plan existente o generar uno nuevo
    plan = _cargar_plan()
    if plan:
        logger.info("Plan existente encontrado — continuando desde donde se dejó")
    else:
        logger.info("Generando nuevo plan semanal...")
        plan = generar_plan_semanal(modelo=modelo_ollama)
        _guardar_plan(plan)

    # Procesar solo los días pendientes
    dias_pendientes = [
        (fecha, dia) for fecha, dia in plan.items()
        if dia["estado"] in ("pendiente", "error")
    ]
    logger.info(f"Días pendientes: {len(dias_pendientes)}")

    for fecha, dia in dias_pendientes:
        # Saltar días pasados (solo publicar hoy o futuro)
        if fecha < datetime.now().strftime("%Y-%m-%d"):
            logger.info(f"Saltando {dia['dia_semana']} {fecha} — fecha pasada")
            plan[fecha]["estado"] = "descartado"
            _guardar_plan(plan)
            continue

        dia_actualizado = ejecutar_pipeline_dia(dia, modelo_ollama, modelo_sdxl)
        plan[fecha] = dia_actualizado
        _guardar_plan(plan)

        # Enviar al bot de Telegram para aprobación
        if dia_actualizado["estado"] == "pendiente_aprobacion":
            try:
                enviar_para_aprobacion(dia_actualizado)
            except Exception as e:
                logger.error(f"Error enviando a Telegram: {e}")

    logger.info("══ Pipeline semanal completado ══")


def iniciar_scheduler() -> None:
    """Inicia el scheduler bloqueante — cron cada lunes a las 9:00."""
    scheduler = BlockingScheduler(timezone="Europe/Madrid")

    scheduler.add_job(
        pipeline_semanal,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="pipeline_semanal",
        name="Pipeline semanal Meraki",
        misfire_grace_time=3600,  # tolera hasta 1h de retraso de arranque
        replace_existing=True,
    )

    logger.info("Scheduler iniciado — pipeline cada lunes a las 09:00 (Europe/Madrid)")
    logger.info("Ctrl+C para detener")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler detenido")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scheduler Meraki Bot")
    parser.add_argument(
        "--ahora",
        action="store_true",
        help="Ejecutar el pipeline inmediatamente (sin esperar al lunes)",
    )
    args = parser.parse_args()

    if args.ahora:
        logger.info("Ejecutando pipeline manualmente...")
        pipeline_semanal()
    else:
        iniciar_scheduler()
