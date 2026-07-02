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

# Logging a fichero con rotación (5 MB × 3 backups) + consola
from logging.handlers import RotatingFileHandler

(BASE_DIR / "logs").mkdir(exist_ok=True)
_formato = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
_fichero = RotatingFileHandler(
    BASE_DIR / "logs" / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding="utf-8",
)
_fichero.setFormatter(_formato)
_consola = logging.StreamHandler(sys.stdout)
_consola.setFormatter(_formato)
logging.basicConfig(level=logging.INFO, handlers=[_fichero, _consola])
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


def limpiar_output_antiguo(dias: int = 30) -> int:
    """
    Borra imágenes de output/ con más de `dias` días de antigüedad.
    Devuelve el número de ficheros eliminados.
    """
    import time
    output_dir = BASE_DIR / "output"
    if not output_dir.exists():
        return 0

    limite = time.time() - dias * 86400
    borrados = 0
    for f in output_dir.iterdir():
        if f.suffix.lower() in (".png", ".jpg", ".jpeg") and f.stat().st_mtime < limite:
            f.unlink()
            borrados += 1
    if borrados:
        logger.info(f"Limpieza: {borrados} imágenes con más de {dias} días eliminadas")
    return borrados


def pipeline_semanal() -> None:
    """
    Pipeline principal: se ejecuta cada lunes a las 9:00.
    Genera o retoma el plan de la semana y procesa cada día.
    """
    from agents.planner import generar_plan_semanal
    from core.approval import enviar_para_aprobacion
    from core.config_check import comprobar_todo

    modelo_ollama = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    modelo_sdxl = os.getenv("SDXL_MODEL", "stabilityai/sdxl-turbo")

    logger.info("══ Inicio pipeline semanal ══")

    # Validar configuración — los errores bloquean, los avisos no
    config = comprobar_todo()
    if not config["ok"]:
        logger.error("Configuración inválida — pipeline abortado. Revisar .env")
        return

    # Mantenimiento: borrar imágenes de hace más de un mes
    limpiar_output_antiguo(dias=30)

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
